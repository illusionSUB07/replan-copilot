import json

import pytest

pytest.importorskip("pxr")
from pxr import Usd, UsdGeom  # noqa: E402

from omniverse.build_stage import BODY_X, BUFFER_X, BUFFER_Y, PAINT_Y, build, slot_xy  # noqa: E402

REPLAY = "web/replay.json"


@pytest.fixture(scope="module")
def stage(tmp_path_factory):
    out = tmp_path_factory.mktemp("usd") / "plant.usda"
    build(REPLAY, out)
    return Usd.Stage.Open(str(out))


def test_scene_has_lights(stage):
    from pxr import UsdLux
    assert UsdLux.DomeLight(stage.GetPrimAtPath("/World/Lights/Dome"))
    assert UsdLux.DistantLight(stage.GetPrimAtPath("/World/Lights/Sun"))


def test_cars_ghosts_and_cameras(stage):
    assert stage and UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    assert len(stage.GetPrimAtPath("/World/Cars").GetChildren()) == 120
    assert len(stage.GetPrimAtPath("/World/Ghosts").GetChildren()) == 120
    assert len(stage.GetPrimAtPath("/World/AssemblyLine/Slots").GetChildren()) == 120
    for name in ("body_to_paint", "paint_to_assembly", "end_of_line"):
        assert UsdGeom.Camera(stage.GetPrimAtPath(f"/World/Cameras/{name}"))
    for name in ("body_in", "paint_in", "assembly_in", "finished"):
        assert stage.GetPrimAtPath(f"/World/Gates/{name}")


def test_cars_follow_the_flow_and_carried_over_stay_in_buffer(stage):
    outcome = json.load(open(REPLAY))["outcome"]
    carried = 0
    for car in stage.GetPrimAtPath("/World/Cars").GetChildren():
        t = car.GetAttribute("xformOp:translate")
        times = t.GetTimeSamples()
        pts = [t.Get(tc) for tc in times]
        info = car.GetCustomData()
        assert len(times) >= 5 and times == sorted(times)
        assert pts[0][0] == BODY_X[0] and pts[2][1] == PAINT_Y[info["paint_line"]]
        assert outcome[info["order_id"]]["plan_pos"] == info["plan_pos"]
        end = t.Get(stage.GetEndTimeCode())
        if info["carried_over"]:
            carried += 1
            assert BUFFER_X[0] <= end[0] <= BUFFER_X[1] and BUFFER_Y[0] <= end[1] <= BUFFER_Y[1]
        else:
            assert tuple(t.Get(info["assembly_in"]))[:2] == slot_xy(info["actual_pos"])
    assert carried == sum(c["assembly_in"] is None for c in outcome.values()) > 0
