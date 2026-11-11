"""DeepSeek 流式聊天 CLI：支持流式输出、历史管理、费用统计。

用法：
    python chat_cli.py

    /help          显示命令列表
    /clear         清空对话历史
    /cost          显示累计 token 与费用
    /temp 0.9      调整 temperature
    /exit          退出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或在程序同目录创建 .env 文件（内容一行：DEEPSEEK_API_KEY=sk-...）

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations
from dotenv import load_dotenv
import os
import sys
from pathlib import Path
import time

from openai import OpenAI, OpenAIError, AuthenticationError
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
SYSTEM_PROMPT = "你是一个乐于助人的助手，回答简洁准确。"
MAX_COUNT = 20

# 价格（美元 / 每百万 token）：(输入价, 输出价)。价格会变，以官方定价页为准。
PRICES: dict[str, tuple[float, float]] = {
    "deepseek-chat": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}


# ---------- 工具函数 ----------
def load_api_key() -> str:
    """从环境变量 DEEPSEEK_API_KEY 读取 Key；没有则尝试解析同目录 .env 文件。

    .env 文件格式（每行一个配置，用 = 分隔）：
        DEEPSEEK_API_KEY=sk-xxxxxxxx

    要求：都没有时 raise ValueError(
        "未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY，或在项目目录创建 .env 文件")
    """
    # TODO 1
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY，或在项目目录创建 .env 文件")
    return key


def make_client() -> OpenAI:
    """创建 OpenAI 客户端（api_key 用 load_api_key()，base_url 用 BASE_URL）。"""
    # TODO 2
    api_key = load_api_key()
    return OpenAI(api_key=api_key,base_url=BASE_URL)

def is_chinese(char:str) -> bool:
    return '\u4e00' <= char <= '\u9fff'

def estimate_tokens(text: str) -> int:
    """粗略估算 token 数（仅用于理解概念，非精确）：
    - 中文字符约 1.5 token/个
    - 其他字符（英文/数字/符号）约 0.3 token/个

    期望: estimate_tokens("你好") -> 3
    期望: estimate_tokens("hello") -> 2
    期望: estimate_tokens("你好 hello") -> 5
    提示：先统计中文字符数，再统计其他字符数，用 int() 取整。
    """
    res = 0
    for char in text:
        if is_chinese(char):
            res += 1.5
        else:
            res += 0.3
    return int(res)

def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """按 PRICES[MODEL] 计算本次调用的美元费用（输入/输出分开计价，除以 1e6）。"""
    # TODO 3
    price = (prompt_tokens * PRICES[MODEL][0] + completion_tokens * PRICES[MODEL][1]) /1e6
    return price

def chat_stream(client: OpenAI, messages: list[dict], temperature: float) -> tuple[str, int, int]:
    """流式对话：逐块打印，返回 (完整回复, 输入token, 输出token)。

    提示：
    - create 时加 stream=True 和 stream_options={"include_usage": True}
      （DeepSeek 兼容 OpenAI，最后一个 chunk 会带 usage）
    - for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta: print(delta, end="", flush=True)
    - usage 读取：chunk.usage（只有最后一个 chunk 非 None），
      取 usage.prompt_tokens / usage.completion_tokens；
      如果始终为 None，返回 0（代码里做好防御即可）
    """
    # TODO 4
    last_error:OpenAIError | None = None
    for attempt in range(3):
        try:
            stream = client.chat.completions.create(model=MODEL,messages=messages,temperature=temperature,stream=True,stream_options={"include_usage":True})
            resp = ""
            p_tokens = 0
            c_tokens = 0
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    resp += delta
                    print(delta,end="",flush=True)
                if chunk.usage:
                    p_tokens = chunk.usage.prompt_tokens
                    c_tokens = chunk.usage.completion_tokens
            if not resp:
                raise ValueError("生成回复失败")
            return (resp,p_tokens,c_tokens)
        except AuthenticationError:
            raise
        except OpenAIError as e:
            last_error = e
            wait = 2 ** attempt
            print(f"第{attempt+1}次失败:{e},等待{wait}秒后重试")
            time.sleep(wait)
    raise last_error

def trim_message_by_count(messages:list[str],max_count:int) -> list[str]:
    if len(messages) <= max_count:
        return messages
    else:
        sys_msg = messages[0] if messages and messages[0]["role"] == "system" else None
        if sys_msg:
            new_messages = [messages[0]] + messages[-(max_count-1):]
        else:
            new_messages = messages[-max_count:]
        return new_messages


# ---------- 主循环 ----------
def run_repl(client: OpenAI) -> None:
    """交互主循环。

    要求：
    - messages 初始为 [{"role": "system", "content": SYSTEM_PROMPT}]
    - 循环 input("你> ")；空输入跳过
    - 命令分发：
        /help -> 打印命令列表
        /clear -> messages 重置为只剩 system
        /cost -> 打印累计 token 与费用
        /temp <值> -> 更新 temperature（非法值给出提示）
        /exit -> break
    - 普通输入：追加 user 消息 -> chat_stream -> 追加 assistant 回复 -> 累计 token/费用
    - 输出本轮 token 数，如：f"（本轮: 输入 {pt} / 输出 {ct} token）"
    - 捕获 KeyboardInterrupt（Ctrl+C）优雅退出
    """
    # TODO 5
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    pt = 0
    ct = 0
    temperature = 0.7
    try:
        while True:
            user_msg = input("你> ")
            if not user_msg:
                continue
            if user_msg == "/help":
                print("/clear -> messages 重置为只剩 system\n/cost -> 打印累计 token 与费用\n/temp <值> -> 更新 temperature（非法值给出提示）\n/exit -> break\n")
            elif user_msg == "/clear":
                messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            elif user_msg == "/cost":
                print(f"累计token:{pt+ct},累计费用：{estimate_cost(pt,ct)}")
            elif user_msg.startswith("/temp"):
                parts = user_msg.split()
                if len(parts) >= 2:
                    try:
                        value = float(parts[1])
                        if value < 0 or value > 1.5:
                            print("temperature参数不在合法范围内（0~1.5）")
                        else:
                            temperature = value
                    except ValueError as e:
                        print("数值格式不正确")
                else:
                    print("缺少参数")
            elif user_msg == "/exit":
                break
            else:
                messages.append({"role":"user","content":user_msg})
                try:
                    reply,pt_in,pt_out = chat_stream(client,messages,temperature)
                    messages.append({"role":"assistant","content":reply})
                    messages = trim_message_by_count(messages,MAX_COUNT)
                    pt += pt_in
                    ct += pt_out
                    print(f"\n本轮输入:{pt_in}tokens,输出:{pt_out}tokens")
                except OpenAIError as e:
                    print(f"API错误:{e},跳过本轮")
                    messages.pop()
                    continue
    except KeyboardInterrupt:
        print("程序已退出")




def main() -> None:
    """入口：加载 Key -> 创建客户端 -> run_repl。Key 缺失时打印友好提示而非 traceback。"""
    try:
        client = make_client()
    except ValueError as e:
        print(e)
        return
    run_repl(client)
    


if __name__ == "__main__":
    main()
