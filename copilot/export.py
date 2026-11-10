"""Replay export: one simulated day as JSON for the web view (web/index.html)."""
from . import plant, replan
from .replan import SLIPS, _kept, evaluate, expected, run_day
from .sim import simulate

POLICIES = {
    "expected": ("expected rule", replan.expected_rule),
    "greedy": ("greedy rule", replan.greedy_rule),
    "never": ("never replan", lambda d: lambda now, rows: False),
    "always": ("always replan", lambda d: lambda now, rows: True),
    "agent": ("claude copilot", lambda d: _agent(d)),
}


def short(text):
    # Claude's closing decision sentence, without markdown, for the decision card
    lines = [l.replace("**", "").strip(" -") for l in text.splitlines() if l.strip()]
    last = next((l for l in reversed(lines) if l.startswith("Decision")), lines[-1] if lines else "")
    return last.replace("**", "").replace("Decision:", "").strip()


def _agent(disruptions):
    from .agent import make_policy  # imported lazily: needs the anthropic SDK and AWS access
    return make_policy(disruptions)


def reason(policy, release, exp_wait, exp_reseq, wait, reseq):
    if exp_reseq < exp_wait:
        why = f"releasing is expected to cost {exp_reseq:,.0f} € vs {exp_wait:,.0f} € for keeping the plan ({reseq:,} vs {wait:,} € if the supplier estimate holds)"
    elif exp_reseq == exp_wait:
        why = f"a new plan would not change the expected cost ({exp_wait:,.0f} € either way)"
    else:
        why = f"keeping the plan is expected to cost {exp_wait:,.0f} € vs {exp_reseq:,.0f} € for releasing ({wait:,} vs {reseq:,} € if the supplier estimate holds)"
    against = release != (exp_reseq < exp_wait)
    return f"{'Release' if release else 'Keep'}{f' ({policy} policy)' if against else ''}: {why}."


def outcome(rows, disruptions, releases, day_end):
    # per-car result plus timestamped cost events that add up to the policy's total
    actual = simulate(rows, disruptions)
    built = sorted((oid for oid in actual if "assembly_in" in actual[oid]), key=lambda oid: actual[oid]["actual_pos"])
    keep = _kept([actual[oid]["pos"] for oid in built])
    oos = {oid for i, oid in enumerate(built) if i not in keep}
    events = [{"t": actual[oid]["assembly_in"], "eur": replan.OUT_OF_SEQUENCE, "what": f"{oid} out of sequence"} for oid in oos]
    events += [{"t": t, "eur": n * replan.CALL_OFF_CHANGE + e * replan.EMERGENCY_CHANGE,
                "what": f"release: {n} call-off changes + {e} emergency"} for t, n, e in releases]
    events += [{"t": day_end, "eur": replan.CARRY_OVER, "what": f"{oid} carried over"} for oid in actual if oid not in built]
    by_id = {r["order"].id: r for r in rows}
    cars = {oid: {"plan_pos": a["pos"], "actual_time": a.get("assembly_in"), "actual_pos": a.get("actual_pos"),
                  "out_of_sequence": oid in oos, "plan_time": by_id[oid]["assembly_in"],
                  "paint_line": by_id[oid]["paint_line"], "body_in": a["body_in"], "paint_in": a["paint_in"],
                  "ready": a["ready"], "assembly_in": a.get("assembly_in"), "finished": a.get("finished")}
            for oid, a in actual.items()}
    return cars, sorted(events, key=lambda e: e["t"])


def export(rows, disruptions, checks, day, policy="expected"):
    name, make = POLICIES[policy]
    trace = []
    pol = make(disruptions)
    final, log = run_day(rows, disruptions, pol, checks, trace)
    own = getattr(pol, "reasons", {})  # the Claude agent explains its own decisions
    never, _ = run_day(rows, disruptions, lambda now, r: False, checks)
    day_start, day_end = day * plant.SHIFT_LEN, (day + 1) * plant.SHIFT_LEN

    check_out = []
    for now, seen, after in trace:
        ev = {g: evaluate(seen, disruptions, now, g) for g in (0, *SLIPS)}
        release = after is not seen
        exp_w, exp_r = expected(ev, "wait"), expected(ev, "resequence")
        check_out.append({
            "time": now,
            "known": [i for i, d in enumerate(disruptions) if d["known_at"] <= now],
            "options": {g: {k: {"total_eur": c["total_eur"], "cost_eur": c["cost_eur"], "out_of_sequence": c["out_of_sequence"],
                                "carried_over": c["carried_over"], "call_off_changes": c["call_off_changes"],
                                "emergency_changes": c["emergency_changes"]} for k, c in e.items()} for g, e in ev.items()},
            "expected_eur": {"wait": round(exp_w), "resequence": round(exp_r)},
            "decision": "release" if release else "keep",
            "reason": short(own[now]) if own.get(now) else reason(name, release, exp_w, exp_r, ev[0]["wait"]["total_eur"], ev[0]["resequence"]["total_eur"]),
        })

    final_rows = trace[-1][2] if trace else rows
    cars, events = outcome(final_rows, disruptions, log, day_end)
    _, never_events = outcome(rows, disruptions, [], day_end)
    strip = lambda c: {k: v for k, v in c.items() if k not in ("avg_delay_min", "max_delay_min")}
    return {
        "plant": {"shift_start": plant.SHIFT_START, "shift_len": plant.SHIFT_LEN, "takt": plant.TAKT, "day": day,
                  "day_start": day_start, "day_end": day_end, "options": list(plant.OPTIONS),
                  "costs_eur": {"out_of_sequence": replan.OUT_OF_SEQUENCE, "carry_over": replan.CARRY_OVER,
                                "call_off_change": replan.CALL_OFF_CHANGE, "emergency_change": replan.EMERGENCY_CHANGE,
                                "freeze_min": replan.FREEZE}},
        "policy": name,
        "plan": [{"id": r["order"].id, "options": sorted(r["order"].options), "pos": r["pos"], "time": r["assembly_in"]}
                 for r in rows],
        "disruptions": [{"id": i, **d} for i, d in enumerate(disruptions)],
        "checks": check_out,
        "outcome": cars,
        "final": {"policy": {**strip(final), "events": events}, "never": {**strip(never), "events": never_events}},
    }
