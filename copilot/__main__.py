"""python -m copilot [--seeds N] [--scenario calm|bad_day] [--agent]"""
import argparse
import json
from pathlib import Path

from .plant import clock, daily_package
from .replan import day_checks, expected_rule, greedy_rule, robust_rule, run_day
from .scenarios import SCENARIOS
from .schedule import plan
from .solver import sequence

DAY = 1
CACHE = Path(".cache")


def cached_sequence(seed):
    # parallel CP-SAT is not reproducible, so each seed's sequence is solved once and reused
    orders = daily_package(DAY, seed=seed)
    f = CACHE / f"seq_{seed}.json"
    if f.exists():
        by_id = {o.id: o for o in orders}
        return [by_id[i] for i in json.loads(f.read_text())]
    seq, _ = sequence(orders)
    CACHE.mkdir(exist_ok=True)
    f.write_text(json.dumps([o.id for o in seq]))
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=1, help="number of seeds")
    ap.add_argument("--first", type=int, default=0, help="first seed, to resume an interrupted run")
    ap.add_argument("--scenario", choices=SCENARIOS, default="bad_day")
    ap.add_argument("--agent", action="store_true", help="also run the Claude copilot (calls Bedrock)")
    args = ap.parse_args()

    totals = {}
    checks = day_checks(DAY)
    for seed in range(args.first, args.first + args.seeds):
        rows = plan(cached_sequence(seed), DAY)
        disruptions = SCENARIOS[args.scenario](rows, seed)
        policies = {
            "never replan": lambda now, r: False,
            "always replan": lambda now, r: True,
            "greedy rule": greedy_rule(disruptions),
            "robust rule": robust_rule(disruptions),
            "expected rule": expected_rule(disruptions),
        }
        if args.agent:
            from .agent import make_policy
            print(f"\n--- seed {seed}: claude copilot ---")
            policies["claude copilot"] = make_policy(disruptions)

        print(f"\nseed {seed}:")
        for name, policy in policies.items():
            c, log = run_day(rows, disruptions, policy, checks)
            totals.setdefault(name, []).append(c["total_eur"])
            releases = ", ".join(clock(t) for t, _, _ in log) or "-"
            print(f"  {name:<15}{c['total_eur']:>8} €   out-of-seq {c['out_of_sequence']:>2}  carried {c['carried_over']:>2}"
                  f"  call-offs {c['call_off_changes']:>2}+{c['emergency_changes']:>2} emergency   releases: {releases}")

    print(f"\nmean over {args.seeds} seed(s):")
    for name, t in sorted(totals.items(), key=lambda kv: sum(kv[1])):
        print(f"  {name:<15}{sum(t) / len(t):>9.0f} €")


if __name__ == "__main__":
    main()
