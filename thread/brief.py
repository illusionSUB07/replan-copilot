"""Claude turns one change's impact numbers into a short planner briefing."""
import json

from anthropic import AnthropicBedrockMantle

from copilot.agent import MODEL, PROFILE, REGION

from .product import scenario

SYSTEM = """You brief production planners at a car plant. The planning chain is: product rules -> buildable
configurations -> weekly production mix -> daily slots -> line sequence. Every car whose content, day or line
position changes triggers a supplier call-off change. You get one product change and its measured impact.
Write 4 to 6 plain sentences, no headings or bullets: what changed, what it forces in the plan (with the numbers),
what the plan did about it, anything that blocks the change (capacities, rules), and one concrete recommendation.
Only use numbers that are in the input."""


def briefing(sc):
    keep = {k: sc[k] for k in ("change", "rules_added", "rules_removed", "new_options", "impact")}
    names = {o: d for f in scenario(sc["name"])["families"].values() for o, d in f.items()}
    words = {w.strip(",") for line in sc["rules_added"] + sc["rules_removed"] for w in line.split()}
    opts = (set(sc["new_options"]) | words) & set(names)  # option codes only, not markets or models
    keep["option_names"] = {o: names[o] for o in sorted(opts)}
    keep["option_counts"] = {o: {"before": sc["before"]["option_counts"].get(o, 0), "after": sc["after"]["option_counts"].get(o, 0)} for o in opts}
    client = AnthropicBedrockMantle(aws_region=REGION, aws_profile=PROFILE, max_retries=6)
    r = client.messages.create(model=MODEL, max_tokens=4000, output_config={"effort": "medium"}, system=SYSTEM,
                               messages=[{"role": "user", "content": json.dumps(keep)}])
    if r.stop_reason == "refusal":
        raise RuntimeError("model refused the briefing")
    return " ".join(b.text for b in r.content if b.type == "text").strip()
