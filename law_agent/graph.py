"""Law Agent LangGraph StateGraph definition.

Graph topology:
    analyze_law → check_routing → (parallel) call_tax + call_compliance → aggregate → END

The parallel branches (call_tax / call_compliance) are dispatched via LangGraph's
Send API so that both sub-agent calls happen concurrently.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, TypedDict

import httpx

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.constants import Send
from langgraph.graph import END, StateGraph

from common.llm import get_llm

logger = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 3


# ---------------------------------------------------------------------------
# State definition
# ---------------------------------------------------------------------------

def _last_wins(a: str, b: str) -> str:
    """Reducer: keep the most recently written value."""
    return b if b else a


class LawState(TypedDict):
    question: str
    context_id: str
    trace_id: str
    delegation_depth: int
    law_analysis: str
    needs_tax: bool
    needs_compliance: bool
    # Annotated so parallel branches can both write without conflict
    tax_result: Annotated[str, _last_wins]
    compliance_result: Annotated[str, _last_wins]
    final_answer: str


def _subagent_unavailable_message(agent_name: str, exc: Exception) -> str:
    """Create user-facing fallback text when a delegated sub-agent is unavailable."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code if exc.response is not None else None
        req_url = str(exc.request.url) if exc.request is not None else ""
        if status == 404 and "/discover/" in req_url:
            return (
                f"[{agent_name} analysis unavailable: registry could not discover an online "
                f"{agent_name} service for this task.]"
            )
        return f"[{agent_name} analysis unavailable: upstream returned HTTP {status}.]"
    if isinstance(exc, httpx.HTTPError):
        return f"[{agent_name} analysis unavailable: network error while calling sub-agent.]"
    return f"[{agent_name} analysis unavailable: {exc}]"


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def analyze_law(state: LawState) -> dict:
    """LLM analysis from a contract / general law perspective."""
    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                "You are a senior corporate litigation attorney specialising in contract law, "
                "tort law, and general business law. Analyse the legal aspects of the question "
                "thoroughly, covering relevant statutes, case law principles, and liability exposure."
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    return {"law_analysis": result.content}


async def check_routing(state: LawState) -> dict:
    """Determine whether tax and/or compliance sub-agents are needed.

    Returns updated state flags so the routing function can read them.
    If delegation depth is already at the max, skip further delegation.
    """
    depth = state.get("delegation_depth", 0)
    if depth >= MAX_DELEGATION_DEPTH:
        logger.info("Max delegation depth reached (%d); skipping sub-agents", depth)
        return {"needs_tax": False, "needs_compliance": False}

    llm = get_llm()
    messages = [
        SystemMessage(
            content=(
                'You are a legal routing expert. Based on the question, decide whether '
                'specialist sub-agents are needed.\n'
                'Reply with ONLY valid JSON — no markdown, no extra text:\n'
                '{"needs_tax": <true|false>, "needs_compliance": <true|false>}\n\n'
                'needs_tax = true  → question involves tax law, IRS, tax evasion, penalties\n'
                'needs_compliance = true → question involves regulatory compliance, SEC, SOX, AML, FCPA'
            )
        ),
        HumanMessage(content=state["question"]),
    ]
    result = await llm.ainvoke(messages)
    raw = result.content.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Routing LLM returned non-JSON: %r — defaulting to both=True", raw)
        parsed = {"needs_tax": True, "needs_compliance": True}

    needs_tax = bool(parsed.get("needs_tax", True))
    needs_compliance = bool(parsed.get("needs_compliance", True))
    logger.info("Routing decision: needs_tax=%s needs_compliance=%s", needs_tax, needs_compliance)
    return {"needs_tax": needs_tax, "needs_compliance": needs_compliance}


def route_to_subagents(state: LawState) -> list[Send]:
    """Routing function: dispatch parallel Send objects based on routing flags.

    This function is used with add_conditional_edges; it returns a list of
    Send objects which LangGraph executes as parallel branches.
    """
    sends: list[Send] = []
    if state.get("needs_tax"):
        sends.append(Send("call_tax", state))
    if state.get("needs_compliance"):
        sends.append(Send("call_compliance", state))
    if not sends:
        # No sub-agents needed — go straight to aggregation
        sends.append(Send("aggregate", state))
    return sends


