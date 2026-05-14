"""Tax Agent LangGraph definition.

Uses create_react_agent with a tax-specialised system prompt.
No tools — it answers purely from LLM knowledge.
"""

from __future__ import annotations

from langgraph.prebuilt import create_react_agent

from common.llm import get_llm

TAX_SYSTEM_PROMPT = """You are a specialist tax attorney and CPA.

Give a concise tax analysis in 120 words or fewer.
Use 3-5 bullet points and focus only on:
1. Civil vs criminal tax exposure
2. Statute of limitations (when relevant)
3. Responsible authorities (IRS/DOJ/FinCEN)
4. Company vs individual executive liability

Avoid long background explanations. Be direct and practical.
End with one short educational-use disclaimer.
"""


def create_graph():
    """Return a compiled LangGraph create_react_agent for tax questions."""
    llm = get_llm()
    graph = create_react_agent(
        model=llm,
        tools=[],
        prompt=TAX_SYSTEM_PROMPT,
    )
    return graph
