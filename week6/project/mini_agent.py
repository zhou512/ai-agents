"""手写 ReAct Agent：不依赖任何框架，也不使用 function calling API。

循环：调模型 -> 解析 Thought/Action -> 执行工具 -> 回填 Observation -> 再调模型 -> ...
直到模型输出 Final Answer 或达到 MAX_STEPS。

用法：
    python mini_agent.py
    /tools     列出可用工具
    /clear     清空对话历史
    /exit      退出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。

按 TODO 1 → TODO 5 的顺序完成。
"""
from __future__ import annotations
from json import JSONDecodeError
import ast
import datetime
import json
import operator
import os
import re
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import httpx
from openai import OpenAI
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_STEPS = 6

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


# ---------- 工具（工具本身不是本周重点，已实现；重点是 ReAct 循环） ----------
def safe_calculate(expression: str) -> float:
    """安全表达式求值（ast 白名单，绝不用 eval）。"""
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
    """查询城市当前天气（Open-Meteo，免费无 key）。"""
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
    """返回指定时区的当前时间。"""
    try:
        return datetime.datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return f"无效时区: {timezone}"


REGISTRY = {
    "get_weather": get_weather,
    "safe_calculate": safe_calculate,
    "get_time": get_time,
}


# ---------- ReAct 核心 ----------
def parse_react_output(text: str) -> dict:
    """从模型输出中解析 Thought / Action / Action Input / Final Answer。

    返回 dict，可能含键：thought / action / action_input / final_answer（缺什么就没那个键）。
    """
    result = {}
    text = text.replace("：", ":")   # 兼容模型输出全角冒号
    m = re.search(r"Thought:\s*(.+)", text)
    if m:
        result["thought"] = m.group(1).strip()
    m = re.search(r"Action:\s*(\w+)",text)
    if m:
        result["action"] = m.group(1)
    m = re.search(r"Action Input:\s*(\{.+?\})",text,re.DOTALL)
    if m:
        try:
            action = json.loads(m.group(1))
            result["action_input"] = action  #result["action_input"]是一个字典，里面存放工具需要的参数
        except JSONDecodeError as e:
            pass
    m = re.search(r"Final Answer:\s*(.+)",text,re.DOTALL)
    if m:
        result["final_answer"] = m.group(1).strip()
    return result


def build_react_prompt() -> str:
    """构造 ReAct system prompt：工具列表 + 严格格式 + 至少 1 个 few-shot 示例。

    参考 week6/README.md 第 5 节的完整示例。
    """
    # TODO 2
    system_prompt = """你是一个通过文本协议调用工具的智能体。

【重要：分工说明】你不需要真正执行任何工具，也没有执行工具的能力。
你只需要按下面的格式输出"调用请求"，系统会读取你的请求、代替你执行工具，
并把执行结果以 Observation 行返回给你。你根据 Observation 继续推理，直到得出答案。

可用工具：
- safe_calculate(expression: str): 计算数学表达式（幂用 **）
- get_weather(city: str): 查询城市当前天气（温度、天气码、风速）
- get_time(timezone: str = "Asia/Shanghai"): 获取 IANA 时区（如 Asia/Shanghai）的当前时间

输出格式（一次只输出一种，不要输出任何解释、说明或客套话）：
Thought: 你的推理过程
Action: 工具名
Action Input: JSON 格式参数，如 {"city": "北京"}

当你获得足够信息后输出：
Thought: 我现在知道了答案
Final Answer: 最终回答

示例（Observation 行是系统返回的，不需要你输出）：
用户问题：计算（2+3）*4
Thought: 需要计算（2+3）*4
Action: safe_calculate
Action Input: {"expression": "(2+3)*4"}
（系统执行后返回：Observation: 20）
Thought: 我已经知道（2+3）*4的结果了
Final Answer: （2+3）*4的结果是20
"""
    return system_prompt

