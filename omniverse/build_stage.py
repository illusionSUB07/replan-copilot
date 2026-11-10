"""python -m omniverse.build_stage replay.json plant.usda: USD scene of the plant animated from a replay (Z-up, meters, time = working minute)."""
import json
import sys
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom

CAR = (4.5, 1.9, 1.3)
PITCH = 6.0                                   # slot / buffer spot spacing
BODY_X, PAINT_X, BUFFER_X, LINE_X = (0, 80), (100, 180), (200, 380), (400, 1120)
PAINT_Y = {"P1": 10.0, "P2": -10.0}
BUFFER_TRACKS, BUFFER_SPOTS = 4, 30
DONE_Y = -6.0                                 # finished lane beside the line
GATES = {"body_in": BODY_X[0] - 2, "paint_in": 90, "assembly_in": 390, "finished": LINE_X[1] + 4}
PALETTE = {"two_tone": (0.85, 0.2, 0.2), "ev": (0.2, 0.55, 0.9), "sunroof": (0.95, 0.75, 0.2),
           "sport_seats": (0.3, 0.75, 0.35), "none": (0.85, 0.85, 0.85)}
PLAY_SECONDS = 120


def box(stage, path, center, size, color, opacity=1.0):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if opacity < 1:
        cube.CreateDisplayOpacityAttr([opacity])
    xf = UsdGeom.Xformable(cube)
    t = xf.AddTranslateOp()
    t.Set(Gf.Vec3d(*center))
    xf.AddScaleOp().Set(Gf.Vec3f(*size))
    return cube, t


def area(stage, path, xs, y, width, color):
    return box(stage, path, ((xs[0] + xs[1]) / 2, y, -0.05), (xs[1] - xs[0], width, 0.1), color)


def slot_xy(k):
    return LINE_X[0] + 3 + k * PITCH, 0.0