async def call_tax(state: LawState) -> dict:
    """Delegate to the Tax Agent via A2A."""
    from common.a2a_client import delegate
    from common.registry_client import discover

    logger.info(
        "LawAgent -> TaxAgent | trace=%s context=%s depth=%d",
        state["trace_id"],
        state["context_id"],
        state.get("delegation_depth", 0) + 1,
    )

    try:
        endpoint = await discover("tax_question")
        logger.info("LawAgent discovered TaxAgent endpoint=%s", endpoint)
        result = await delegate(
            endpoint=endpoint,
            question=state["question"],
            context_id=state["context_id"],
            trace_id=state["trace_id"],
            depth=state.get("delegation_depth", 0) + 1,
        )
        logger.info("Tax Agent returned %d chars", len(result))
        return {"tax_result": result}
    except Exception as exc:
        logger.exception("call_tax failed: %s", exc)
        return {"tax_result": _subagent_unavailable_message("Tax", exc)}


async def call_compliance(state: LawState) -> dict:
    """Delegate to the Compliance Agent via A2A."""
    from common.a2a_client import delegate
    from common.registry_client import discover

    logger.info(
        "LawAgent -> ComplianceAgent | trace=%s context=%s depth=%d",
        state["trace_id"],
        state["context_id"],
        state.get("delegation_depth", 0) + 1,
    )

    try:
        endpoint = await discover("compliance_question")
        logger.info("LawAgent discovered ComplianceAgent endpoint=%s", endpoint)
        result = await delegate(
            endpoint=endpoint,
            question=state["question"],
            context_id=state["context_id"],
            trace_id=state["trace_id"],
            depth=state.get("delegation_depth", 0) + 1,
        )
        logger.info("Compliance Agent returned %d chars", len(result))
        return {"compliance_result": result}
    except Exception as exc:
        logger.exception("call_compliance failed: %s", exc)
        return {"compliance_result": _subagent_unavailable_message("Compliance", exc)}


async def aggregate(state: LawState) -> dict:
    """Combine law_analysis, tax_result, and compliance_result into a final answer."""
    llm = get_llm()

    sections: list[str] = []
    if state.get("law_analysis"):
        sections.append(f"## Legal Analysis\n{state['law_analysis']}")
    if state.get("tax_result"):
        sections.append(f"## Tax Analysis\n{state['tax_result']}")
    if state.get("compliance_result"):
        sections.append(f"## Regulatory Compliance Analysis\n{state['compliance_result']}")

    combined = "\n\n---\n\n".join(sections)

    messages = [
        SystemMessage(
            content=(
                "You are a senior legal counsel synthesising specialist analyses into a "
                "comprehensive, well-structured response for the client. Combine the following "
                "analyses into a cohesive answer with clear sections. Avoid redundancy. "
                "End with a brief disclaimer that the analysis is educational and the client "
                "should consult licensed attorneys for their specific situation."
            )
        ),
        HumanMessage(content=combined),
    ]
    result = await llm.ainvoke(messages)
    return {"final_answer": result.content}


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def create_graph():
    """Build and compile the Law Agent StateGraph."""
    graph = StateGraph(LawState)

    graph.add_node("analyze_law", analyze_law)
    graph.add_node("check_routing", check_routing)
    graph.add_node("call_tax", call_tax)
    graph.add_node("call_compliance", call_compliance)
    graph.add_node("aggregate", aggregate)

    graph.set_entry_point("analyze_law")
    graph.add_edge("analyze_law", "check_routing")

    # Conditional parallel dispatch: after check_routing, route_to_subagents
    # returns a list of Send objects (to call_tax, call_compliance, or aggregate)
    graph.add_conditional_edges(
        "check_routing",
        route_to_subagents,
        ["call_tax", "call_compliance", "aggregate"],
    )

    graph.add_edge("call_tax", "aggregate")
    graph.add_edge("call_compliance", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()