def execute_tool(action_name:str,action_input:dict) -> str:
    f = REGISTRY.get(action_name)
    if not f:
        return f"未知工具:{action_name}"
    try:
        res = f(**action_input)
        return res
    except TypeError as e:
        return f"参数类型不匹配:{e}"

def react_step(client: OpenAI, messages: list[dict]) -> tuple[str | None, bool]:
    """单步：调模型 -> 解析 -> 执行工具 -> Observation 回填。

    返回 (最终回答 or None, 是否结束)：
    - final_answer -> (final_answer, True)
    - action -> 执行工具（出错也作为 Observation 回填），(None, False)
    - 解析失败 -> Observation 提示模型重新输出，(None, False)
    每步都要打印过程：Thought / Action / Observation。
    """
    # TODO 3
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1
    )
    text = resp.choices[0].message.content
    messages.append({"role": "assistant", "content": text})
    result = parse_react_output(text)
    if not result:
        print("模型输出解析失败")
        messages.append({"role":"user","content":"Observation: 无法解析你的输出，请严格按照格式重新输出"})
        return (None,False)
    final_answer = result.get("final_answer")
    if final_answer:
        print(f"Thought: {result.get('thought', '')}")
        print(f"Final Answer: {final_answer}")
        return (final_answer, True)
    action_name = result.get("action")
    if action_name:
        action_input = result.get("action_input")
        if action_input is None:
            messages.append({"role": "user", "content": "Observation: 缺少 Action Input，请按格式重新输出"})
            return (None, False)
        # 只把 execute_tool 放进 try；打印放外面（打印自身的错误不该被当成工具错误）
        try:
            tool_result = execute_tool(action_name, action_input)
        except Exception as e:
            tool_result = f"工具执行出错: {e}"
        # 字段一律用 .get 防御缺失（模型可能跳过某个字段）
        print(f"Thought: {result.get('thought', '')}")
        print(f"Action: {action_name}")
        print(f"Action Input: {json.dumps(action_input)}")
        print(f"Observation: {tool_result}")
        messages.append({"role": "user", "content": f"Observation: {tool_result}"})
        return (None, False)


def react_loop(client: OpenAI,messages:list[dict]) -> str:
    """完整循环：直到 Final Answer 或 MAX_STEPS。"""
    # TODO 4
    for _ in range(MAX_STEPS):
        resp,valid = react_step(client,messages)
        if valid:
            return f"已得到最终回答：{resp}"
    return f"达到最大步数 {MAX_STEPS}，未能得到最终回答"


# ---------- 入口 ----------
def load_api_key() -> str:
    """从环境变量读 Key，缺失时给出明确错误。"""
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key


def main() -> None:
    """REPL：输入问题 -> react_loop；命令 /tools /clear /exit；友好错误处理。"""
    try:
        key = load_api_key()
    except ValueError as e:
        print(e)
        return
    client = OpenAI(api_key=key,base_url=BASE_URL)
    tools_description = {"safe_calculate(expression:str)":"安全计算器,输入表达式得到计算结果","get_weather(city:str)":"查询一个城市的天气码，温度，时间","get_time(timezone:str)":"查询一个时区的当前时间，参数为IANA时区，如Asia/Shanghai"}
    messages = [{"role":"system","content":f"{build_react_prompt()}"}]
    try:
        while True:
            user_input = input("用户:")
            if user_input == "/tools":
                for td_key,td_value in tools_description.items():
                    print(f"工具名称:{td_key}")
                    print(f"工具功能:{td_value}")
            elif user_input == "/clear":
                messages = [messages[0]]
                print("聊天记录已清空")
            elif user_input == '/exit':
                print("程序已退出")
                break
            else:
                messages.append({"role":"user","content":user_input})
                try:
                    final_answer = react_loop(client,messages)
                    print(f"最终回答:{final_answer}")
                except Exception as e:
                    print(f"程序出错:{e}")
                    messages.pop()
    except KeyboardInterrupt as e:
        print("程序已退出")
        return
                         


if __name__ == "__main__":
    main()
