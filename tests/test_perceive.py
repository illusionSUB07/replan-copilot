import json

import pytest

pytest.importorskip("pxr")
from pxr import Usd  # noqa: E402

from omniverse.build_stage import build  # noqa: E402
from omniverse.perceive import COLOURS, ground_truth, parse  # noqa: E402

REPLAY = "web/replay.json"


@pytest.fixture(scope="module")
def stage(tmp_path_factory):
    out = tmp_path_factory.mktemp("usd") / "plant.usda"
    build(REPLAY, out)
    return Usd.Stage.Open(str(out))


@pytest.mark.parametrize("t", [878, 1478, 2078])
def test_buffer_truth_matches_replay(stage, t):
    outcome = json.load(open(REPLAY))["outcome"].values()
    end = lambda c: c["assembly_in"] if c["assembly_in"] is not None else float("inf")
    parked = sum(c["ready"] + 1 <= t <= end(c) - 1 for c in outcome)  # sure to sit in the buffer
    nearby = sum(c["ready"] < t < end(c) for c in outcome)  # also counts cars in transit
    truth = ground_truth(stage, t, "overview")  # the overview frames the whole buffer
    assert parked <= truth["total"] <= nearby
    assert truth["total"] == sum(truth[c] for c in COLOURS)
    assert ground_truth(stage, t, "paint_to_assembly")["total"] <= truth["total"]  # closer camera crops the near corner


def test_nothing_visible_before_the_day_starts(stage):
    assert ground_truth(stage, stage.GetStartTimeCode(), "body_to_paint")["total"] == 0


def test_parse_reply():
    got = parse('{"red": 3, "blue": 7, "yellow": 2, "green": 3, "white": 2, "notes": "one car behind a column"}')
    assert got["total"] == 17 and got["blue"] == 7 and got["notes"]
    for bad in ('{"red": -1, "blue": 0, "yellow": 0, "green": 0, "white": 0}', '{"red": 1}',
                '{"red": 1.5, "blue": 0, "yellow": 0, "green": 0, "white": 0}',
                '{"red": 1, "blue": 0, "yellow": 0, "green": 0, "white": 0, "purple": 2}', "[]", "three cars"):
        with pytest.raises(ValueError):
            parse(bad)
