from thread.congen import buildable, generate
from thread.impact import analyse
from thread.plan import DAILY_CAP, DAYS, PER_DAY, VOLUME, WEEKLY_CAP, options_of, run
from thread.product import scenario


def test_rules_are_enforced_and_explained():
    p = scenario("base")
    ok = ("P1", "R1", "T1", "W19", "S1", "A0")
    assert buildable(p, "S1", "EU", ok) is None
    assert buildable(p, "W1", "EU", ("P2", "R3", "T2", "W19", "S1", "A0")) == "R3 not offered on W1"
    assert buildable(p, "S1", "CN", ok) == "P1 not offered in CN"
    assert buildable(p, "S1", "US", ok) == "US requires A1"
    assert buildable(p, "S1", "EU", ("P3", "R1", "T2", "W21", "S1", "A0")) == "P3 excludes W21"
    pools = generate(p)
    assert all(abs(sum(w for _, w in rows) - 1) < 1e-9 for rows in pools.values())
    assert all(buildable(p, mm, k, c) is None for (mm, k), rows in pools.items() for c, _ in rows)


def test_plan_respects_volume_and_capacities():
    p = scenario("base")
    r = run(p, generate(p))
    assert len(r["orders"]) == sum(VOLUME.values()) == DAYS * PER_DAY
    for o, cap in WEEKLY_CAP.items():
        assert sum(o in options_of(i) for i in r["orders"]) <= cap
    for d, seq in r["sequence"].items():
        assert len(seq) == PER_DAY
        for o, cap in DAILY_CAP.items():
            assert sum(o in options_of(i) for i in seq) <= cap


def test_loosening_a_rule_changes_nothing_and_tightening_replaces_invalid_cars():
    loose = analyse("carbon_roof_on_wagon")[0]
    assert loose["configs"]["removed"] == 0 and loose["call_off_changes"] == 0
    tight = analyse("sport_seats_need_sport_trim")[0]
    assert tight["invalid_plan_configs"]["cars"] > 0
    assert tight["orders"]["replaced"] >= tight["invalid_plan_configs"]["cars"]
