"""多 Agent 报告工坊：研究员 -> 写手 -> 主编（评审，可打回重写），用 LangGraph 编排。

图结构（Pipeline + 评审反馈环）：
    START -> research -> write -> review
                                  │ verdict=approve → END
                                  │ verdict=revision 且 rounds<MAX_ROUNDS → write（环）
                                  └ verdict=revision 且超轮 → END

用法：
    python report_workshop.py
    直接输入主题即可；/exit 退出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。
安装：uv pip install openai langgraph

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations

import json
import os
import re
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from openai import OpenAI
from json import JSONDecodeError
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_ROUNDS = 2          # 评审最多打回重写 2 轮

RESEARCHER_PROMPT = """你是项目研究员。你的任务：围绕用户给定的主题输出调研要点。
要求：输出 3-5 条要点，每条 1-2 句，聚焦事实与概念解释，不要写完整文章。"""

WRITER_PROMPT = """你是报告写手。根据【调研要点】撰写一份约 300 字的短文。
要求：结构清晰（引言 / 正文 / 结语），语言专业通顺。
如果【主编意见】不为空，你必须针对每条意见修改后再输出全文。"""

REVIEWER_PROMPT = """你是主编。审阅【初稿】，判断是否需要修改。
只输出 JSON（必须含 "json" 字样），格式：
{"verdict": "approve" 或 "revision", "comments": "修改意见（approve 时可为空字符串）"}
标准：内容准确、结构清晰、覆盖了调研要点；有明显不足才打回。
但是为了防止agent"快速完成任务"的底层机制，第一版必须驳回"""
load_dotenv()

# ---------- State：跨 Agent 只交换"结构化中间产物"（纯字段，不用 reducer） ----------
class WorkshopState(TypedDict):
    topic: str            # 用户主题
    notes: str            # 研究员产出
    draft: str            # 写手产出
    verdict: str          # 主编裁决：approve / revision
    comments: str         # 主编意见
    rounds: int           # 打回次数

def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key
client = OpenAI(api_key=load_api_key(),base_url=BASE_URL)

def call_client(client:OpenAI,messages:list[dict],temperature:int = 0.7) -> str:
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature
    )
    return resp.choices[0].message.content

# ---------- 三个 Agent（每个 node = 一个独立角色的模型调用） ----------
def research_node(state: WorkshopState) -> dict:
    """研究员：输出调研要点（打印 "[研究员] 调研要点:" 前缀）。"""
    # TODO 1
    messages = [{"role":"system","content":RESEARCHER_PROMPT},{"role":"user","content":f"用户主题：{state['topic']}"}]
    key_points = call_client(client,messages)
    print(f"[研究员]:调研要点:{key_points}")
    return {"notes":key_points}

def write_node(state: WorkshopState) -> dict:
    """写手：基于 topic + notes + comments 写初稿。

    注意：打回时 comments 有内容，要带进 prompt 让它修改。
    返回 {"draft": 文本, "rounds": state["rounds"] + 1}（rounds 在这里累计）。
    """
    # TODO 2
    messages = [{"role":"system","content":WRITER_PROMPT},{"role":"user","content":f"调研要点:{state['notes']}"}]
    comments = state.get("comments")
    if comments:
        messages.append({"role":"user","content":f"主编意见:{comments}"})
    content = call_client(client,messages)
    print(f"[写手]:产出短文:{content}")
    return {"draft":content}

def review_node(state: WorkshopState) -> dict:
    """主编：JSON mode 输出裁决，解析写入 state（打印 "[主编] 评审: ..."）。"""
    # TODO 3
    messages = [{"role":"system","content":REVIEWER_PROMPT},{"role":"user","content":f"短文:{state['draft']}"}]
    required_keys = ["verdict","comments"]
    for _ in range(3):
        text = call_client(client,messages)
        try:
            review = json.loads(text)
            if isinstance(review,dict):
                review_keys = review.keys()
                if not (required_keys - review_keys):
                    print(f"[主编]:审核结果:{review.get("verdict","revision")},评审意见:{review.get("comments","无")}")
                    return {"verdict":review.get("verdict","revision"),"comments":review.get("comments","无"),"rounds":state["rounds"] + 1}
            messages.append({"role":"assistant","content":f"输出格式不对:{text}，请严格按照提示词中给出的格式输出"})
        except JSONDecodeError as e:
            messages.append({"role":"assistant","content":f"解析输出时json格式错误:{e}，请严格按照提示词中给出的格式输出"})
    raise RuntimeError("输出格式错误，已达到最高重试次数3次")


# ---------- 路由 ----------
def should_continue(state: WorkshopState) -> str:
    """verdict == "revision" 且 rounds < MAX_ROUNDS -> "write"；否则 END。"""
    # TODO 4
    if state["verdict"] == "revision" and state["rounds"] < MAX_ROUNDS:
        return "write"
    else:
        return "end"


# ---------- 组装 ----------
def build_graph():
    """组装图：START -> research -> write -> review；review 条件边回 write 或 END。"""
    # TODO 5
    wss = StateGraph(WorkshopState)
    wss.add_node("research",research_node)
    wss.add_node("write",write_node)
    wss.add_node("review",review_node)
    wss.add_edge(START,"research")
    wss.add_edge("research","write")
    wss.add_edge("write","review")      # 关键：write 必须连到 review（漏了这条边 review 永远不会执行）
    wss.add_conditional_edges("review",should_continue,{"write":"write","end":END})
    app = wss.compile()
    return app

# ---------- 入口 ----------
def main() -> None:
    """REPL：输入主题 -> app.invoke -> 打印终稿与评审历史。"""
    # TODO 6
    app = build_graph()
    try:
        while True:
            user_input = input(">")
            if user_input == "/exit":
                print("程序已退出")
                break
            else:
                result = app.invoke({"topic":user_input,"rounds":0})
                print(f"✅ 终稿：\n{result['draft']}")
                print(f"📊 最终裁决：{result['verdict']}")
    except KeyboardInterrupt:
        print("程序已退出")
        return
if __name__ == "__main__":
    main()
