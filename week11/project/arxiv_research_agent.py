"""arXiv 论文调研多 Agent：真实搜索 + 研究员/写手/主编协作产出调研报告。

图结构：
    START -> search（真实 arXiv API）-> research（提炼贡献）-> write（写初稿）
      -> review（评审）
            ├─ approve -> END（保存 report.md）
            └─ revision -> write（≤ MAX_ROUNDS 轮）

用法：
    python arxiv_research_agent.py
    输入研究主题（如 "AI Agent"）；/exit 退出

安装：uv pip install openai langgraph httpx
前置：设置环境变量 DEEPSEEK_API_KEY（或项目目录 .env）

注意：search_arxiv 已实现并验证（必须用 https）；其余节点按 TODO 完成。
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Annotated, TypedDict
from json import JSONDecodeError
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END, add_messages
from openai import OpenAI

load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_ROUNDS = 2
SUMMARY_LIMIT = 400        # 摘要截断长度（省 token）
REPORT_FILE = Path(__file__).parent / "report.md"

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_URL = "https://export.arxiv.org/api/query"    # 必须 https！

RESEARCHER_PROMPT = """你是论文调研员。用户给了研究主题，并提供了搜到的论文（标题+摘要）。
任务：逐篇提炼"这篇论文的核心贡献"，每条 1-2 句，聚焦：解决了什么问题、用什么方法、关键结果。
输出格式：如下：
1.【论文标题】
- 解决的问题
- 使用的方法
- 关键结论
- 链接:(原文url)
2. ...
若某篇论文与主题明显无关时在结尾注明"与主题相关性低"。
铁律：论文列表是系统提供的唯一事实来源。如果列表为空，你必须直接回复"未搜索到相关论文"；
绝对禁止自行编造论文标题、方法、结论或链接。"""

WRITER_PROMPT = """你是调研报告写手。根据【调研要点】撰写约 400-600 字的调研报告。
结构：## 概述 → ## 代表性论文（每篇给出标题+链接+贡献）→ ## 趋势观察。
链接必须用原文 URL。如果【主编意见】不为空，必须按意见修改后输出全文。"""

REVIEWER_PROMPT = """你是主编。审阅【初稿】，判断是否需要修改。
只输出 JSON（必须含 "json" 字样），格式：
{"verdict": "approve" 或 "revision", "comments": "修改意见"}
如果"verdict"为"approve","comments"可以为空内容，但一定要保留"comments"这个字段（键）
标准：是否覆盖所有论文、要点是否准确、结构是否清晰、链接是否保留。"""

QUERY_REWRITER_PROMPT = """你精通 arXiv 查询语法。把用户的研究主题改写为适合
search_query 参数的查询串。

语法要点：
- 短语必须用双引号，如 abs:"operating system"（单引号无效！）
- 字段前缀：ti: 标题 / abs: 摘要 / all: 全部元数据
- 布尔连接：AND / OR，可用括号分组
- 使用英文关键词，不要把中文直接放进查询

示例：用户输入"AI操作系统" -> (abs:"operating system") AND (abs:AI OR abs:agent)

要求：只输出查询串本身，不要任何解释、不要代码块围栏。"""


# ---------- State（纯字段；跨 Agent 只交换结构化中间产物） ----------
class ResearchState(TypedDict):
    topic: str
    papers: list                      # [{"title","url","summary"}, ...]
    notes: str                        # 研究员产出
    draft: str                        # 写手产出
    verdict: str
    comments: str
    rounds: int


# ---------- 搜索：真实 arXiv API（已实现并验证） ----------
def search_arxiv(query: str, max_results: int = 5) -> list[dict]:
    """用 arXiv 查询串搜索，返回 [{"title", "url", "summary"}, ...]（摘要已截断）。

    query 是 search_query 参数（如 all:"AI OS" 或 (abs:"operating system") AND abs:AI），
    由查询改写器生成或由调用方传入完整语法。
    注意：用 https（http 会 301 且 httpx 默认不跟）；解析带 Atom 命名空间前缀。
    """
    resp = httpx.get(
        ARXIV_URL,
        params={"search_query": query, "start": 0, "max_results": max_results},
        timeout=20,
    )
    resp.raise_for_status()
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        summary = entry.findtext(f"{ATOM}summary", "").strip().replace("\n", " ")
        papers.append({
            "title": entry.findtext(f"{ATOM}title", "").strip().replace("\n", " "),
            "url": entry.findtext(f"{ATOM}id", "").strip(),
            "summary": summary[:SUMMARY_LIMIT],
        })
    return papers



# ---------- 模型调用 ----------
def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key


client: OpenAI | None = None


def get_client() -> OpenAI:
    """惰性创建 client：只在第一次真正需要时才要求 API Key（import 不触发）。"""
    global client
    if client is None:
        client = OpenAI(api_key=load_api_key(), base_url=BASE_URL)
    return client


def call_client(messages: list[dict], temperature: float = 0.5) -> str:
    resp = get_client().chat.completions.create(model=MODEL, messages=messages, temperature=temperature)
    return resp.choices[0].message.content


# ---------- Agent 节点（TODO） ----------
def clean_query(text: str) -> str:
    """清洗模型生成的查询：去围栏/说明文字，单引号统一转双引号（arXiv 短语只认双引号）。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    return text.replace("'", '"')


