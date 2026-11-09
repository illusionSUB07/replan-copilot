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

All data, costs and plant parameters are synthetic.
