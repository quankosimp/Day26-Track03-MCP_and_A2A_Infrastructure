"""End-to-end test client for the Legal Multi-Agent System.

Sends a legal question to the Customer Agent and prints the response.
"""

import asyncio
import argparse
import os
import sys
from uuid import uuid4

import httpx
from dotenv import load_dotenv

load_dotenv()

CUSTOMER_AGENT_URL = os.getenv("CUSTOMER_AGENT_URL", "http://localhost:10100")

DEFAULT_QUESTION = (
    "If a company breaks a contract and avoids taxes, "
    "what are the legal and regulatory consequences?"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send one end-to-end request to Customer Agent.")
    parser.add_argument(
        "--question",
        default=os.getenv("TEST_QUESTION", DEFAULT_QUESTION),
        help="Question to send to the Customer Agent.",
    )
    parser.add_argument(
        "--trace-id",
        default=os.getenv("TRACE_ID") or str(uuid4()),
        help="Trace ID for cross-service log correlation.",
    )
    parser.add_argument(
        "--context-id",
        default=os.getenv("CONTEXT_ID") or str(uuid4()),
        help="A2A context ID for this request.",
    )
    return parser.parse_args()


def _extract_text(response: object) -> str:
    """Extract text from A2A SendMessageResponse payload."""
    text = ""
    if hasattr(response, "root"):
        root = response.root
        if hasattr(root, "result"):
            result = root.result
            if hasattr(result, "artifacts") and result.artifacts:
                for artifact in result.artifacts:
                    for part in artifact.parts:
                        p = part.root if hasattr(part, "root") else part
                        if hasattr(p, "text") and p.text:
                            text += p.text
            elif hasattr(result, "parts") and result.parts:
                for part in result.parts:
                    p = part.root if hasattr(part, "root") else part
                    if hasattr(p, "text") and p.text:
                        text += p.text
    return text


async def main() -> None:
    args = _parse_args()

    print(f"Connecting to Customer Agent at {CUSTOMER_AGENT_URL}")
    print(f"Question: {args.question}")
    print(f"trace_id: {args.trace_id}")
    print(f"context_id: {args.context_id}")
    print("-" * 60)

    async with httpx.AsyncClient(timeout=300.0) as http_client:
        # Resolve agent card
        card_url = f"{CUSTOMER_AGENT_URL}/.well-known/agent.json"
        try:
            card_resp = await http_client.get(card_url)
            card_resp.raise_for_status()
        except Exception as e:
            print(f"ERROR: Could not reach Customer Agent at {card_url}")
            print(f"  {e}")
            print("Make sure all services are running (./start_all.sh)")
            sys.exit(1)

        from a2a.types import AgentCard, Message, Part, Role, TextPart
        from a2a.client import A2AClient

        agent_card = AgentCard.model_validate(card_resp.json())
        print(f"Connected to agent: {agent_card.name} v{agent_card.version}")
        print("-" * 60)

        # Build the legacy A2AClient
        client = A2AClient(httpx_client=http_client, agent_card=agent_card)

        # Construct the message
        from a2a.types import SendMessageRequest, MessageSendParams as MSP
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=args.question))],
            message_id=str(uuid4()),
            context_id=args.context_id,
            metadata={
                "trace_id": args.trace_id,
                "context_id": args.context_id,
                "delegation_depth": 0,
            },
        )
        request = SendMessageRequest(
            id=str(uuid4()),
            params=MSP(message=message),
        )

        print("Sending request (this may take 30-60s while agents chain)...\n")
        response = await client.send_message(request)

        result_text = _extract_text(response)
        if result_text:
            print("RESPONSE:")
            print("=" * 60)
            print(result_text)
            print("=" * 60)
        else:
            print("No text response received. Raw response:")
            print(response)


if __name__ == "__main__":
    asyncio.run(main())
