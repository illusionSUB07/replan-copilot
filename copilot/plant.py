"""Synthetic plant: body shop -> two paint lines -> assembly; times in working minutes (960 per day, from 06:00)."""
import random
from dataclasses import dataclass

SHIFT_START, SHIFT_LEN = 6 * 60, 16 * 60
TAKT = 8                    # assembly takt -> 120 cars per day
BODY_LEAD = 240             # body_in -> paint_in
PAINT_LEAD = 300            # paint_in -> ready for assembly
TWO_TONE_EXTRA = 90         # second paint pass
BUFFER = 60                 # planned slack before the assembly slot
ASSEMBLY_LEAD = 480         # assembly_in -> finished

# option: (share of orders, at most k cars in any window of n)
OPTIONS = {
    "sunroof": (0.30, 1, 3),
    "two_tone": (0.15, 1, 5),
    "ev": (0.40, 2, 3),
    "sport_seats": (0.25, 1, 2),
}


@dataclass(frozen=True)
class Order:
    id: str
    options: frozenset

    def paint_lead(self):
        return PAINT_LEAD + (TWO_TONE_EXTRA if "two_tone" in self.options else 0)

    def paint_line(self, idx):
        # two-tone only runs on P2; everything else alternates
        return "P2" if "two_tone" in self.options else ("P1" if idx % 2 == 0 else "P2")


def daily_package(day, n=120, seed=0):
    rng = random.Random(f"{seed}-{day}")
    return [
        Order(f"D{day}-{i:03d}", frozenset(o for o, (share, _, _) in OPTIONS.items() if rng.random() < share))
        for i in range(n)
    ]


def clock(w):
    day, m = divmod(int(w), SHIFT_LEN)
    m += SHIFT_START
    return f"D{day} {m // 60:02d}:{m % 60:02d}"
