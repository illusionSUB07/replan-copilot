"""Mix optimiser, slot planner and sequencer as one chain; every stage keeps as much of the previous plan as it can."""
from collections import Counter

from ortools.sat.python import cp_model

from copilot.plant import Order
from copilot.solver import sequence

VOLUME = {("S1", "EU"): 120, ("S1", "US"): 80, ("S1", "CN"): 60, ("C1", "EU"): 80, ("C1", "US"): 60,
          ("C1", "CN"): 30, ("W1", "EU"): 90, ("W1", "US"): 50, ("W1", "CN"): 30}  # cars per week
WEEKLY_CAP = {"P3": 200, "R3": 50, "R2": 260, "A2": 60}  # supplier capacity per week
DAYS, PER_DAY = 5, 120
DAILY_CAP = {"P3": 45, "R3": 12}  # station capacity per day
SPACING = {"P3": (1, 2), "R3": (1, 5), "R2": (2, 3), "A2": (1, 3)}  # k cars in any n on the line
CHANGE_PENALTY = 1  # a replaced car weighs as much as one car of mix deviation


def solve(m, seconds=10):
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = seconds
    s.parameters.num_workers = 8
    s.parameters.random_seed = 0
    status = s.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(cp_model.CpSolver().status_name(status))
    return s


def mix(product, pools, previous=None):
    """{(model, market, config): quantity}. Hits option-mix targets per model/market within weekly supplier caps."""
    m = cp_model.CpModel()
    q = {(mm, k, c): m.new_int_var(0, VOLUME[(mm, k)], "") for (mm, k), rows in pools.items() for c, _ in rows}
    cost = []
    for (mm, k), vol in VOLUME.items():
        keys = [key for key in q if key[:2] == (mm, k)]
        m.add(sum(q[key] for key in keys) == vol)
        for fam in product["families"].values():
            for o in fam:
                target = round(product["take"][k].get(o, 0) * vol)
                dev = m.new_int_var(0, vol, "")
                count = sum(q[key] for key in keys if o in key[2])
                m.add(count - target <= dev)
                m.add(target - count <= dev)
                cost.append(dev)
    for o, cap in WEEKLY_CAP.items():
        m.add(sum(v for key, v in q.items() if o in key[2]) <= cap)
    for key, before in (previous or {}).items():  # stability: penalise every car the new plan takes away
        if key in q:
            cut = m.new_int_var(0, before, "")
            m.add(before - q[key] <= cut)
            cost.append(CHANGE_PENALTY * cut)
        else:
            cost.append(CHANGE_PENALTY * before)  # config no longer buildable: all its cars must change
    m.minimize(sum(cost))
    s = solve(m)
    return {key: s.value(v) for key, v in q.items() if s.value(v)}


def orders(quantities):
    # stable ids: the n-th car of a configuration keeps its id across replans
    return [f"{mm}|{k}|{'-'.join(c)}|{n}" for (mm, k, c), qty in sorted(quantities.items()) for n in range(qty)]


def options_of(order_id):
    return frozenset(order_id.split("|")[2].split("-"))


def slot(order_ids, previous=None):
    """{order id: day}. Daily volume and station caps hold; cars stay on their previous day where possible."""
    m = cp_model.CpModel()
    x = {(o, d): m.new_bool_var("") for o in order_ids for d in range(DAYS)}
    for o in order_ids:
        m.add_exactly_one(x[o, d] for d in range(DAYS))
    for d in range(DAYS):
        m.add(sum(x[o, d] for o in order_ids) == PER_DAY)
        for opt, cap in DAILY_CAP.items():
            m.add(sum(x[o, d] for o in order_ids if opt in options_of(o)) <= cap)
    prev = previous or {}
    m.maximize(sum(x[o, prev[o]] for o in order_ids if o in prev))
    s = solve(m)
    return {o: d for (o, d), v in x.items() if s.value(v)}


def sequence_days(days, previous=None, seconds=5):
    """{day: [order ids in line order]}; spacing rules first, then keep cars where the previous sequence had them."""
    out = {}
    for d in range(DAYS):
        ids = sorted(o for o, day in days.items() if day == d)
        rules = {o: r for o, r in SPACING.items() if any(o in options_of(i) for i in ids)}
        prefer = {o: i for i, o in enumerate(previous[d])} if previous else None
        seq, _ = sequence([Order(i, options_of(i)) for i in ids], seconds, rules, prefer)
        out[d] = [o.id for o in seq]
    return out


def run(product, pools, previous=None):
    q = mix(product, pools, previous and previous["mix"])
    ids = orders(q)
    days = slot(ids, previous and previous["days"])
    return {"mix": q, "orders": ids, "days": days, "sequence": sequence_days(days, previous and previous["sequence"])}


def mix_gap(product, q):
    """Cars off the option-mix target, summed over all options and model/market groups."""
    gap = 0
    for (mm, k), vol in VOLUME.items():
        counts = Counter(o for (a, b, c), n in q.items() if (a, b) == (mm, k) for o in c for _ in range(n))
        gap += sum(abs(counts[o] - round(product["take"][k].get(o, 0) * vol)) for fam in product["families"].values() for o in fam)
    return gap
