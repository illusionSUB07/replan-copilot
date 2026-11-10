"""python -m thread.export web/thread.json [--brief]: every scenario's before/after chain and impact as one JSON for web/thread.html."""
import json
import sys
from collections import Counter

from .impact import analyse
from .plan import DAILY_CAP, DAYS, SPACING, VOLUME, WEEKLY_CAP, options_of
from .product import MODELS, SCENARIOS, scenario

WATCH = ("P3", "R3", "R2", "A2")  # options the line cares about, coloured in the sequence strips


def stage(product, r):
    groups = Counter(o.split("|")[0] + "-" + o.split("|")[1] for o in r["orders"])
    return {
        "configs_used": len(r["mix"]),
        "cars_by_group": dict(groups),
        "option_counts": dict(Counter(opt for o in r["orders"] for opt in options_of(o))),
        "targets": {f"{mm}-{k}": {o: round(product["take"][k].get(o, 0) * v) for fam in product["families"].values() for o in fam}
                    for (mm, k), v in VOLUME.items()},
        "days": [[o for o in r["sequence"][d]] for d in range(DAYS)],
    }


def rule_text(p):
    lines = [f"{o} only on {', '.join(m)}" for o, m in p["models"].items()]
    lines += [f"{o} only in {', '.join(m)}" for o, m in p["markets"].items()]
    lines += [f"{o} requires {' or '.join(n)}" for o, n in p["requires"]]
    lines += [f"{a.replace(':model', '')} excludes {b}" for a, b in p["excludes"]]
    lines += [f"{k} cars must carry {' or '.join(v)}" for k, v in p["mandatory"].items()]
    return lines


def export(brief=False):
    base = scenario("base")
    out = {"models": MODELS, "families": base["families"], "base_rules": rule_text(base), "watch": WATCH,
           "spacing": SPACING, "weekly_cap": WEEKLY_CAP, "daily_cap": DAILY_CAP, "scenarios": []}
    for name in SCENARIOS:
        imp, before, after = analyse(name)
        p = scenario(name)
        rules_b, rules_a = set(rule_text(base)), set(rule_text(p))
        sc = {"name": name, "change": p["version"], "rules_added": sorted(rules_a - rules_b), "rules_removed": sorted(rules_b - rules_a),
              "new_options": sorted(set(o for f in p["families"].values() for o in f) - set(o for f in base["families"].values() for o in f)),
              "impact": imp, "before": stage(base, before), "after": stage(p, after),
              "replaced": sorted(set(before["orders"]) - set(after["orders"])), "added": sorted(set(after["orders"]) - set(before["orders"]))}
        if brief:
            from .brief import briefing
            sc["briefing"] = briefing(sc)
        out["scenarios"].append(sc)
    return out


if __name__ == "__main__":
    data = export("--brief" in sys.argv)
    with open(sys.argv[1], "w") as f:
        json.dump(data, f)
    print(f"wrote {sys.argv[1]}: {len(data['scenarios'])} scenarios")