def search_node(state: ResearchState) -> dict:
    """查询改写（LLM）-> arXiv 搜索 -> 0 结果时回退短语搜索。

    返回 {"papers": [...]}，打印 "[搜索] 找到 N 篇论文"。
    提醒：礼貌使用 arXiv，搜索前 time.sleep(3)。
    """
    # TODO 1
    time.sleep(3)
    # 第一步：让 LLM 把用户主题改写成 arXiv 查询语法（英文 + 双引号短语 + 字段前缀）
    rewritten = clean_query(call_client([
        {"role": "system", "content": QUERY_REWRITER_PROMPT},
        {"role": "user", "content": f"研究主题：{state['topic']}"},
    ]))
    papers = search_arxiv(rewritten)
    if not papers:
        # 第二步：改写查询无效时，回退到原始主题的短语搜索
        print(f"[搜索] 改写查询无结果（{rewritten}），回退短语搜索")
        papers = search_arxiv(f'all:"{state["topic"]}"')
    print(f"[搜索]找到{len(papers)}篇论文")
    return {"papers": papers}


def empty_node(state: ResearchState) -> dict:
    """搜索无结果时走这里：给用户提示并正常结束（防空数据进入研究环节）。"""
    print("[提示] 未搜索到相关论文。arXiv 主要收录英文论文，建议改用英文关键词，"
          "如 'multi-agent system'、'RAG'、'AI agent'。")
    return {}


def route_after_search(state: ResearchState) -> str:
    """搜索有结果 -> research；无结果 -> empty。

    关键设计：空数据绝不能喂给模型——模型会在输入缺失时"体面地编造"论文。
    """
    return "research" if state.get("papers") else "empty"


def research_node(state: ResearchState) -> dict:
    """研究员：把 papers 拼成文本喂给模型，提炼各篇贡献，返回 {"notes": 文本}。

    提示：user 消息 = "主题：{topic}\n论文列表：\n1. 标题...\n摘要..."；
    注意摘要是从 state["papers"] 里取的（已截断）。
    打印 "[研究员] 提炼要点:" 前缀。
    """
    # TODO 2
    paper_msg = ""
    for i,paper in enumerate(state.get("papers")):
        paper_msg += f"{i+1}.标题:{paper.get("title")}\n摘要:{paper.get("summary")}\n链接:{paper.get("url")}\n"
    messages = [{"role":"system","content":RESEARCHER_PROMPT},{"role":"user","content":f"主题{state.get("topic")}\n{paper_msg}"}]
    content = call_client(messages)
    print(f"[研究员] 提炼要点:\n{content}")
    return {"notes":content}


def write_node(state: ResearchState) -> dict:
    """写手：基于 topic + notes + comments 写初稿，返回 {"draft": 文本}。

    打回时 comments 要拼进 prompt。
    """
    messages = [{"role":"system","content":WRITER_PROMPT},{"role":"user","content":f"主题:{state.get("topic")},调研要点:{state.get("notes")},主编意见:{state.get("comments","")}"}]
    content = call_client(messages)
    print(f"[写手]短文草稿：\n{content}")
    return {"draft":content}
    


def review_node(state: ResearchState) -> dict:
    """主编：让模型输出 JSON 裁决，解析写入 state，返回 {"verdict", "comments", "rounds"}。

    提示：解析容错——失败时把错误反馈给模型重试（最多 3 次）；
    参考第四周 JSON mode + pydantic 思路（这里手写解析即可）。
    打印 "[主编] 评审: 通过/打回 - 意见"。
    """
    # TODO 4
    messages = [{"role":"system","content":REVIEWER_PROMPT},{"role":"user","content":f"初稿:{state.get("draft")}"}]
    required_keys = ["verdict","comments"]
    content = ""
    for _ in range(3):
        try:
            resp = get_client().chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    temperature=0.5,
                    response_format={"type":"json_object"}
                )
            content = resp.choices[0].message.content
            data = json.loads(content)
            if isinstance(data,dict):
                if not (required_keys - data.keys()):
                    return {"verdict":data["verdict"],"comments":data["comments"],"rounds":state.get("rounds",0) + 1}
                else:
                    messages.append({"role":"assistant","content":f"你刚刚输出的内容是{content},输出格式解析错误,请严格按照提示词中的格式要求输出json对象"})
        except JSONDecodeError as e:
            messages.append({"role":"assistant","content":f"你刚刚输出的内容是{content},json解析错误,请严格按照提示词中的格式要求输出json对象:{e}"})
    raise RuntimeError("reviewer输出解析失败，已达到最大尝试次数3次")




