"""python -m copilot [--seed N] [--scenario calm|bad_day] [--agent]"""
import argparse
import json

from .plant import clock, daily_package
from .replan import day_checks, run_day
from .scenarios import SCENARIOS
from .schedule import plan
from .solver import sequence

DAY = 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scenario", choices=SCENARIOS, default="bad_day")
    ap.add_argument("--agent", action="store_true", help="also run the Claude copilot (calls Bedrock)")
    args = ap.parse_args()

    seq, viol = sequence(daily_package(DAY, seed=args.seed))
    rows = plan(seq, DAY)
    disruptions = SCENARIOS[args.scenario](rows)
    checks = day_checks(DAY)
    print(f"plan: {len(seq)} cars, {viol} spacing violations, assembly {clock(rows[0]['assembly_in'])}-{clock(rows[-1]['assembly_in'])}")
    print(f"checks: {', '.join(clock(c) for c in checks)}\n")

    policies = {"never replan": lambda now, r: False, "always replan": lambda now, r: True}
    if args.agent:
        from .agent import make_policy
        policies["claude copilot"] = make_policy(disruptions)

    results = {}
    for name, policy in policies.items():
        results[name], log = run_day(rows, disruptions, policy, checks)
        if log:
            print(f"{name} released at: " + ", ".join(f"{clock(t)} ({n}+{e} emergency)" for t, n, e in log))

    print(f"\n{'policy':<16}{'total €':>9}{'out-of-seq':>12}{'carried':>9}{'call-offs':>11}{'emergency':>11}")
    for name, c in results.items():
        print(f"{name:<16}{c['total_eur']:>9}{c['out_of_sequence']:>12}{c['carried_over']:>9}"
              f"{c['call_off_changes']:>11}{c['emergency_changes']:>11}")
    if not args.agent:
        print("\n(add --agent to let Claude decide)")


if __name__ == "__main__":
    main()
