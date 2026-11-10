"""Assembly sequencing as CP-SAT: place every order once, minimise k-in-n spacing violations."""
from ortools.sat.python import cp_model

from .plant import OPTIONS

PLANT_RULES = {opt: (k, win) for opt, (_, k, win) in OPTIONS.items()}


def sequence(orders, time_limit=10.0, rules=PLANT_RULES, prefer=None):
    # prefer: {order id: previous position}; among equally good sequences, keep cars where they were
    n = len(orders)
    m = cp_model.CpModel()
    x = {(i, p): m.new_bool_var(f"x{i}_{p}") for i in range(n) for p in range(n)}
    for i in range(n):
        m.add_exactly_one(x[i, p] for p in range(n))
    for p in range(n):
        m.add_exactly_one(x[i, p] for i in range(n))

    slack = []
    for opt, (k, win) in rules.items():
        holders = [i for i, o in enumerate(orders) if opt in o.options]
        at = [sum(x[i, p] for i in holders) for p in range(n)]
        for s in range(n - win + 1):
            v = m.new_int_var(0, win, f"v_{opt}_{s}")
            m.add(sum(at[s:s + win]) <= k + v)
            slack.append(v)
    moves = []
    for i, o in enumerate(orders):
        if prefer and o.id in prefer:
            moves += [abs(p - prefer[o.id]) * x[i, p] for p in range(n)]
            m.add_hint(x[i, min(prefer[o.id], n - 1)], 1)
    m.minimize(1000 * sum(slack) + sum(moves))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"no sequence found: {solver.status_name(status)}")
    seq = sorted(range(n), key=lambda i: next(p for p in range(n) if solver.value(x[i, p])))
    out = [orders[i] for i in seq]
    return out, violations(out, rules)  # recount: v vars may carry slack in non-optimal solutions


def violations(seq, rules=PLANT_RULES):
    count = 0
    for opt, (k, win) in rules.items():
        flags = [opt in o.options for o in seq]
        count += sum(max(0, sum(flags[s:s + win]) - k) for s in range(len(seq) - win + 1))
    return count
