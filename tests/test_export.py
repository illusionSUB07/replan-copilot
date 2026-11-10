import json

from copilot.export import export
from copilot.plant import daily_package
from copilot.replan import day_checks, expected_rule, run_day
from copilot.scenarios import bad_day
from copilot.schedule import plan

DAY = 1
ROWS = plan(daily_package(DAY, seed=4), DAY)  # unsolved order is a valid plan and keeps the test fast
DIS = bad_day(ROWS, 4)
CHECKS = day_checks(DAY)


def test_trace_does_not_change_results():
    trace = []
    assert run_day(ROWS, DIS, expected_rule(DIS), CHECKS, trace) == run_day(ROWS, DIS, expected_rule(DIS), CHECKS)
    assert [t for t, _, _ in trace] == CHECKS


def test_export_is_consistent_with_run_day():
    out = json.loads(json.dumps(export(ROWS, DIS, CHECKS, DAY, "expected")))
    final, log = run_day(ROWS, DIS, expected_rule(DIS), CHECKS)
    assert out["final"]["policy"]["total_eur"] == final["total_eur"]
    assert [c["time"] for c in out["checks"] if c["decision"] == "release"] == [t for t, _, _ in log]
    assert all(c["reason"] and set(c["options"]) == {"0", "60", "120", "180"} for c in out["checks"])
    for f in out["final"].values():
        assert sum(e["eur"] for e in f["events"]) == f["total_eur"]
    assert len(out["plan"]) == len(out["outcome"]) == len(ROWS)
    assert sum(c["out_of_sequence"] for c in out["outcome"].values()) == final["out_of_sequence"]
    never = export(ROWS, DIS, CHECKS, DAY, "never")
    assert never["final"]["policy"]["total_eur"] == never["final"]["never"]["total_eur"]


def test_short_keeps_only_claudes_decision_sentence():
    from copilot.export import short
    assert short("Numbers...\n\n**Decision:** keep it.\n- **Still open:** y") == "keep it."
    assert short("just one line") == "just one line"
