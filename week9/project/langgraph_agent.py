"""图版工具 Agent：用 LangGraph 把"工具调用循环"表达成图。

图结构：
    START -> call_model --有 tool_calls--> execute_tools --+
             │                                             │
             └--------无 tool_calls--> END  ◄──────────────┘（环）

用法：
    python langgraph_agent.py
    /tools   查看工具
    /exit    退出
    直接输入问题

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。
安装：uv pip install langgraph openai

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations

import ast
import datetime
import json
import operator
import os
import re
from typing import TypedDict
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import httpx
from langgraph.graph import StateGraph, START, END
from openai import OpenAI
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_TURNS = 6

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key


client = OpenAI(api_key=load_api_key(),base_url=BASE_URL)
# ---------- 工具（与第六周相同；重点是它们如何进图） ----------
def safe_calculate(expression: str) -> float:
    OPS = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow}

    def eval_node(node):
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            return OPS[type(node.op)](eval_node(node.left), eval_node(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = eval_node(node.operand)
            return val if isinstance(node.op, ast.UAdd) else -val
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")

    return eval_node(ast.parse(expression, mode="eval"))


def get_weather(city: str) -> str:
    geo = httpx.get(GEO_URL, params={"name": city, "count": 1, "language": "zh"}, timeout=10).json()
    results = geo.get("results")
    if not results:
        return f"未找到城市: {city}"
    lat, lon = results[0]["latitude"], results[0]["longitude"]
    fc = httpx.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "auto",
    }, timeout=10).json()
    cur = fc["current"]
    return f"{city}: 温度{cur['temperature_2m']}°C，天气码{cur['weather_code']}，风速{cur['wind_speed_10m']} km/h"


def get_time(timezone: str = "Asia/Shanghai") -> str:
    try:
        return datetime.datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return f"无效时区: {timezone}"


TOOLS_SCHEMA = [
    {"type": "function", "function": {"name": "get_weather",
                                      "description": "查询城市当前天气",
                                      "parameters": {"type": "object",
                                                     "properties": {"city": {"type": "string", "description": "城市名，如 北京"}},
                                                     "required": ["city"]}}},
    {"type": "function", "function": {"name": "safe_calculate",
                                      "description": "计算数学表达式（幂用 **）",
                                      "parameters": {"type": "object",
                                                     "properties": {"expression": {"type": "string", "description": "表达式，如 (2+3)*4"}},
                                                     "required": ["expression"]}}},
    {"type": "function", "function": {"name": "get_time",
                                      "description": "获取 IANA 时区当前时间",
                                      "parameters": {"type": "object",
                                                     "properties": {"timezone": {"type": "string", "description": "如 Asia/Shanghai"}}}}},
]

TOOL_REGISTRY = {"safe_calculate": safe_calculate, "get_weather": get_weather, "get_time": get_time}


# ---------- State（图里流动的数据） ----------
class AgentState(TypedDict):
    # 用普通 list 字段（覆盖模式），不用 add_messages：
    # add_messages 会把 dict 转成 langchain Message 对象，和裸 openai SDK 冲突
    # （langgraph 自动装了 langchain-core）。普通字段保证全程纯 dict，和手写一致。
    messages: list
    turns: int                                  # 防止无限循环的计数器


# ---------- 图的节点（TODO 核心） ----------
def call_model(state: AgentState) -> dict:
    """调 LLM。返回 {"messages": [assistant 消息 dict]}。

    注意：assistant 消息要转成纯 dict（OpenAI API 的 wire 格式），且**不能动 state 本身**，
    只返回要更新的部分。需要 client —— 用全局单例（模块级创建一次）。
    """
    # TODO 2
    resp = client.chat.completions.create(
        model=MODEL,
        messages=state["messages"],   # 纯 dict 列表，openai SDK 直接可用
        temperature=0.3,
        tools=TOOLS_SCHEMA
    )
    msg = resp.choices[0].message
    # 手工构造 wire 格式的 assistant dict（不要 model_dump：会带 refusal/audio 等多余字段）
    assistant_dict: dict = {"role": "assistant"}
    if msg.content:    # 工具调用消息的 content 是 None/空——省略该字段而不是发 None
        assistant_dict["content"] = msg.content
    if msg.tool_calls:
        assistant_dict["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    # 覆盖模式下必须返回"完整历史 + 新消息"
    return {"messages": state["messages"] + [assistant_dict]}


def execute_tools(state: AgentState) -> dict:
    """执行最后一条 assistant 消息里的 tool_calls，回填 tool 消息。

    提示：
    - last = state["messages"][-1]
    - 对 last["tool_calls"] 里的每个 tc：
        name = tc["function"]["name"]; args = json.loads(tc["function"]["arguments"])
        调用 TOOL_REGISTRY[name](**args)，出错时结果 = f"工具执行失败: {e}"
        tool 消息：{"role": "tool", "tool_call_id": tc["id"], "content": str(结果)}
    - 返回 {"messages": [所有 tool 消息]}；顺带把 turns + 1
    """
    tool_messages = []
    last = state["messages"][-1]
    if last.get("tool_calls"):
        for tc in last["tool_calls"]:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"])
            try:
                result = TOOL_REGISTRY[name](**args)
            except Exception as e:
                result = f"工具执行失败:{e}"
            # content 必须是字符串：工具返回数字/浮点也要 str()（API 严格校验）
            tool_messages.append({"role": "tool", "content": str(result), "tool_call_id": tc["id"]})
        # 覆盖模式：返回完整历史 + tool 消息
        return {"messages": state["messages"] + tool_messages, "turns": state["turns"] + 1}
    else:
        # 防御：没有 tool_calls 时保持历史不变（不要返回空列表清空它）
        return {"messages": state["messages"]}

def should_continue(state: AgentState) -> str:
    """最后一条消息有 tool_calls 且 turns < MAX_TURNS -> "tools"；否则 END。

    提示：last = state["messages"][-1]；last.get("tool_calls") 非空即有工具要执行
    """
    # TODO 4
    last = state["messages"][-1]
    if last.get("tool_calls") and state["turns"] < MAX_TURNS:
        return "tools"
    else:
        return "end"


# ---------- 组装 ----------
def build_graph():
    """构建并编译图。

    结构：
        START -> call_model
        call_model 条件边：{"tools": "execute_tools", "end": END}
        execute_tools -> call_model（形成环）
    返回编译后的 app。
    """
    # TODO 5
    agent_s = StateGraph(AgentState)
    agent_s.add_node("call",call_model)
    agent_s.add_node("tools",execute_tools)
    agent_s.add_edge(START,"call")
    agent_s.add_conditional_edges("call",should_continue,{"tools":"tools","end":END})
    agent_s.add_edge("tools","call")
    app = agent_s.compile()
    return app


# ---------- 入口 ----------



def main() -> None:
    """REPL：输入问题 -> app.invoke -> 打印最终回答。"""
    app = build_graph()
    try:
        while True:
            user_input = input(">")
            if user_input == "/tools":
                for tool in TOOLS_SCHEMA:
                    print(f"工具名称:{tool["function"]["name"]}")
                    print(f"工具功能:{tool['function']['description']}")
            elif user_input == "/exit":
                print("程序已退出")
                break
            else:
                reply = app.invoke({"messages":[{"role":"user","content":user_input}],"turns":0})
                print(reply["messages"][-1]["content"])
    except KeyboardInterrupt:
        print("程序已退出")
        return

if __name__ == "__main__":
    main()
