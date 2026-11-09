"""Disruption scenarios; each takes the planned rows so they hit the same positions whatever the solver picks."""
from .plant import SHIFT_LEN


def calm(rows):
    return []


def bad_day(rows):
    d = (rows[0]["assembly_in"] // SHIFT_LEN) * SHIFT_LEN
    repaint = lambda pos: {"type": "repaint", "order": rows[pos]["order"].id,
                           "known_at": rows[pos]["paint_in"] + rows[pos]["order"].paint_lead()}
    return [
        {"type": "paint_stop", "line": "P2", "start": d - 400, "end": d - 310, "known_at": d - 400},
        repaint(10),
        repaint(50),
        repaint(90),
        # supplier first estimates 3h, later revises to 5h
        {"type": "supplier_late", "option": "sport_seats", "until": d + 180, "known_at": d - 60},
        {"type": "supplier_late", "option": "sport_seats", "until": d + 300, "known_at": d + 120},
        {"type": "assembly_stop", "start": d + 420, "end": d + 465, "known_at": d + 420},
    ]


SCENARIOS = {"calm": calm, "bad_day": bad_day}
