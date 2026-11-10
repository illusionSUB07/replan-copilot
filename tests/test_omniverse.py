import json

import pytest

pytest.importorskip("pxr")
from pxr import Usd, UsdGeom  # noqa: E402

from omniverse.build_stage import BUFFER_X, build  # noqa: E402

REPLAY = "web/replay.json"


@pytest.fixture(scope="module")
def stage(tmp_path_factory):
    out = tmp_path_factory.mktemp("usd") / "plant.usda"
    build(REPLAY, out)
    return Usd.Stage.Open(str(out))


def test_cars_ghosts_and_cameras(stage):
    assert stage and UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert len(stage.GetPrimAtPath("/World/Cars").GetChildren()) == 120
    assert len(stage.GetPrimAtPath("/World/Ghosts").GetChildren()) == 120
    assert len(stage.GetPrimAtPath("/World/AssemblyLine/Slots").GetChildren()) == 120
    for name in ("body_to_paint", "paint_to_assembly", "end_of_line"):
        assert UsdGeom.Camera(stage.GetPrimAtPath(f"/World/Cameras/{name}"))
    for name in ("body_in", "paint_in", "assembly_in", "finished"):
        assert stage.GetPrimAtPath(f"/World/Gates/{name}")


def test_cars_move_forward_and_carried_over_stay_in_buffer(stage):
    outcome = json.load(open(REPLAY))["outcome"]
    carried = 0
    for car in stage.GetPrimAtPath("/World/Cars").GetChildren():
        t = car.GetAttribute("xformOp:translate")
        times = t.GetTimeSamples()
        xs = [t.Get(tc)[0] for tc in times]
        assert len(times) >= 6 and times == sorted(times) and xs == sorted(xs)
        info = car.GetCustomData()
        assert outcome[info["order_id"]]["plan_pos"] == info["plan_pos"]
        if info["carried_over"]:
            carried += 1
            assert BUFFER_X[0] <= t.Get(stage.GetEndTimeCode())[0] <= BUFFER_X[1]
    assert carried == sum(c["assembly_in"] is None for c in outcome.values()) > 0
