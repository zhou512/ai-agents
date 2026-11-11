"""带长期记忆的对话助手：检索注入 + 事实抽取 + 文件持久化。

流程：
1. 启动时从 memories.json 加载记忆库（VectorStore）
2. 每轮提问：检索 top-k 相关记忆 -> 拼进 system 提示词 -> 模型回答
3. 回答后：让模型抽取"值得记住的事实"（JSON）-> 相似度去重 -> 入库 -> 持久化

用法：
    python memory_chat.py
    /memories   查看已记住的信息
    /forget     清空记忆库
    /exit       退出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
from json import JSONDecodeError
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MEMORY_FILE = Path(__file__).parent / "memories.json"
TOP_K = 3
DEDUP_THRESHOLD = 0.85          # 相似度超过它就认为是重复

SYSTEM_TEMPLATE = """你是一个乐于助人的对话助手。

以下是用户过去提到过的信息（可能相关，也可能不相关，请自行判断）：
{context}

回答要自然简洁。"""


# ========== 向量与记忆库（已实现，直接使用；原理见第七周 README） ==========
def char_ngrams(text: str, n: int = 2) -> list[str]:
    text = text.lower()
    return [text[i:i+n] for i in range(len(text) - n + 1)]


def simple_embed(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for g in char_ngrams(text):
        counts[g] = counts.get(g, 0) + 1
    norm = math.sqrt(sum(v*v for v in counts.values()))
    if norm == 0:
        return {}
    return {k: v / norm for k, v in counts.items()}


def cosine_similarity(v1: dict, v2: dict) -> float:
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) | set(v2))
    n1 = math.sqrt(sum(x*x for x in v1.values()))
    n2 = math.sqrt(sum(x*x for x in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


class VectorStore:
    """极简向量库，持久化到 JSON。"""

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, text: str) -> None:
        self.items.append({"text": text, "vector": simple_embed(text)})

    def search(self, query: str, k: int = 3) -> list[tuple[str, float]]:
        qv = simple_embed(query)
        scored = [(item["text"], cosine_similarity(qv, item["vector"])) for item in self.items]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps([item["text"] for item in self.items], ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        for text in json.loads(path.read_text(encoding="utf-8")):
            self.add(text)

    def clear(self) -> None:
        self.items = []


# ========== 记忆架构（本周核心，TODO） ==========
def retrieve_context(store: VectorStore, question: str, k: int = TOP_K) -> str:
    """检索 top-k 记忆，拼成注入上下文的参考材料文本。

    要求：
    - 无记忆时返回 "（暂无记忆）"
    - 有记忆时每行一条：f"- {text}（相关度 {score:.2f}）"
    """
    # TODO 1
    memories_k = store.search(question,k)
    if not memories_k:
        return "(暂无记忆)"
    res_str = ""
    for g in memories_k:
        text,score = g
        res_str += f"- {text} (相关度{score:.2f})\n"
    return res_str


def build_messages(question: str, context:str) -> list[dict]:
    """构造 messages：system 用 SYSTEM_TEMPLATE 注入 context，user 放问题。"""
    # TODO 2
    system_content = SYSTEM_TEMPLATE.format(context=context)
    messages = [{"role":"system","content":system_content},{"role":"user","content":question}]
    return messages


def chat_once(client: OpenAI, question: str, store: VectorStore) -> str:
    """完整一轮：检索 -> 构造 -> 回答。

    要求：
    - 打印 "📎 检索到的记忆: ..."（空则打印 "（无相关记忆）"），便于观察注入效果
    - resp = client.chat.completions.create(model=MODEL, messages=..., temperature=0.7)
    - 返回回答文本
    """
    # TODO 3
    searched_memories = retrieve_context(store,question)
    print(f"📎 检索到的记忆: {searched_memories}")
    messages = build_messages(question,searched_memories)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.7
    )
    return resp.choices[0].message.content


def extract_facts(client: OpenAI, question: str, answer: str, max_retries: int = 2) -> list[str]:
    """让模型从对话中抽取值得长期记住的事实，返回字符串列表。

    要求：
    - system 提示："从对话中提取值得长期记住的用户信息（名字、偏好、重要事实）。
      只输出 JSON 对象，键值为"facts"或"memories",值为字符串数组 如 {\"facts\":[\"用户叫小明\", \"用户喜欢喝咖啡\"]}。没有值得记住的就输出 []。"
    - user 消息包含问题与回答
    - response_format={"type": "json_object"} 注意：prompt 必须含 "json" 字样
    - json.loads 解析失败时重试（把模型错误输出反馈给它），最多 max_retries 次
    - 解析出的是 dict（如 {"facts": [...]} 或 {"memories": [...]}），取第一个 list 值；失败返回 []
    """
    # TODO 4
    messages = [{"role":"system","content":"你是一个有很强提取信息和总结能力的助手，你将会收到一段对话，你需要从对话中提取值得长期记住的用户信息（如名字，用户的偏好和重要的事实，对话主题等），但只输出 JSON 对象，键值为'facts'或'memories',值为字符串数组 如 {\"facts\":[\"用户叫小明\", \"用户喜欢喝咖啡\"]}，如果没有值得记住的，就输出[]"},
                {"role":"user","content":question},
                {"role":"assistant","content":answer}]
    for _ in range(max_retries):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3,
            response_format={"type":"json_object"}
        )
        ans_json = resp.choices[0].message.content
        try:
            parse = json.loads(ans_json)
            for value in parse.values():
                if isinstance(value,list):
                    return value
            return []
        except JSONDecodeError as e:
            messages.append({"role":"user","content":f"输出格式解析出错了:{e}，请调整输出格式"})
    raise RuntimeError(f"抽取信息失败，已尝试{max_retries}")


def save_facts(store: VectorStore, facts: list[str]) -> int:
    """事实入库（去重 + 持久化），返回实际新增条数。

    要求：
    - 与已有记忆相似度 > DEDUP_THRESHOLD 的跳过（先查 search(fact, k=1)）
    - 新增的 store.add(fact)，最后 store.save(MEMORY_FILE)
    """
    count = 0
    for fact in facts:
        # 库非空时先查重；相似度超阈值就跳过
        if store.items:
            _, sim = store.search(fact, k=1)[0]
            if sim > DEDUP_THRESHOLD:
                continue
        store.add(fact)
        count += 1
    store.save(MEMORY_FILE)   # 循环结束后统一保存一次
    return count              # 所有事实都处理完再返回

def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key


def main() -> None:
    """加载记忆 -> REPL：每轮 = chat_once + extract_facts + save_facts。命令 /memories /forget /exit。"""
    # TODO 6
    try:
        key = load_api_key()
    except ValueError:
        print("未找到 API Key")
        return
    client = OpenAI(api_key=key,base_url=BASE_URL)
    store = VectorStore()
    store.load(MEMORY_FILE)
    try:
        while True:
            user_input = input("用户:")
            if user_input == "/memories":
                for item in store.items:
                    print(item.get("text"))
            elif user_input == "/forget":
                store.clear()
                store.save(MEMORY_FILE)
            elif user_input == "/exit":
                print("程序已退出")
                break
            else:
                answer = chat_once(client,user_input,store)
                print(answer)
                try:
                    inf_list = extract_facts(client,user_input,answer)
                    save_facts(store,inf_list)
                except RuntimeError as e:
                    print(e)
    except KeyboardInterrupt:
        print("程序已退出")

                


if __name__ == "__main__":
    main()
