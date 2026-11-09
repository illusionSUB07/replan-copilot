"""Assembly sequencing as CP-SAT: place every order once, minimise k-in-n spacing violations."""
from ortools.sat.python import cp_model

from .plant import OPTIONS


def sequence(orders, time_limit=10.0):
    n = len(orders)
    m = cp_model.CpModel()
    x = {(i, p): m.new_bool_var(f"x{i}_{p}") for i in range(n) for p in range(n)}
    for i in range(n):
        m.add_exactly_one(x[i, p] for p in range(n))
    for p in range(n):
        m.add_exactly_one(x[i, p] for i in range(n))

    slack = []
    for opt, (_, k, win) in OPTIONS.items():
        holders = [i for i, o in enumerate(orders) if opt in o.options]
        at = [sum(x[i, p] for i in holders) for p in range(n)]
        for s in range(n - win + 1):
            v = m.new_int_var(0, win, f"v_{opt}_{s}")
            m.add(sum(at[s:s + win]) <= k + v)
            slack.append(v)
    m.minimize(sum(slack))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    status = solver.solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"no sequence found: {solver.status_name(status)}")
    seq = sorted(range(n), key=lambda i: next(p for p in range(n) if solver.value(x[i, p])))
    out = [orders[i] for i in seq]
    return out, violations(out)  # recount: v vars may carry slack in non-optimal solutions


def violations(seq):
    count = 0
    for opt, (_, k, win) in OPTIONS.items():
        flags = [opt in o.options for o in seq]
        count += sum(max(0, sum(flags[s:s + win]) - k) for s in range(len(seq) - win + 1))
    return count
