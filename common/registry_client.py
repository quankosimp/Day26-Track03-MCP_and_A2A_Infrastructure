"""Registry client helpers.

Provides `discover(task)` to look up an agent endpoint from the registry,
and `register(agent_info)` for agents to self-register on startup.
"""

import os
import logging

import httpx

REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:10000")
logger = logging.getLogger(__name__)


async def discover(task: str) -> str:
    """Return the endpoint URL of the agent that handles the given task.

    Args:
        task: The task identifier (e.g. "legal_question", "tax_question").

    Returns:
        The HTTP endpoint base URL of the matching agent.

    Raises:
        httpx.HTTPStatusError: If no agent is found or the registry is unreachable.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        logger.info("Registry discover request | task=%s", task)
        resp = await client.get(f"{REGISTRY_URL}/discover/{task}")
        resp.raise_for_status()
        payload = resp.json()
        endpoint = payload["endpoint"]
        logger.info(
            "Registry discover success | task=%s agent=%s endpoint=%s",
            task,
            payload.get("agent_name", "unknown"),
            endpoint,
        )
        return endpoint


async def register(agent_info: dict) -> None:
    """Register an agent with the registry.

    Args:
        agent_info: Dict with keys: agent_name, version, description,
                    tasks, endpoint, tags.

    Raises:
        httpx.HTTPStatusError: If registration fails.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        logger.info(
            "Registry register request | agent=%s endpoint=%s tasks=%s",
            agent_info.get("agent_name", "unknown"),
            agent_info.get("endpoint", "unknown"),
            agent_info.get("tasks", []),
        )
        resp = await client.post(f"{REGISTRY_URL}/register", json=agent_info)
        resp.raise_for_status()
        logger.info("Registry register success | agent=%s", agent_info.get("agent_name", "unknown"))
