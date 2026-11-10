"""Disruption scenarios; each takes the planned rows so they hit the same positions whatever the solver picks."""
import random

from .plant import OPTIONS, SHIFT_LEN


def calm(rows, seed=0):
    return []


def bad_day(rows, seed=0):
    rng = random.Random(seed)
    d = (rows[0]["assembly_in"] // SHIFT_LEN) * SHIFT_LEN
    repaint = lambda pos: {"type": "repaint", "order": rows[pos]["order"].id,
                           "known_at": rows[pos]["paint_in"] + rows[pos]["order"].paint_lead()}
    option = rng.choice([o for o in OPTIONS if o != "two_tone"])
    estimate = d + rng.choice([120, 180, 240])
    out = [
        {"type": "paint_stop", "line": rng.choice(["P1", "P2"]), "start": d - 400, "end": d - 310, "known_at": d - 400},
        *(repaint(p) for p in sorted(rng.sample(range(5, len(rows) - 5), 3))),
        {"type": "supplier_late", "option": option, "until": estimate, "known_at": d - 60},
        {"type": "assembly_stop", "start": d + 420, "end": d + 465, "known_at": d + 420},
    ]
    if rng.random() < 0.5:  # half the time the supplier later revises the estimate upward
        out.append({"type": "supplier_late", "option": option, "until": estimate + rng.choice([60, 120, 180]),
                    "known_at": estimate - 60})
    return out


SCENARIOS = {"calm": calm, "bad_day": bad_day}
