"""A2A delegation helper.

Provides `delegate(endpoint, question, context_id, trace_id, depth)` which
sends a message to another A2A agent and returns the text response.
"""

from __future__ import annotations

import logging
from uuid import uuid4

import httpx

from a2a.client import A2AClient
from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Part,
    Role,
    SendMessageRequest,
    TextPart,
)

logger = logging.getLogger(__name__)


async def delegate(
    endpoint: str,
    question: str,
    context_id: str,
    trace_id: str,
    depth: int,
) -> str:
    """Send a question to an A2A agent and return the text response.

    Args:
        endpoint: Base URL of the target agent (e.g. "http://localhost:10101").
        question: The question to ask.
        context_id: Current A2A context ID to propagate.
        trace_id: Trace ID generated at the Customer Agent; propagated throughout.
        depth: Current delegation depth (used to enforce MAX_DELEGATION_DEPTH).

    Returns:
        The agent's text response, or an empty string if none could be extracted.
    """
    async with httpx.AsyncClient(timeout=300.0) as http_client:
        # Fetch agent card
        card_url = f"{endpoint}/.well-known/agent.json"
        card_resp = await http_client.get(card_url)
        card_resp.raise_for_status()
        agent_card = AgentCard.model_validate(card_resp.json())

        # Build deprecated (legacy) A2AClient — straightforward for send_message
        client = A2AClient(httpx_client=http_client, agent_card=agent_card)

        # Build message with trace metadata
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=question))],
            message_id=str(uuid4()),
            context_id=context_id,
            metadata={
                "trace_id": trace_id,
                "context_id": context_id,
                "delegation_depth": depth,
            },
        )

        request = SendMessageRequest(
            id=str(uuid4()),
            params=MessageSendParams(message=message),
        )

        logger.info(
            "A2A delegate request | endpoint=%s depth=%d trace=%s context=%s",
            endpoint,
            depth,
            trace_id,
            context_id,
        )

        response = await client.send_message(request)
        logger.info(
            "A2A delegate response | endpoint=%s depth=%d trace=%s",
            endpoint,
            depth,
            trace_id,
        )

        # Extract text from SendMessageResponse
        return _extract_text(response)


def _extract_text(response: object) -> str:
    """Walk the response tree and collect all TextPart.text values."""
    text = ""

    # Unwrap root if it's a RootModel
    if hasattr(response, "root"):
        response = response.root

    # SendMessageSuccessResponse has a .result (Task | Message)
    result = getattr(response, "result", None)
    if result is None:
        return text

    # Task — text lives in artifacts
    artifacts = getattr(result, "artifacts", None)
    if artifacts:
        for artifact in artifacts:
            parts = getattr(artifact, "parts", []) or []
            for part in parts:
                text += _part_text(part)
        if text:
            return text

    # Message — text lives in parts directly
    parts = getattr(result, "parts", None)
    if parts:
        for part in parts:
            text += _part_text(part)

    # Task history messages as fallback
    if not text:
        history = getattr(result, "history", None)
        if history:
            for msg in history:
                msg_parts = getattr(msg, "parts", []) or []
                for part in msg_parts:
                    text += _part_text(part)

    return text


def _part_text(part: object) -> str:
    """Extract text from a Part object (handling both Part(root=TextPart) and raw TextPart)."""
    inner = getattr(part, "root", part)
    return getattr(inner, "text", "") or ""
