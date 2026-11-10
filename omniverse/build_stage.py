"""python -m omniverse.build_stage replay.json plant.usda: USD scene of the plant animated from a replay (Z-up, meters, time = working minute)."""
import json
import sys
from pathlib import Path

from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdShade

HALL_X, HALL_Y = (-10, 270), (-75, 75)
BODY_X, BODY_Y = (10, 70), 55
PAINT_X, PAINT_Y = (85, 145), {"P1": 62.0, "P2": 48.0}
BUFFER_X, BUFFER_Y = (160, 250), (41, 64)
BUFFER_SPOTS, BUFFER_PITCH = 20, 4.5
LINE_X0, SLOTS_PER_ROW, PITCH, ROW_Y = 40, 30, 6.0, (20, 5, -10, -25)
YARD_X0, YARD_PER_ROW, YARD_Y = 40, 40, (-45, -50, -55)
GATES = {"body_in": (BODY_X[0] - 4, BODY_Y), "paint_in": (PAINT_X[0] - 6, 55), "assembly_in": (LINE_X0 - 6, ROW_Y[0]),
         "finished": (LINE_X0 - 6, ROW_Y[-1])}
PAINT = {"two_tone": (0.55, 0.04, 0.06), "ev": (0.04, 0.22, 0.6), "sunroof": (0.85, 0.58, 0.08),
         "sport_seats": (0.08, 0.42, 0.22), "none": (0.72, 0.74, 0.77)}
PLAY_SECONDS = 120


def material(stage, name, color, rough=0.5, metal=0.0, opacity=1.0):
    mat = UsdShade.Material.Define(stage, f"/World/Looks/{name}")
    sh = UsdShade.Shader.Define(stage, f"/World/Looks/{name}/Shader")
    sh.CreateIdAttr("UsdPreviewSurface")
    sh.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(rough)
    sh.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metal)
    sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), "surface")
    return mat


def bind(prim, mat):
    UsdShade.MaterialBindingAPI.Apply(prim.GetPrim()).Bind(mat)


def box(stage, path, center, size, mat):
    cube = UsdGeom.Cube.Define(stage, path)
    cube.CreateSizeAttr(1.0)
    xf = UsdGeom.Xformable(cube)
    xf.AddTranslateOp().Set(Gf.Vec3d(*center))
    xf.AddScaleOp().Set(Gf.Vec3f(*size))
    bind(cube, mat)
    return cube


def car(stage, path, paint, tyre=None):
    # low-poly car: body, cabin and (for real cars) four wheels under one animated Xform
    root = UsdGeom.Xform.Define(stage, path)
    t = root.AddTranslateOp()
    box(stage, f"{path}/Body", (0, 0, 0.6), (4.4, 1.85, 0.6), paint)
    box(stage, f"{path}/Cabin", (-0.2, 0, 1.15), (2.3, 1.6, 0.55), paint)
    for i, (x, y) in enumerate(((1.4, 0.85), (1.4, -0.85), (-1.4, 0.85), (-1.4, -0.85)) if tyre else ()):
        w = UsdGeom.Cylinder.Define(stage, f"{path}/Wheel{i}")
        w.CreateRadiusAttr(0.34)
        w.CreateHeightAttr(0.26)
        w.CreateAxisAttr("Y")
        UsdGeom.Xformable(w).AddTranslateOp().Set(Gf.Vec3d(x, y, 0.34))
        bind(w, tyre)
    return root, t


def look_at(stage, path, eye, target, focal):
    cam = UsdGeom.Camera.Define(stage, path)
    cam.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse())
    cam.CreateFocalLengthAttr(focal)
    cam.CreateClippingRangeAttr(Gf.Vec2f(0.1, 3000))
    return cam


def slot_xy(k):
    # serpentine line: even rows run left to right, odd rows back
    row, i = divmod(k, SLOTS_PER_ROW)
    i = i if row % 2 == 0 else SLOTS_PER_ROW - 1 - i
    return LINE_X0 + i * PITCH, ROW_Y[row % len(ROW_Y)]


