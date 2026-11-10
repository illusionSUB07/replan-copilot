"""What one product change does to every stage of the chain, measured against the plan before it."""
from bisect import bisect_left
from collections import Counter

from .congen import buildable, generate
from .plan import mix_gap, run
from .product import scenario


def lis(seq):
    tails = []
    for x in seq:
        i = bisect_left(tails, x)
        tails[i:i + 1] = [x]
    return len(tails)


def impact(before_product, before, after_product, after, pools_before, pools_after):
    cfg_b = {(mm, k, c) for (mm, k), rows in pools_before.items() for c, _ in rows}
    cfg_a = {(mm, k, c) for (mm, k), rows in pools_after.items() for c, _ in rows}
    gone = [key for key in before["mix"] if key not in cfg_a]
    why = Counter(buildable(after_product, key[0], key[1], key[2]) for key in gone)
    ids_b, ids_a = set(before["orders"]), set(after["orders"])
    kept = ids_b & ids_a
    moved_day = sum(before["days"][o] != after["days"][o] for o in kept)
    resequenced = 0
    for d, seq in after["sequence"].items():  # cars that kept their day but lost their place in the line order
        pos_b = {o: i for i, o in enumerate(before["sequence"][d])}
        same = [pos_b[o] for o in seq if o in pos_b]
        resequenced += len(same) - lis(same)
    return {
        "change": after_product["version"],
        "configs": {"buildable_before": len(cfg_b), "buildable_after": len(cfg_a),
                    "added": len(cfg_a - cfg_b), "removed": len(cfg_b - cfg_a)},
        "invalid_plan_configs": {"count": len(gone), "cars": sum(before["mix"][k] for k in gone),
                                 "because": {str(r): n for r, n in why.items()}},
        "mix": {"gap_before": mix_gap(before_product, before["mix"]), "gap_after": mix_gap(after_product, after["mix"]),
                "configs_used_before": len(before["mix"]), "configs_used_after": len(after["mix"])},
        "orders": {"replaced": len(ids_b - ids_a), "kept": len(kept)},
        "slots": {"kept_cars_moved_day": moved_day},
        "sequence": {"kept_cars_resequenced": resequenced},
        # every car whose content, day or line position changed means a new supplier call-off
        "call_off_changes": len(ids_b - ids_a) + moved_day + resequenced,
    }


def analyse(name):
    p0, p1 = scenario("base"), scenario(name)
    pools0, pools1 = generate(p0), generate(p1)
    before = run(p0, pools0)
    after = run(p1, pools1, previous=before)
    return impact(p0, before, p1, after, pools0, pools1), before, after
