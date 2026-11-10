"""python -m omniverse.perceive FRAMES_DIR [plant.usda]: Claude counts cars by colour in rendered camera frames, compared with the USD stage."""
import base64
import json
import os
import sys
from pathlib import Path

from .build_stage import BODY_X, BUFFER_X, BUFFER_Y, PAINT, PAINT_X, PAINT_Y, YARD_PER_ROW, YARD_X0, YARD_Y

MODEL = os.environ.get("COPILOT_MODEL", "anthropic.claude-opus-5-5")
REGION = os.environ.get("COPILOT_AWS_REGION", "us-east-1")
PROFILE = os.environ.get("COPILOT_AWS_PROFILE", "Sandbox-dkhan")
COLOUR = {"two_tone": "red", "ev": "blue", "sunroof": "yellow", "sport_seats": "green", "none": "white"}
COLOURS = list(COLOUR.values())
BUFFER = ((BUFFER_X[0], BUFFER_X[1] + 3), (BUFFER_Y[0] - 3, BUFFER_Y[1] + 3), "the buffer between paint and assembly")
# camera -> (x range, y range, how the area looks in that camera's frame)
AREAS = {
    "body_to_paint": ((BODY_X[0] - 3, PAINT_X[1]), (PAINT_Y["P2"] - 3, PAINT_Y["P1"] + 3),
                      "the body shop and the two long glass paint booths in the foreground (cars may be inside the booths); "
                      "ignore the cars far in the background"),
    "paint_to_assembly": (*BUFFER[:2], "the buffer: the large blue-grey floor area; ignore the assembly line at the right edge"),
    "end_of_line": ((YARD_X0 - 3, YARD_X0 + YARD_PER_ROW * 4.5), (YARD_Y[-1] - 3, YARD_Y[0] + 3),
                    "the finished-car yard: the blue-grey strip in the right foreground; ignore the assembly line rows "
                    "with yellow edges"),
    "overview": (*BUFFER[:2], "the buffer: the blue-grey floor area at the top right of the hall, past the paint booths"),
}
WIDTH, HEIGHT = 1280, 720


def ground_truth(stage, t, camera):
    """Counts by colour (and total) of real cars inside the camera's area and frame at time code t."""
    from pxr import Gf, UsdGeom
    (x0, x1), (y0, y1), _ = AREAS[camera]
    cam = UsdGeom.Camera(stage.GetPrimAtPath(f"/World/Cameras/{camera}")).GetCamera(t)
    cam.verticalAperture = cam.horizontalAperture * HEIGHT / WIDTH  # the renderer keeps the horizontal field of view
    frustum = cam.frustum
    counts = dict.fromkeys(COLOURS, 0)
    for car in stage.GetPrimAtPath("/World/Cars").GetChildren():
        x, y, _ = car.GetAttribute("xformOp:translate").Get(t)
        if (UsdGeom.Imageable(car).ComputeVisibility(t) != UsdGeom.Tokens.invisible and x0 <= x <= x1 and y0 <= y <= y1
                and frustum.Intersects(Gf.Vec3d(x, y, 0.9))):
            opts = car.GetCustomData()["options"].split(",")
            counts[COLOUR[next((o for o in PAINT if o in opts), "none")]] += 1
    return {**counts, "total": sum(counts.values())}


SCHEMA = {"type": "object", "additionalProperties": False, "required": [*COLOURS, "notes"],
          "properties": {**{c: {"type": "integer"} for c in COLOURS}, "notes": {"type": "string"}}}


def parse(text):
    """Validated counts from the model's JSON reply; total is derived, not trusted."""
    d = json.loads(text)
    if not isinstance(d, dict) or set(d) - {*COLOURS, "notes"}:
        raise ValueError(f"unexpected reply: {text!r}")
    counts = {}
    for c in COLOURS:
        v = d.get(c)
        if type(v) is not int or v < 0:
            raise ValueError(f"bad count for {c}: {v!r}")
        counts[c] = v
    return {**counts, "total": sum(counts.values()), "notes": str(d.get("notes", ""))}


def perceive(png, camera, client=None):
    """Ask Claude for counts by colour of the cars in the camera's area, one call per image."""
    from anthropic import AnthropicBedrockMantle
    client = client or AnthropicBedrockMantle(aws_region=REGION, aws_profile=PROFILE, max_retries=6)
    prompt = (f"This is a rendered camera frame of a synthetic car plant (body shop -> two paint lines -> buffer -> "
              f"serpentine assembly line -> finished-car yard). Cars are small low-poly boxes with wheels, painted "
              f"{', '.join(COLOURS[:-1])} or {COLOURS[-1]} (white also covers silver/light grey). Faded, see-through cars "
              f"on the assembly line are planning ghosts, not real cars. Count the real cars in {AREAS[camera][2]}. "
              f"Count each car once, by body colour. Reply with the counts per colour and a one-sentence note on what "
              f"made counting hard.")
    msg = client.messages.create(
        model=MODEL, max_tokens=4000, output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                         "data": base64.b64encode(Path(png).read_bytes()).decode()}},
            {"type": "text", "text": prompt}]}])
    return parse("".join(b.text for b in msg.content if b.type == "text"))


def main(frames, usd="omniverse/out/plant.usda"):
    from anthropic import AnthropicBedrockMantle
    from pxr import Usd
    stage, client = Usd.Stage.Open(usd), AnthropicBedrockMantle(aws_region=REGION, aws_profile=PROFILE, max_retries=6)
    rows = []
    for png in sorted(Path(frames).glob("*/*.png")):
        camera, t = png.parent.name, int(png.stem)
        if camera not in AREAS:
            continue
        truth, seen = ground_truth(stage, t, camera), perceive(png, camera, client)
        rows.append({"camera": camera, "time": t, "truth": truth, "perceived": seen, "abs_error": abs(seen["total"] - truth["total"])})
        print(f"{camera:18} {t:5}  " + "  ".join(f"{c[0]} {truth[c]}/{seen[c]}" for c in COLOURS)
              + f"  total {truth['total']}/{seen['total']}  err {rows[-1]['abs_error']}", flush=True)
    mae = sum(r["abs_error"] for r in rows) / max(len(rows), 1)
    print(f"{len(rows)} frames, truth/perceived per colour (r b y g w = red blue yellow green white), MAE of totals {mae:.2f}")
    (Path(frames) / "perception.json").write_text(json.dumps({"model": MODEL, "mae_total": mae, "rows": rows}, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:])
