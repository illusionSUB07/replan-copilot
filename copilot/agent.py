"""Claude as the replan policy: at each check it inspects the line, compares options in the sandbox and decides."""
import json
import os

from anthropic import AnthropicBedrockMantle, beta_tool

from .plant import clock
from .replan import CALL_OFF_CHANGE, CARRY_OVER, EMERGENCY_CHANGE, FREEZE, OUT_OF_SEQUENCE, evaluate, known
from .sim import kpis, simulate

MODEL = os.environ.get("COPILOT_MODEL", "anthropic.claude-opus-5-5")
REGION = os.environ.get("COPILOT_AWS_REGION", "us-east-1")  # Opus 5.5 on Bedrock Mantle is enabled there in the sandbox
PROFILE = os.environ.get("COPILOT_AWS_PROFILE", "Sandbox-dkhan")

SYSTEM = f"""You are the replanning copilot of a car assembly plant (body shop -> two paint lines -> assembly, 8-minute takt).
Several times a day you check the line and decide whether to release a resequenced assembly plan to suppliers or keep the current one.

Costs (EUR): out-of-sequence car at the line {OUT_OF_SEQUENCE}, car carried over to tomorrow {CARRY_OVER},
supplier call-off change {CALL_OFF_CHANGE}, or {EMERGENCY_CHANGE} if the car is due within {FREEZE} minutes (freeze window).
Only these costs count; how late cars are does not. Predictions only use disruptions known so far.
In this plant, an open supplier delay is revised upward about half the time, by 60, 120 or 180 minutes, usually
about an hour before the first estimate expires. Decide on expected cost, not on the worst case: compare wait vs
resequence with evaluate_options at delay_growth_min 0 and at the possible slips, weight them by how likely they are,
and release when resequencing is cheaper in expectation. A release that changes nothing is pointless.

Use get_status and evaluate_options, then either call release_resequence or keep the plan. Finish with one short sentence
stating your decision and the main reason."""


def make_policy(disruptions, verbose=True):
    client = AnthropicBedrockMantle(aws_region=REGION, aws_profile=PROFILE, max_retries=6)
    history, reasons = [], {}

    def policy(now, rows):
        decision = {"release": False}

        @beta_tool
        def get_status() -> str:
            """Current time, disruptions known so far, and the predicted day outcome if the plan is kept."""
            seen = known(disruptions, now)
            actual = simulate(rows, seen)
            built = sum(a.get("assembly_in", now) < now for a in actual.values())
            return json.dumps({
                "now": clock(now),
                "cars_built_so_far": built,
                "known_disruptions": [{**d, **{k: clock(d[k]) for k in ("start", "end", "until", "known_at") if k in d}}
                                      for d in seen],
                "predicted_if_kept": kpis(rows, actual),
            })

        @beta_tool
        def evaluate_options(delay_growth_min: int = 0) -> str:
            """Sandbox comparison of predicted full-day cost: keep the plan ('wait') vs release a resequenced plan.

            Args:
                delay_growth_min: Stress test, assume every open supplier delay slips by this many minutes.
            """
            return json.dumps({name: {k: v for k, v in c.items() if k not in ("avg_delay_min", "max_delay_min")}
                               for name, c in evaluate(rows, disruptions, now, delay_growth_min).items()})

        @beta_tool
        def release_resequence(reason: str) -> str:
            """Release the resequenced plan to the line and suppliers.

            Args:
                reason: One sentence why releasing now pays off.
            """
            decision["release"], decision["reason"] = True, reason
            return "released"

        prompt = f"It is {clock(now)}. Check the line and decide."
        if history:
            prompt += "\nYour earlier decisions today:\n" + "\n".join(history)
        runner = client.beta.messages.tool_runner(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=SYSTEM,
            tools=[get_status, evaluate_options, release_resequence],
            messages=[{"role": "user", "content": prompt}],
        )
        final = runner.until_done()
        if final.stop_reason == "refusal":
            raise RuntimeError(f"model refused at {clock(now)}")
        text = " ".join(b.text for b in final.content if b.type == "text").strip()
        reasons[now] = text
        history.append(f"- {clock(now)}: {'RELEASED' if decision['release'] else 'kept plan'} ({text[-300:]})")
        if verbose:
            print(history[-1])
        return decision["release"]

    policy.reasons = reasons  # check time -> Claude's own explanation, used by the replay export
    return policy
