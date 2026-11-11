"""Chat with the FiberLab support agent in the console.

Run:  python -m fiberlab.agent.cli            (Amazon Bedrock)
      python -m fiberlab.agent.cli --offline  (rule-based brain, no AWS needed)
"""

import asyncio
import sys
import uuid

from dotenv import load_dotenv
from langgraph.types import Command

from fiberlab.agent.brain import BedrockBrain, RuleBrain
from fiberlab.agent.graph import build_graph
from fiberlab.agent.retrieval import build_retriever
from fiberlab.agent.toolbox import Toolbox


async def chat(offline: bool) -> None:
    brain = RuleBrain() if offline else BedrockBrain()
    async with Toolbox.open() as toolbox:
        graph = build_graph(brain, toolbox, build_retriever(offline))
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        result = await graph.ainvoke({}, config)
        while "__interrupt__" in result:
            print(f"\n🤖 FiberLab: {result['__interrupt__'][0].value['say']}")
            reply = input("\n🙂 Vos: ").strip()
            result = await graph.ainvoke(Command(resume=reply), config)

        print(f"\n🤖 FiberLab: {result['final_message']}")
        print(f"\n[outcome={result.get('outcome')} ticket={result.get('ticket_id', '-')} "
              f"guides={result.get('guides_used', [])} tools={toolbox.calls}]")


def main() -> None:
    load_dotenv()
    asyncio.run(chat(offline="--offline" in sys.argv))


if __name__ == "__main__":
    main()