def buffer_xy(k):
    return BUFFER_X[0] + 3 + (k % BUFFER_SPOTS) * PITCH, (k // BUFFER_SPOTS % BUFFER_TRACKS - 1.5) * 3.0


def keys(c, end):
    # (time, (x, y)) through body hall, paint booth, buffer, assembly slot, finished lane
    ly, buf = PAINT_Y[c["paint_line"]], buffer_xy(c["plan_pos"])
    k = [(c["body_in"], (BODY_X[0], 0.0)), (c["paint_in"], (BODY_X[1], 0.0)),
         (c["paint_in"] + 1, (PAINT_X[0], ly)), (c["ready"], (PAINT_X[1], ly)), (c["ready"] + 1, buf)]
    if c["assembly_in"] is None:
        return k + [(end, buf)]
    slot = slot_xy(c["actual_pos"])
    k += [(c["assembly_in"] - 1, buf), (c["assembly_in"], slot), (c["finished"], slot), (c["finished"] + 1, (slot[0], DONE_Y))]
    out = []
    for t, xy in k:  # keep times strictly increasing when stops have no dwell
        out.append((max(t, out[-1][0] + 0.01) if out else t, xy))
    return out


def build(replay, out):
    d = json.loads(Path(replay).read_text())
    cars, opts = d["outcome"], {p["id"]: p["options"] for p in d["plan"]}
    start = min(c["body_in"] for c in cars.values())
    end = max([d["plant"]["day_end"]] + [c["finished"] for c in cars.values() if c["finished"] is not None]) + 2

    stage = Usd.Stage.CreateNew(str(out))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    stage.SetStartTimeCode(start)
    stage.SetEndTimeCode(end)
    stage.SetTimeCodesPerSecond((end - start) / PLAY_SECONDS)
    stage.SetFramesPerSecond(24)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    stage.GetRootLayer().customLayerData = {"seed": d["seed"], "scenario": d["scenario"], "policy": d["policy"]}

    area(stage, "/World/BodyShop/Floor", BODY_X, 0, 12, (0.55, 0.55, 0.6))
    for line, y in PAINT_Y.items():
        area(stage, f"/World/Paint/{line}/Floor", PAINT_X, y, 6, (0.5, 0.5, 0.65))
        box(stage, f"/World/Paint/{line}/Booth", ((PAINT_X[0] + PAINT_X[1]) / 2, y, 2), (PAINT_X[1] - PAINT_X[0], 5, 4), (0.7, 0.7, 0.9), 0.15)
    area(stage, "/World/Buffer/Floor", BUFFER_X, 0, 12, (0.6, 0.55, 0.45))
    area(stage, "/World/AssemblyLine/Floor", LINE_X, 0, 4, (0.35, 0.35, 0.35))
    area(stage, "/World/AssemblyLine/FinishedLane", LINE_X, DONE_Y, 3, (0.4, 0.5, 0.4))
    for k in range(len(cars)):
        x, y = slot_xy(k)
        box(stage, f"/World/AssemblyLine/Slots/slot_{k:03d}", (x - PITCH / 2, y, 0.01), (0.15, 4, 0.02), (1, 1, 1))
    for name, x in GATES.items():
        g = UsdGeom.Xform.Define(stage, f"/World/Gates/{name}")
        g.AddTranslateOp().Set(Gf.Vec3d(x, 0, 0))
        g.GetPrim().SetCustomData({"checkpoint": name})
        for post, y in (("PostL", -16), ("PostR", 16)):
            box(stage, f"/World/Gates/{name}/{post}", (0, y, 3), (0.4, 0.4, 6), (0.95, 0.5, 0.1))
        box(stage, f"/World/Gates/{name}/Beam", (0, 0, 6), (0.4, 32.4, 0.4), (0.95, 0.5, 0.1))

    # cameras look along local -Z; rotate X by 80 (slight tilt down) then Z to face along the flow
    for name, pos, yaw in (("body_to_paint", (GATES["paint_in"] - 6, 0, 5), -90),
                           ("paint_to_assembly", (GATES["assembly_in"] - 6, 0, 5), -90),
                           ("end_of_line", (GATES["finished"] + 12, 0, 5), 90)):
        cam = UsdGeom.Camera.Define(stage, f"/World/Cameras/{name}")
        cam.AddTranslateOp().Set(Gf.Vec3d(*pos))
        cam.AddRotateXYZOp().Set(Gf.Vec3f(80, 0, yaw))
        cam.CreateFocalLengthAttr(18)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 2000))

    z = CAR[2] / 2
    for oid, c in cars.items():
        name = oid.replace("-", "_")
        color = PALETTE[next((o for o in PALETTE if o in opts[oid]), "none")]
        car, t = box(stage, f"/World/Cars/{name}", (0, 0, z), CAR, color)
        for tc, (x, y) in keys(c, end):
            t.Set(Gf.Vec3d(x, y, z), tc)
        vis = car.CreateVisibilityAttr()
        vis.Set(UsdGeom.Tokens.invisible, start)
        vis.Set(UsdGeom.Tokens.inherited, c["body_in"])
        info = {"order_id": oid, "options": ",".join(opts[oid]), "plan_pos": c["plan_pos"], "plan_time": c["plan_time"],
                "out_of_sequence": c["out_of_sequence"], "carried_over": c["assembly_in"] is None, "paint_line": c["paint_line"]}
        if c["assembly_in"] is not None:
            info.update(actual_pos=c["actual_pos"], assembly_in=c["assembly_in"], finished=c["finished"])
        car.GetPrim().SetCustomData(info)

        x, y = slot_xy(c["plan_pos"])
        ghost, _ = box(stage, f"/World/Ghosts/{name}", (x, y, z), CAR, color, 0.25)
        gvis = ghost.CreateVisibilityAttr()
        gvis.Set(UsdGeom.Tokens.invisible, start)
        gvis.Set(UsdGeom.Tokens.inherited, c["plan_time"])
        ghost.GetPrim().SetCustomData({"order_id": oid, "plan_pos": c["plan_pos"], "plan_time": c["plan_time"]})
    stage.GetRootLayer().Save()
    return stage


if __name__ == "__main__":
    Path(sys.argv[2]).parent.mkdir(parents=True, exist_ok=True)
    build(sys.argv[1], sys.argv[2])
    print(f"wrote {sys.argv[2]}")
