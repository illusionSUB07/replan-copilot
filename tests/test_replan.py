from copilot.plant import SHIFT_LEN, daily_package
from copilot.replan import call_off_changes, cost, day_checks, evaluate, known, resequence, run_day
from copilot.scenarios import bad_day
from copilot.schedule import plan
from copilot.solver import sequence

DAY = 1
SEQ, _ = sequence(daily_package(DAY), time_limit=5)
ROWS = plan(SEQ, DAY)
DIS = bad_day(ROWS)


def test_known_filters_by_time():
    assert known(DIS, -1) == []
    assert len(known(DIS, 10**9)) == len(DIS)


def test_unchanged_plan_has_no_call_off_changes():
    assert call_off_changes(ROWS, ROWS, DAY * SHIFT_LEN) == (0, 0)


def test_resequence_freezes_built_cars_and_keeps_all_orders():
    now = DAY * SHIFT_LEN + 300
    new = resequence(ROWS, DIS, now)
    assert sorted(r["order"].id for r in new) == sorted(r["order"].id for r in ROWS)
    built_before = [r for r in new if r["assembly_in"] < now]
    assert all(r in ROWS for r in built_before)


def test_resequence_removes_predicted_out_of_sequence():
    now = DAY * SHIFT_LEN + 400
    opts = evaluate(ROWS, DIS, now)
    assert opts["wait"]["call_off_changes"] == 0
    assert opts["resequence"]["out_of_sequence"] <= opts["wait"]["out_of_sequence"]


def test_policies_differ_on_bad_day_and_match_on_calm():
    checks = day_checks(DAY)
    never, _ = run_day(ROWS, DIS, lambda n, r: False, checks)
    always, log = run_day(ROWS, DIS, lambda n, r: True, checks)
    assert never["total_eur"] != always["total_eur"] and log
    calm_never, _ = run_day(ROWS, [], lambda n, r: False, checks)
    calm_always, _ = run_day(ROWS, [], lambda n, r: True, checks)
    assert calm_never["total_eur"] == calm_always["total_eur"] == 0
