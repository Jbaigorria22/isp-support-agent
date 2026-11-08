"""One cheap Bedrock call to confirm credentials, model access and the model ID.

Run:  python -m fiberlab.agent.check_bedrock
"""

import os

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    from fiberlab.agent.brain import BedrockBrain

    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-haiku-5-5")
    print(f"Testing {model_id} ...")
    try:
        intent = BedrockBrain().classify_intent("Hola, no tengo internet desde esta mañana")
        print(f"OK: Bedrock answered, intent = {intent}")
    except Exception as exc:  # show a useful hint for the most common errors
        message = str(exc)
        print(f"ERROR: {message[:300]}")
        if "on-demand throughput" in message or "inference profile" in message:
            print("\nThis model needs an inference profile ID. List them with:\n"
                  '  aws bedrock list-inference-profiles --region us-east-1 '
                  '--query "inferenceProfileSummaries[?contains(inferenceProfileId, \'haiku-5-5\')].inferenceProfileId"\n'
                  "Then set BEDROCK_MODEL_ID in your .env to that ID (it usually starts with 'us.').")
        elif "AccessDenied" in message:
            print("\nYour IAM user needs bedrock:InvokeModel permission, and model access enabled in the Bedrock console.")


if __name__ == "__main__":
    main()
