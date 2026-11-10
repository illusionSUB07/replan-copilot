"""Configuration generator: every buildable configuration per model type and market, weighted by take rates."""
from itertools import product as cartesian

from .product import MODELS


def buildable(product, model, market, cfg):
    """None if the configuration is valid, else the first rule it breaks (as text, for explanations)."""
    opts = set(cfg)
    for o in cfg:
        if model not in product["models"].get(o, [model]):
            return f"{o} not offered on {model}"
        if market not in product["markets"].get(o, [market]):
            return f"{o} not offered in {market}"
    for o, need in product["requires"]:
        if o in opts and not opts & set(need):
            return f"{o} requires {' or '.join(need)}"
    for a, b in product["excludes"]:
        a_on = a == f"{model}:model" or a in opts
        if a_on and b in opts:
            return f"{a.replace(':model', '')} excludes {b}"
    must = product["mandatory"].get(market)
    if must and not opts & set(must):
        return f"{market} requires {' or '.join(must)}"
    return None


def generate(product):
    """{(model, market): [(config tuple, weight)]}: all rule-valid configs, weights = take-rate product, normalised."""
    pools = {}
    for model, market in cartesian(MODELS, product["take"]):
        take = product["take"][market]
        rows = []
        for cfg in cartesian(*(fam.keys() for fam in product["families"].values())):
            w = 1.0
            for o in cfg:
                w *= take.get(o, 0.0)
            if w > 0 and buildable(product, model, market, cfg) is None:
                rows.append((cfg, w))
        total = sum(w for _, w in rows)
        pools[(model, market)] = [(c, w / total) for c, w in rows]
    return pools
