"""Forward simulation: body/paint are delay stations, assembly is a takt server pulling the next ready car in plan order."""
from bisect import bisect_left

from .plant import ASSEMBLY_LEAD, BODY_LEAD, SHIFT_LEN, TAKT


def _overlap(a, b, s, e):
    return max(0, min(b, e) - max(a, s))


def simulate(rows, disruptions=(), horizon=None):
    # disruption types: body_stop, paint_stop(line), repaint(order), supplier_late(option, until), assembly_stop
    by = lambda t: [d for d in disruptions if d["type"] == t]
    repaints = {d["order"] for d in by("repaint")}
    part_until = {}  # latest supplier message per option wins
    for d in sorted(by("supplier_late"), key=lambda d: d.get("known_at", 0)):
        part_until[d["option"]] = d["until"]

    actual = {}
    for r in rows:
        o = r["order"]
        body_out = r["body_in"] + BODY_LEAD
        body_out += sum(_overlap(r["body_in"], body_out, d["start"], d["end"]) for d in by("body_stop"))
        paint_out = body_out + o.paint_lead() * (2 if o.id in repaints else 1)
        paint_out += sum(_overlap(body_out, paint_out, d["start"], d["end"])
                         for d in by("paint_stop") if d["line"] == r["paint_line"])
        parts = max((part_until.get(opt, 0) for opt in o.options), default=0)
        actual[o.id] = {"pos": r["pos"], "body_in": r["body_in"], "paint_in": body_out,
                        "ready": max(paint_out, parts)}

    start = min(r["assembly_in"] for r in rows)
    end = horizon if horizon is not None else (start // SHIFT_LEN + 1) * SHIFT_LEN
    stops = sorted((d["start"], d["end"]) for d in by("assembly_stop"))
    waiting = [r["order"].id for r in rows]
    t, built = start, 0
    while waiting and t < end:
        stop = next(((s, e) for s, e in stops if s <= t < e), None)
        if stop:
            t = stop[1]
            continue
        nxt = next((oid for oid in waiting if actual[oid]["ready"] <= t), None)
        if nxt is None:
            t = min(actual[oid]["ready"] for oid in waiting)
            continue
        waiting.remove(nxt)
        a = actual[nxt]
        a["assembly_in"], a["finished"], a["actual_pos"] = t, t + ASSEMBLY_LEAD, built
        built += 1
        t += TAKT
    return actual


def lis(seq):
    tails = []
    for x in seq:
        i = bisect_left(tails, x)
        tails[i:i + 1] = [x]
    return len(tails)


def kpis(rows, actual):
    planned = {r["order"].id: r for r in rows}
    built = sorted((a for a in actual.values() if "assembly_in" in a), key=lambda a: a["actual_pos"])
    delays = [a["assembly_in"] - planned[oid]["assembly_in"] for oid, a in actual.items() if "assembly_in" in a]
    return {
        "planned": len(rows),
        "built": len(built),
        "carried_over": len(rows) - len(built),
        # cars that broke the planned order = everything outside the longest in-order chain
        "out_of_sequence": len(built) - lis([a["pos"] for a in built]),
        "late_cars": sum(d > 0 for d in delays),
        "avg_delay_min": round(sum(delays) / max(1, len(delays)), 1),
        "max_delay_min": max(delays, default=0),
    }
