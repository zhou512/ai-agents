"""工具版聊天助手：LLM + 3 个真实工具（天气/时间/安全计算）的 Agent 最小形态。

用法：
    python tool_agent.py
    /tools     列出可用工具
    /clear     清空对话历史
    /exit      退出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。

按 TODO 1 → TODO 7 的顺序完成。
"""
from __future__ import annotations
import sys
from pathlib import Path
import argparse
import ast
from datetime import datetime
import json
import operator
import os
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from dotenv import load_dotenv
import httpx
from openai import OpenAI
load_dotenv()

""" project_root = Path(__file__).parent.parent
sys.path.append(str(project_root)) """

from tools import get_weather,safe_calculate,execute_tool
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_TURNS = 5
SYSTEM_PROMPT = "你是一个乐于助人的助手。需要外部信息时使用提供的工具，工具结果会以消息形式返回给你。回答简洁准确。"

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

# 工具 schema（模型靠 description 决定用哪个工具）
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气（温度、天气码、风速）",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string", "description": "城市名，如 北京"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取指定时区的当前日期和时间",
            "parameters": {
                "type": "object",
                "properties": {"timezone": {"type": "string", "description": "IANA 时区名，如 Asia/Shanghai，默认 Asia/Shanghai"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_calculate",
            "description": "计算数学表达式（仅支持四则运算和幂运算）",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string", "description": "数学表达式，如 (2+3)*4,幂运算的运算符用'**'而不是'^'"}},
                "required": ["expression"],
            },
        },
    },
]


# ---------- 工具实现 ----------

def get_time(timezone: str = "Asia/Shanghai") -> str:
    """返回指定时区的当前时间；时区无效时给出提示而不是崩溃。"""
    # TODO 3
    try:
        tz = ZoneInfo(timezone)
        now = datetime.now(tz)
        return now.strftime("%Y-%m-%d %H:%M:%S")
    except ZoneInfoNotFoundError:
        return f"无效时区:{timezone}"


# ---------- 工具分发 ----------
REGISTRY = {
    "get_weather":get_weather,
    "safe_calculate":safe_calculate,
    "get_time":get_time
}

# ---------- Agent 循环 ----------

def agent_turn(client: OpenAI, messages: list[dict]) -> tuple[bool, str | None]:
    """单轮：调模型。

    返回 (是否结束, 最终回答)：
    - 模型无 tool_calls -> (True, msg.content)
    - 有 tool_calls -> 打印 "🔧 调用工具: name(args) -> 结果"，
      逐个执行并回填 tool 消息，返回 (False, None)
    """
    # TODO 5
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1,
        tools=TOOLS
    )
    msg = resp.choices[0].message
    if not msg.tool_calls:
        messages.append(msg)
        return (True,msg.content)
    messages.append(msg)
    for tc in msg.tool_calls:
        name = tc.function.name
        args = tc.function.arguments
        try:
            result = execute_tool(REGISTRY,name,args)
        except Exception as e:
            result = f"工具执行失败:{e}"
        messages.append({"role":"tool","content":str(result),"tool_call_id":tc.id})
        print(f"🔧 调用工具: {name}({args}) -> 结果:{result}")
    return (False,None)


def run_agent(client: OpenAI, messages:list[dict]) -> str:
    """循环 agent_turn 直到得到最终回答或达到 MAX_TURNS。"""
    # TODO 6
    for turn in range(MAX_TURNS):
        valid,res = agent_turn(client,messages)
        if valid:
            return res
    raise RuntimeError(f"达到最大工具调用轮数（{MAX_TURNS}），未能生成最终回答")

def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未成功载入apikey")
    return key

# ---------- 入口 ----------
def main() -> None:
    """REPL：输入问题 -> run_agent；命令 /tools /clear /exit；友好错误处理。"""
    # TODO 7
    tools_description = []
    try:
        api_key = load_api_key()
    except ValueError as e:
        print(e)
        return
    client = OpenAI(api_key=api_key,base_url=BASE_URL)
    messages = [{"role":"system","content":SYSTEM_PROMPT}]
    for i in range(len(TOOLS)):
        part_description = f"工具名称：{TOOLS[i]['function']['name']}\n工具描述:{TOOLS[i]['function']['description']}"
        tools_description.append(part_description)

    tools_text = "\n".join(tools_description)
    try:
        while True:
            user_msg = input("用户：")
            if user_msg == "/tools":
                print(tools_text)
            elif user_msg == "/clear":
                messages = [messages[0]]
                print("历史聊天记录已清空")
            elif user_msg == "/exit":
                break
            else:
                try:
                    messages.append({"role":"user","content":user_msg})
                    resp = run_agent(client,messages)
                    print(resp)
                except RuntimeError as e:
                    print(e)
                    messages.pop()
                    continue
                except Exception as e:
                    print(f"发生未知错误：{e}")
                    messages.pop()
                    continue
    except KeyboardInterrupt:
        print("程序已退出")
        return


if __name__ == "__main__":
    main()
