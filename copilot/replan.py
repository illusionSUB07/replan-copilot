"""Replanning: what is known at time `now`, the resequence option, its cost, and a day loop for any policy."""
from .plant import SHIFT_LEN
from .sim import kpis, lis, simulate

# synthetic cost assumptions in EUR
CALL_OFF_CHANGE = 40      # supplier re-sequences one car with normal lead time
EMERGENCY_CHANGE = 250    # same, inside the freeze window
FREEZE = 120              # minutes before assembly in which call-offs are frozen
OUT_OF_SEQUENCE = 150     # car reaches the line in a different order than suppliers delivered
CARRY_OVER = 900          # car not built today


def known(disruptions, now):
    return [d for d in disruptions if d["known_at"] <= now]


def resequence(rows, disruptions, now):
    """Sandbox: predict the day from what is known and make that prediction the plan; built cars stay frozen."""
    actual = simulate(rows, known(disruptions, now))
    by_id = {r["order"].id: r for r in rows}
    order = sorted(actual, key=lambda oid: (actual[oid].get("actual_pos", len(rows)), actual[oid]["pos"]))
    new = []
    for oid in order:
        r, a = by_id[oid], actual[oid]
        if a.get("assembly_in", now) < now:
            new.append(r)
        else:
            new.append({**r, "pos": len(new), "assembly_in": a.get("assembly_in", r["assembly_in"])})
    return new


def _kept(seq):
    # indices of one longest increasing subsequence (O(n^2), n <= a few hundred)
    best, prev = [1] * len(seq), [-1] * len(seq)
    for i in range(len(seq)):
        for j in range(i):
            if seq[j] < seq[i] and best[j] + 1 > best[i]:
                best[i], prev[i] = best[j] + 1, j
    i, keep = (max(range(len(seq)), key=best.__getitem__) if seq else -1), set()
    while i >= 0:
        keep.add(i)
        i = prev[i]
    return keep


def call_off_changes(old, new, now):
    """Unbuilt cars a supplier must re-sequence, split into (normal, inside freeze window by old plan time)."""
    old_by = {r["order"].id: (i, r) for i, r in enumerate(old)}
    open_ids = [r["order"].id for r in new if r["assembly_in"] >= now]
    keep = _kept([old_by[oid][0] for oid in open_ids])
    moved = [oid for i, oid in enumerate(open_ids) if i not in keep]
    frozen = sum(old_by[oid][1]["assembly_in"] < now + FREEZE for oid in moved)
    return len(moved) - frozen, frozen


def cost(rows, disruptions, normal=0, emergency=0):
    k = kpis(rows, simulate(rows, disruptions))
    eur = {
        "out_of_sequence": k["out_of_sequence"] * OUT_OF_SEQUENCE,
        "carried_over": k["carried_over"] * CARRY_OVER,
        "call_offs": normal * CALL_OFF_CHANGE + emergency * EMERGENCY_CHANGE,
    }
    return {**k, "call_off_changes": normal, "emergency_changes": emergency,
            "cost_eur": eur, "total_eur": sum(eur.values())}


def evaluate(rows, disruptions, now):
    """Predicted day cost for 'wait' vs 'resequence', using only what is known at `now`."""
    seen = known(disruptions, now)
    new = resequence(rows, disruptions, now)
    n, e = call_off_changes(rows, new, now)
    return {"wait": cost(rows, seen), "resequence": cost(new, seen, n, e)}


def run_day(rows, disruptions, policy, checks):
    """Ask `policy(now, rows)` at each check; on True release the resequenced plan. Returns final cost and log."""
    normal = emergency = 0
    log = []
    for now in checks:
        if policy(now, rows):
            new = resequence(rows, disruptions, now)
            n, e = call_off_changes(rows, new, now)
            normal, emergency, rows = normal + n, emergency + e, new
            log.append((now, n, e))
    return cost(rows, disruptions, normal, emergency), log


def day_checks(day, every=120):
    start = day * SHIFT_LEN
    return list(range(start - 60, start + SHIFT_LEN, every))
