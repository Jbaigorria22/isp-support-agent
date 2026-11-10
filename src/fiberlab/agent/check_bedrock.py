"""Confirm Bedrock credentials, model access and the right model ID.

Run:  python -m fiberlab.agent.check_bedrock          (tests BEDROCK_MODEL_ID through the agent)
      python -m fiberlab.agent.check_bedrock --scan   (finds which Claude models this account can call)
"""

import os
import sys

from dotenv import load_dotenv

# Candidates from cheapest to most capable. "us."/"global." IDs are inference profiles.
CANDIDATES = [
    "anthropic.claude-haiku-5-5",
    "us.anthropic.claude-haiku-5-5",
    "global.anthropic.claude-haiku-5-5",
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
]


def scan(region: str) -> None:
    """One tiny call (max 5 output tokens) per candidate. Costs fractions of a cent."""
    import boto3

    client = boto3.client("bedrock-runtime", region_name=region)
    working = []
    for model_id in CANDIDATES:
        try:
            client.converse(
                modelId=model_id,
                messages=[{"role": "user", "content": [{"text": "Reply with OK"}]}],
                inferenceConfig={"maxTokens": 5},
            )
            print(f"  OK      {model_id}")
            working.append(model_id)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
            print(f"  FAIL    {model_id}  ({code})")

    if working:
        print(f"\nUse this in your .env:\n  BEDROCK_MODEL_ID={working[0]}")
    else:
        print("\nNo model worked. In the AWS console: Bedrock > Model catalog > pick an Anthropic model\n"
              "and complete the 'use case details' form if it asks for it. Then run --scan again.")


def check(model_id: str) -> None:
    from fiberlab.agent.brain import BedrockBrain

    print(f"Testing {model_id} ...")
    try:
        intent = BedrockBrain().classify_intent("Hola, no tengo internet desde esta mañana")
        print(f"OK: Bedrock answered, intent = {intent}")
    except Exception as exc:
        print(f"ERROR: {str(exc)[:300]}")
        print("\nRun with --scan to find which models this account can use.")


def main() -> None:
    load_dotenv()
    region = os.environ.get("AWS_REGION", "us-east-1")
    if "--scan" in sys.argv:
        print(f"Scanning Claude models in {region} ...")
        scan(region)
    else:
        check(os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"))


if __name__ == "__main__":
    main()
