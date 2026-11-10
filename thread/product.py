"""Synthetic product rules (the PMD stage): model types, markets, option families, availability and requires/excludes rules."""
from copy import deepcopy

MODELS = {"S1": "sedan", "C1": "coupe", "W1": "wagon"}
MARKETS = ("EU", "US", "CN")
FAMILIES = {
    "powertrain": {"P1": "petrol", "P2": "hybrid", "P3": "electric"},
    "roof": {"R1": "standard roof", "R2": "panoramic sunroof", "R3": "carbon roof"},
    "trim": {"T1": "base trim", "T2": "sport trim", "T3": "premium trim"},
    "wheels": {"W19": "19 inch", "W20": "20 inch", "W21": "21 inch"},
    "seats": {"S1": "standard seats", "S2": "sport seats", "S3": "comfort seats"},
    "assist": {"A0": "no assistance pack", "A1": "driver assistance pack"},
}

BASE = {
    "version": "MY27",
    "families": FAMILIES,
    # option -> models / markets where it may be ordered (missing = everywhere)
    "models": {"R3": ["S1", "C1"]},
    "markets": {"P1": ["EU", "US"]},
    # (option, required option set: at least one), (option, excluded option)
    "requires": [("R3", ["T2"]), ("S2", ["T2", "T3"]), ("W21", ["T2", "T3"])],
    "excludes": [("P3", "W21"), ("W1:model", "W21")],
    # option that every car in a market must carry
    "mandatory": {"US": ["A1"]},
    # take rates per family (synthetic), market -> option -> share
    "take": {
        "EU": {"P1": .35, "P2": .35, "P3": .30, "R1": .55, "R2": .35, "R3": .10, "T1": .40, "T2": .35, "T3": .25,
               "W19": .45, "W20": .40, "W21": .15, "S1": .45, "S2": .30, "S3": .25, "A0": .50, "A1": .50},
        "US": {"P1": .40, "P2": .30, "P3": .30, "R1": .40, "R2": .45, "R3": .15, "T1": .30, "T2": .35, "T3": .35,
               "W19": .30, "W20": .45, "W21": .25, "S1": .35, "S2": .30, "S3": .35, "A0": .0, "A1": 1.0},
        "CN": {"P1": .0, "P2": .40, "P3": .60, "R1": .30, "R2": .60, "R3": .10, "T1": .30, "T2": .25, "T3": .45,
               "W19": .40, "W20": .45, "W21": .15, "S1": .30, "S2": .20, "S3": .50, "A0": .30, "A1": .70},
    },
}


def scenario(name):
    """The base product plus one change, the kind a model-year update or a supplier brings overnight."""
    p = deepcopy(BASE)
    if name == "base":
        return p
    if name == "carbon_roof_on_wagon":
        p["version"] = "MY27.1 carbon roof released for wagon"
        p["models"]["R3"] = ["S1", "C1", "W1"]
    elif name == "new_highway_pilot":
        p["version"] = "MY27.1 highway pilot A2 launched (electric only, EU+US)"
        p["families"] = {**p["families"], "assist": {**p["families"]["assist"], "A2": "highway pilot"}}
        p["markets"]["A2"] = ["EU", "US"]
        p["requires"].append(("A2", ["P3"]))
        for m, share in (("EU", .15), ("US", .20)):
            p["take"][m]["A2"] = share
            p["take"][m]["A1"] -= share
        p["take"]["CN"]["A2"] = 0.0
        p["mandatory"]["US"] = ["A1", "A2"]  # US cars must carry one of these
    elif name == "sport_seats_need_sport_trim":
        p["version"] = "MY27.1 sport seats now only with sport trim"
        p["requires"] = [r for r in p["requires"] if r[0] != "S2"] + [("S2", ["T2"])]
    else:
        raise KeyError(name)
    return p


SCENARIOS = ("carbon_roof_on_wagon", "new_highway_pilot", "sport_seats_need_sport_trim")