# ---------- 路由 ----------
def should_continue(state: ResearchState) -> str:
    """verdict == "revision" 且 rounds < MAX_ROUNDS -> "write"；否则 "end"。"""
    # TODO 5
    return "write" if state.get("verdict") == "revision" and state.get("rounds") < MAX_ROUNDS else "end"


# ---------- 组装：工作流图（路线 A：结构化字段） ----------
def build_graph():
    """组装图：START -> search -> research -> write -> review；review 条件边回 write 或 END。

    ⚠️ 第十周的血泪教训：记得加 write -> review 的边，否则 review 永远不会执行！
    """
    rs = StateGraph(ResearchState)
    rs.add_node("search",search_node)
    rs.add_node("empty", empty_node)
    rs.add_node("research",research_node)
    rs.add_node("write",write_node)
    rs.add_node("review",review_node)
    rs.add_edge(START,"search")
    rs.add_conditional_edges("search", route_after_search, {"research": "research", "empty": "empty"})
    rs.add_edge("empty", END)
    rs.add_edge("research","write")
    rs.add_edge("write","review")
    rs.add_conditional_edges("review",should_continue,{"write":"write","end":END})
    app = rs.compile()
    return app


# =====================================================================
# 阶段二：报告后的问答图（路线 B：add_messages reducer + ChatOpenAI）
#
# 为什么这里终于可以用 reducer？——问答阶段存在"会自然累积的聊天消息流"，
# 而工作流阶段（papers/notes/draft/verdict）是结构化字段，没有消息流。
# 两种状态模式用在同一项目里：字段给工作流，消息给对话。见 README「面试讲法」。
# =====================================================================

class ChatState(TypedDict):
    messages: Annotated[list, add_messages]     # 累积模式：聊天历史


chat_llm: ChatOpenAI | None = None


def get_chat_llm() -> ChatOpenAI:
    """惰性创建 ChatOpenAI（Route B：langchain 消息对象与 add_messages 原生兼容）。"""
    global chat_llm
    if chat_llm is None:
        chat_llm = ChatOpenAI(model=MODEL, api_key=load_api_key(), base_url=BASE_URL, temperature=0.5)
    return chat_llm


def chat_node(state: ChatState) -> dict:
    """单节点对话：ChatOpenAI 直接消费 state["messages"]（langchain 对象），返回新回复。

    返回 {"messages": [回复]}，add_messages reducer 自动把它追加进历史。
    """
    # TODO 7
    resp = get_chat_llm().invoke(state.get("messages"))
    return {"messages":[resp]}


def build_chat_graph():
    """组装问答图：START -> chat -> END（单节点；以后加工具时在此扩展 ToolNode）。"""
    # TODO 8
    cs = StateGraph(ChatState)
    cs.add_node("chat",chat_node)
    cs.add_edge(START,"chat")
    cs.add_edge("chat",END)
    app = cs.compile()
    return app



# ---------- 入口 ----------
def main() -> None:
    """REPL 两阶段：
    1. 输入主题 -> 工作流图（search/research/write/review）-> 保存 report.md
    2. 报告后问答阶段（多轮对话，验证 add_messages 历史累积）-> /exit 退出
    """
    # TODO 9
    print("输入要查找的论文主题即可获取论文简报，获取论文简报后直接输入问题即可展开对论文内容的讨论")
    try:
        while True:
            user_input = input("输入研究主题:")
            if user_input == "/exit":
                print("程序已退出")
                break
            else:
                app = build_graph()
                result = app.invoke({"topic":user_input,"rounds":0})
                if not result.get("draft"):
                    print("本次搜索未产出报告（可能未搜到相关论文）。请换一个关键词重新输入。")
                    continue          # 回到主题输入，不进入问答阶段
                REPORT_FILE.write_text(result.get("draft"),encoding="utf-8")
                print(f"最终裁决:{result.get("verdict")},经过{result.get("rounds")}轮")
                print(f"\n\n论文简报已保存到{REPORT_FILE},下面可以展开对本次论文内容的讨论啦")
                break
        # 工作流跑完后，进入问答阶段：
        chat_state = {"messages": [{"role": "system", "content":
            f"你刚刚完成了一份论文调研报告。报告的论文如下：\n"
            + "\n".join(f"- {p['title']} ({p['url']}): {p['summary'][:150]}" for p in result["papers"])
            + "\n用户会就这些论文提问，请基于论文信息回答，链接给原文 URL。"}]}
        chat_graph = build_chat_graph()
        while True:
            q = input("[问答] > ")
            if q in ("/exit", "exit"):
                break
            chat_state["messages"].append({"role": "user", "content": q})   # 追加用户消息
            chat_state = chat_graph.invoke(chat_state)                       # 上一轮 state 传回 → 历史累积
            print(chat_state["messages"][-1].content)
    except KeyboardInterrupt:
        print("程序已退出")
        return
                


if __name__ == "__main__":
    main()
