# Replan Copilot

When should a car plant replan its assembly sequence? Every disruption (late supplier, repaint, station stop) breaks the planned order, but every replan triggers new supplier call-offs. This project is a fully synthetic testbed for that decision, with Claude as the copilot.

- **Plant:** body shop → two parallel paint lines → assembly at an 8-minute takt (120 cars/day)
- **Planning:** daily order package → CP-SAT sequencing with k-in-n spacing rules → backward scheduling to body and paint entry
- **Simulation:** forward run with disruptions that become known over time; supplier estimates can be revised
- **Replanning:** a sandbox predicts the day from what is known and offers a resequenced plan; cost = out-of-sequence cars, carry-overs, call-off changes (more expensive inside the freeze window)
- **Copilot:** Claude (on Amazon Bedrock) checks the line through the day and decides whether releasing a new plan pays off, compared against "never replan" and "always replan"

```bash
uv run pytest
uv run python -m copilot            # baselines
uv run python -m copilot --agent    # add the Claude copilot (needs AWS credentials, see copilot/agent.py)
```

## Replay view

`web/index.html` plays back one simulated day: planned vs actual sequence, disruptions as they become known (including revised supplier estimates), the decision at each check and the running cost against "never replan".

```bash
uv run python -m copilot --export web/replay.json --seed 0 --policy agent      # policies: agent (Claude), expected, greedy, never, always
python -m http.server -d web                                                   # open http://localhost:8000
```

The page also accepts a dropped or selected replay JSON. Each check carries a `reason`: with `--policy agent` it is Claude's own closing sentence, otherwise it is generated from the numbers. The committed replay is day 0 decided by Claude.

## Omniverse scene

`omniverse/build_stage.py` turns a replay into an OpenUSD stage (`.usda`, Z-up, meters) for Omniverse / Isaac Sim: body-shop hall, paint booths P1/P2, a buffer, an assembly line with 120 slot markers, named checkpoint gates (`/World/Gates/body_in|paint_in|assembly_in|finished`) and three cameras under `/World/Cameras`. Every order is a box in `/World/Cars` colored by its main option and animated along its simulated times (time code = working minute, the day plays in about 2 minutes); built cars stop at their actual slot, carried-over cars stay in the buffer. A transparent ghost in `/World/Ghosts` marks each order's planned slot from its planned time. Each car's `customData` holds order id, options, planned/actual position and the out-of-sequence flag.

```bash
uv run --group omniverse python -m omniverse.build_stage web/replay.json omniverse/out/plant.usda
uv run --group omniverse pytest
```

`omniverse/perceive.py` is the vision step: Claude counts cars by colour in rendered camera frames (buffer, finished yard, paint booths) and each count is compared with what the stage says is in that camera's area at that time.

```bash
uv run --group omniverse python -m omniverse.perceive FRAMES_DIR    # FRAMES_DIR/<camera>/<time code>.png, writes FRAMES_DIR/perception.json
```

The replay's `outcome` carries each car's times (`body_in`, `paint_in`, `paint_line`, `ready`, `assembly_in`, `finished`, `plan_time`); for cars moved by a release, plan position and time refer to the final plan.

All data, costs and plant parameters are synthetic.

## Variant-to-Sequence

`thread/` chains five planning stages on synthetic data: product rules, configuration generator, mix optimiser (CP-SAT), slot planner and the line sequencer. A product change is pushed through all five and measured, in two modes (free replan vs lock valid orders), and Claude writes a planner briefing for each change.

```bash
uv run python -m thread                                # impact of each change as JSON
uv run python -m thread.export web/thread.json --brief # data for the page (briefings call Bedrock)
python3 -m http.server -d web                          # open http://localhost:8000/thread.html
```
