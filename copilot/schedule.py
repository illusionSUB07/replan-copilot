"""Backward scheduling: from each assembly slot back to paint and body checkpoints."""
from .plant import ASSEMBLY_LEAD, BODY_LEAD, BUFFER, SHIFT_LEN, TAKT


def plan(seq, day):
    start = day * SHIFT_LEN
    rows = []
    for pos, o in enumerate(seq):
        assembly_in = start + pos * TAKT
        paint_in = assembly_in - BUFFER - o.paint_lead()
        rows.append({
            "pos": pos,
            "order": o,
            "paint_line": o.paint_line(pos),
            "body_in": paint_in - BODY_LEAD,
            "paint_in": paint_in,
            "assembly_in": assembly_in,
            "finished": assembly_in + ASSEMBLY_LEAD,
        })
    return rows
