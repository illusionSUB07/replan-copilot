from copilot.plant import BODY_LEAD, SHIFT_LEN, TAKT, daily_package
from copilot.schedule import plan
from copilot.sim import kpis, simulate
from copilot.solver import sequence, violations

DAY = 1


def setup(n=30):
    seq, viol = sequence(daily_package(DAY, n=n), time_limit=5)
    return seq, viol, plan(seq, DAY)


def test_solver_places_every_order_and_reports_true_violations():
    orders = daily_package(DAY, n=30)
    seq, viol = sequence(orders, time_limit=5)
    assert sorted(o.id for o in seq) == sorted(o.id for o in orders)
    assert viol == violations(seq)
    assert viol <= violations(orders)


def test_backward_schedule_is_consistent():
    _, _, rows = setup()
    for r in rows:
        assert r["paint_in"] - r["body_in"] == BODY_LEAD
        assert r["body_in"] < r["paint_in"] < r["assembly_in"] < r["finished"]
    assert rows[1]["assembly_in"] - rows[0]["assembly_in"] == TAKT


def test_no_disruption_matches_plan():
    _, _, rows = setup()
    actual = simulate(rows)
    for r in rows:
        assert actual[r["order"].id]["assembly_in"] == r["assembly_in"]
    k = kpis(rows, actual)
    assert k["out_of_sequence"] == 0 and k["late_cars"] == 0


def test_repaint_pulls_next_car_forward():
    _, _, rows = setup()
    victim = rows[0]["order"].id
    actual = simulate(rows, [{"type": "repaint", "order": victim}])
    assert actual[victim]["actual_pos"] > 0
    assert actual[rows[1]["order"].id]["actual_pos"] == 0


def test_assembly_stop_shifts_everything_after_it():
    _, _, rows = setup()
    s = DAY * SHIFT_LEN
    actual = simulate(rows, [{"type": "assembly_stop", "start": s, "end": s + 40}])
    assert actual[rows[0]["order"].id]["assembly_in"] == s + 40
    assert kpis(rows, actual)["out_of_sequence"] == 0