def buffer_xy(k):
    return BUFFER_X[0] + 3 + (k % BUFFER_SPOTS) * BUFFER_PITCH, BUFFER_Y[0] + (k // BUFFER_SPOTS) * BUFFER_PITCH


def yard_xy(k):
    return YARD_X0 + (k % YARD_PER_ROW) * 4.5, YARD_Y[k // YARD_PER_ROW % len(YARD_Y)]


def keys(c, end):
    # (time, (x, y)) through body shop, paint booth, buffer, assembly slot, finished yard
    ly, buf = PAINT_Y[c["paint_line"]], buffer_xy(c["plan_pos"])
    hop = lambda a, b: min(1.0, (b - a) / 3)  # transit time, shrunk when the next stop is close
    paint_in, ready, asm = c["paint_in"], c["ready"], c["assembly_in"]
    k = [(c["body_in"], (BODY_X[0], BODY_Y)), (paint_in, (BODY_X[1], BODY_Y)),
         (paint_in + hop(paint_in, ready), (PAINT_X[0], ly)),
         # a car built the moment it is ready leaves the booth just before, so it sits in its slot on time
         (ready if asm is None or asm > ready else ready - hop(paint_in, ready), (PAINT_X[1], ly))]
    if asm is None:
        return k + [(ready + hop(ready, end), buf), (end, buf)]
    if asm > ready:  # waits in the buffer only if there is time to wait
        k += [(ready + hop(ready, asm), buf), (asm - hop(ready, asm), buf)]
    slot = slot_xy(c["actual_pos"])
    k += [(asm, slot), (c["finished"], slot), (c["finished"] + 1, yard_xy(c["actual_pos"]))]
    out = []
    for t, xy in k:  # keep times strictly increasing when stops have no dwell
        out.append((max(t, out[-1][0] + 0.01) if out else t, xy))
    return out


def build_hall(stage, looks):
    cx, cy = (HALL_X[0] + HALL_X[1]) / 2, (HALL_Y[0] + HALL_Y[1]) / 2
    w, d = HALL_X[1] - HALL_X[0], HALL_Y[1] - HALL_Y[0]
    box(stage, "/World/Hall/Floor", (cx, cy, -0.1), (w, d, 0.2), looks["concrete"])
    for name, (x, y), (sx, sy) in (("WallN", (cx, HALL_Y[1]), (w, 0.4)), ("WallS", (cx, HALL_Y[0]), (w, 0.4)),
                                   ("WallW", (HALL_X[0], cy), (0.4, d)), ("WallE", (HALL_X[1], cy), (0.4, d))):
        box(stage, f"/World/Hall/{name}", (x, y, 2), (sx, sy, 4), looks["wall"])
    for i, x in enumerate(range(HALL_X[0] + 20, HALL_X[1], 30)):
        for j, y in enumerate((HALL_Y[0] + 1, 34, HALL_Y[1] - 1)):
            box(stage, f"/World/Hall/Columns/c{i}_{j}", (x, y, 6), (0.8, 0.8, 12), looks["steel"])

    def zone(path, xs, ys):
        box(stage, path, ((xs[0] + xs[1]) / 2, (ys[0] + ys[1]) / 2, 0.01), (xs[1] - xs[0], ys[1] - ys[0], 0.02), looks["zone"])

    zone("/World/BodyShop/Floor", (BODY_X[0] - 3, BODY_X[1] + 3), (BODY_Y - 5, BODY_Y + 5))
    zone("/World/Buffer/Floor", (BUFFER_X[0], BUFFER_X[1] + 3), (BUFFER_Y[0] - 3, BUFFER_Y[1] + 3))
    zone("/World/FinishedYard/Floor", (YARD_X0 - 3, YARD_X0 + YARD_PER_ROW * 4.5), (YARD_Y[-1] - 3, YARD_Y[0] + 3))
    for line, y in PAINT_Y.items():
        box(stage, f"/World/Paint/{line}/Floor", ((PAINT_X[0] + PAINT_X[1]) / 2, y, 0.01), (PAINT_X[1] - PAINT_X[0], 6, 0.02), looks["zone"])
        box(stage, f"/World/Paint/{line}/Booth", ((PAINT_X[0] + PAINT_X[1]) / 2, y, 2.5), (PAINT_X[1] - PAINT_X[0], 6, 5), looks["glass"])
    x1 = LINE_X0 + (SLOTS_PER_ROW - 1) * PITCH
    for r, y in enumerate(ROW_Y):
        box(stage, f"/World/AssemblyLine/Row{r}", ((LINE_X0 + x1) / 2, y, 0.05), (x1 - LINE_X0 + PITCH, 4, 0.1), looks["conveyor"])
        for side, tag in ((-2.1, "L"), (2.1, "R")):
            box(stage, f"/World/AssemblyLine/Row{r}Edge{tag}", ((LINE_X0 + x1) / 2, y + side, 0.12), (x1 - LINE_X0 + PITCH, 0.2, 0.04), looks["safety"])


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

    looks = {"concrete": material(stage, "Concrete", (0.32, 0.32, 0.34), 0.9),
             "zone": material(stage, "EpoxyZone", (0.2, 0.24, 0.3), 0.6),
             "wall": material(stage, "Wall", (0.82, 0.83, 0.85), 0.8),
             "steel": material(stage, "Steel", (0.45, 0.47, 0.5), 0.4, 0.8),
             "conveyor": material(stage, "Conveyor", (0.12, 0.12, 0.13), 0.5, 0.3),
             "safety": material(stage, "SafetyYellow", (0.95, 0.75, 0.05), 0.5),
             "glass": material(stage, "BoothGlass", (0.75, 0.85, 0.95), 0.05, 0.0, 0.18),
             "gate": material(stage, "Gate", (0.95, 0.45, 0.08), 0.4),
             "marker": material(stage, "SlotMarker", (0.9, 0.9, 0.9), 0.6),
             "tyre": material(stage, "Tyre", (0.03, 0.03, 0.03), 0.8)}
    paints = {o: material(stage, f"Paint_{o}", c, 0.25, 0.6) for o, c in PAINT.items()}
    ghosts = {o: material(stage, f"Ghost_{o}", c, 0.5, 0.0, 0.25) for o, c in PAINT.items()}

    build_hall(stage, looks)
    for k in range(len(cars)):
        x, y = slot_xy(k)
        box(stage, f"/World/AssemblyLine/Slots/slot_{k:03d}", (x - PITCH / 2, y, 0.11), (0.12, 3.6, 0.02), looks["marker"])
    for name, (x, y) in GATES.items():
        g = UsdGeom.Xform.Define(stage, f"/World/Gates/{name}")
        g.AddTranslateOp().Set(Gf.Vec3d(x, y, 0))
        g.GetPrim().SetCustomData({"checkpoint": name})
        for post, py in (("PostL", -4), ("PostR", 4)):
            box(stage, f"/World/Gates/{name}/{post}", (0, py, 2.5), (0.3, 0.3, 5), looks["gate"])
        box(stage, f"/World/Gates/{name}/Beam", (0, 0, 5), (0.3, 8.3, 0.3), looks["gate"])

    # eye/target pairs framed on the part of the hall each camera is named after
    look_at(stage, "/World/Cameras/body_to_paint", (60, 28, 14), (115, 56, 0), 18)
    look_at(stage, "/World/Cameras/paint_to_assembly", (150, 22, 18), (200, 50, 0), 18)
    look_at(stage, "/World/Cameras/end_of_line", (20, -70, 16), (90, -25, 0), 18)
    look_at(stage, "/World/Cameras/overview", (-40, -175, 150), (130, 0, 0), 22)

    UsdLux.DomeLight.Define(stage, "/World/Lights/Dome").CreateIntensityAttr(350)
    sun = UsdLux.DistantLight.Define(stage, "/World/Lights/Sun")
    sun.CreateIntensityAttr(1500)
    sun.CreateAngleAttr(2.0)
    sun.AddRotateXYZOp().Set(Gf.Vec3f(-35, 0, 40))

    for oid, c in cars.items():
        name, opt = oid.replace("-", "_"), next((o for o in PAINT if o in opts[oid]), "none")
        root, t = car(stage, f"/World/Cars/{name}", paints[opt], looks["tyre"])
        for tc, (x, y) in keys(c, end):
            t.Set(Gf.Vec3d(x, y, 0), tc)
        vis = root.CreateVisibilityAttr()
        vis.Set(UsdGeom.Tokens.invisible, start)
        vis.Set(UsdGeom.Tokens.inherited, c["body_in"])
        info = {"order_id": oid, "options": ",".join(opts[oid]), "plan_pos": c["plan_pos"], "plan_time": c["plan_time"],
                "out_of_sequence": c["out_of_sequence"], "carried_over": c["assembly_in"] is None, "paint_line": c["paint_line"]}
        if c["assembly_in"] is not None:
            info.update(actual_pos=c["actual_pos"], assembly_in=c["assembly_in"], finished=c["finished"])
        root.GetPrim().SetCustomData(info)

        ghost, gt = car(stage, f"/World/Ghosts/{name}", ghosts[opt])
        gt.Set(Gf.Vec3d(*slot_xy(c["plan_pos"]), 0))
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
