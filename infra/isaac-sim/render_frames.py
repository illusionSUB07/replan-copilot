# Headless Isaac Sim: open the plant USD, step its time codes, save RGB frames per camera under /World/Cameras.

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--usd", default=str(ROOT / "omniverse/out/plant.usda"))
    p.add_argument("--out", default=str(ROOT / "frames"))
    p.add_argument("--every", type=int, default=10, help="render every K time codes")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--subframes", type=int, default=4, help="path-tracing subframes per capture, removes ghosting")
    return p.parse_args()


def render(args):
    # Kit modules only exist after SimulationApp has started
    import carb.settings
    import omni.replicator.core as rep
    import omni.timeline
    import omni.usd
    from PIL import Image
    from pxr import Usd, UsdGeom

    carb.settings.get_settings().set("/omni/replicator/captureOnPlay", False)
    ctx = omni.usd.get_context()
    if not ctx.open_stage(args.usd):
        raise SystemExit(f"cannot open {args.usd}")
    stage = ctx.get_stage()
    root = stage.GetPrimAtPath("/World/Cameras")
    cams = [p for p in Usd.PrimRange(root) if p.IsA(UsdGeom.Camera)] if root else []
    if not cams:
        raise SystemExit("no cameras under /World/Cameras")

    out = Path(args.out)
    shots = []
    for cam in cams:
        name = str(cam.GetPath()).removeprefix("/World/Cameras/").replace("/", "_")
        (out / name).mkdir(parents=True, exist_ok=True)
        rp = rep.create.render_product(str(cam.GetPath()), (args.width, args.height))
        rgb = rep.annotators.get("rgb")
        rgb.attach(rp)
        shots.append((name, rp, rgb))

    timeline = omni.timeline.get_timeline_interface()
    fps = stage.GetTimeCodesPerSecond()
    start, end = int(stage.GetStartTimeCode()), int(stage.GetEndTimeCode())
    for tc in range(start, end + 1, args.every):
        timeline.set_current_time(tc / fps)
        rep.orchestrator.step(rt_subframes=args.subframes, delta_time=0.0)
        for name, _, rgb in shots:
            Image.fromarray(rgb.get_data()[:, :, :3]).save(out / name / f"{tc:06d}.png")
        print(f"time code {tc}: {len(shots)} frames", flush=True)

    rep.orchestrator.wait_until_complete()
    for _, rp, rgb in shots:
        rgb.detach()
        rp.destroy()


def main():
    args = parse_args()
    from isaacsim import SimulationApp

    app = SimulationApp({"headless": True})
    try:
        render(args)
    finally:
        app.close()


if __name__ == "__main__":
    main()
