"""Bài Tập 2: Thêm Tools và Knowledge Base

Hoàn thành các TODO để thêm tool và knowledge base entry mới.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from common.llm import get_llm

# Knowledge base
LEGAL_KNOWLEDGE = [
    {
        "id": "ucc_breach",
        "keywords": ["breach", "contract", "remedies", "damages", "ucc"],
        "text": (
            "Under the Uniform Commercial Code (UCC) Article 2, remedies for breach of contract "
            "include: (1) expectation damages; (2) consequential damages; (3) specific performance; "
            "(4) cover damages. Statute of limitations is typically 4 years (UCC § 2-725)."
        ),
    },
    {
        "id": "labor_law",
        "keywords": ["lao động", "sa thải", "kỷ luật", "hợp đồng lao động", "tranh chấp lao động"],
        "text": (
            "Theo Bộ luật Lao động 2019, người sử dụng lao động chỉ được sa thải trong các trường hợp "
            "luật định và phải tuân thủ đúng trình tự xử lý kỷ luật lao động. Người lao động có quyền "
            "khởi kiện tranh chấp lao động cá nhân để bảo vệ quyền lợi; thời hiệu khởi kiện tại Tòa án "
            "thường là 1 năm kể từ ngày phát hiện quyền, lợi ích hợp pháp bị xâm phạm."
        ),
    },
]


@tool
def search_legal_knowledge(query: str) -> str:
    """Tìm kiếm trong knowledge base pháp lý."""
    query_lower = query.lower()
    for entry in LEGAL_KNOWLEDGE:
        if any(kw in query_lower for kw in entry["keywords"]):
            return f"[{entry['id']}] {entry['text']}"
    return "Không tìm thấy thông tin liên quan."


@tool
def check_statute_of_limitations(case_type: str) -> str:
    """Kiểm tra thời hiệu khởi kiện theo loại vụ việc."""
    case = case_type.lower()

    if any(kw in case for kw in ["hợp đồng", "contract", "breach", "ucc"]):
        return (
            "Thời hiệu khởi kiện tham khảo cho tranh chấp vi phạm hợp đồng mua bán hàng hóa "
            "(UCC § 2-725): 4 năm."
        )
    if any(kw in case for kw in ["lao động", "sa thải", "kỷ luật", "employment"]):
        return (
            "Thời hiệu khởi kiện tham khảo cho tranh chấp lao động cá nhân tại Tòa án theo Bộ luật "
            "Lao động 2019: 1 năm kể từ ngày phát hiện quyền, lợi ích hợp pháp bị xâm phạm."
        )
    if any(kw in case for kw in ["trade secret", "dtsa", "bí mật kinh doanh", "nda"]):
        return (
            "Thời hiệu khởi kiện tham khảo cho hành vi xâm phạm bí mật kinh doanh theo DTSA: 3 năm."
        )
    return (
        "Chưa có quy tắc thời hiệu cụ thể trong tool cho loại vụ việc này. "
        "Vui lòng cung cấp rõ hơn loại tranh chấp và hệ thống pháp luật áp dụng."
    )


async def main():
    load_dotenv()
    llm = get_llm()
    
    tools = [search_legal_knowledge, check_statute_of_limitations]
    llm_with_tools = llm.bind_tools(tools)
    
    question = "Thời hiệu khởi kiện vụ vi phạm hợp đồng là bao lâu?"
    
    messages = [
        SystemMessage(content="Bạn là chuyên gia pháp lý. Sử dụng tools để tra cứu thông tin."),
        HumanMessage(content=question),
    ]
    
    print(f"Câu hỏi: {question}\n")
    
    # First LLM call - decide which tools to use
    response = await llm_with_tools.ainvoke(messages)
    messages.append(response)
    
    # Execute tools if requested
    if response.tool_calls:
        for tool_call in response.tool_calls:
            print(f"🔧 Gọi tool: {tool_call['name']}")
            tool_result = None
            
            if tool_call["name"] == "search_legal_knowledge":
                tool_result = search_legal_knowledge.invoke(tool_call["args"])
            elif tool_call["name"] == "check_statute_of_limitations":
                tool_result = check_statute_of_limitations.invoke(tool_call["args"])
            
            if tool_result:
                messages.append(ToolMessage(content=tool_result, tool_call_id=tool_call["id"]))
        
        # Second LLM call - synthesize final answer
        final_response = await llm_with_tools.ainvoke(messages)
        print(f"\n✅ Kết quả:\n{final_response.content}")
    else:
        print(f"\n✅ Kết quả:\n{response.content}")


if __name__ == "__main__":
    asyncio.run(main())
