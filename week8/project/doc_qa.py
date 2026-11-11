"""个人文档问答 Agent（RAG 最小实现）：索引 -> 检索 -> 基于片段回答，带命中率评估。

用法：
    python doc_qa.py
    /ingest     扫描 docs/ 目录（.txt/.md），分块 + 索引，保存到 index.json
    /sources    显示最近一次回答依据的文档片段
    /eval       用内置测试问题集评估检索命中率（hit rate@k）
    /exit       退出
    直接输入问题即可提问

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或项目目录创建 .env。docs/ 目录放你的笔记文件。

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
DOC_DIR = Path(__file__).parent / "docs"
INDEX_FILE = Path(__file__).parent / "index.json"
TOP_K = 3
MAX_CHARS = 120          # 每块最大字符数（可调）
OVERLAP_CHARS = 20       # 块间重叠

# 内置测试问题集：每个问题都要知道答案在哪个文件里（评估用，可扩充）
QA_PAIRS = [
    {"question": "装饰器的本质是什么？", "answer_source": "notes_python.txt"},
    {"question": "什么是闭包？", "answer_source": "notes_python.txt"},
    {"question": "async/await 解决了什么问题？", "answer_source": "notes_python.txt"},
]


# ---------- 分块与索引（零件；原理见 README） ----------
def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"(?<=[。！？.!?])", text) if p.strip()]


def chunk_by_sentences(text: str, max_chars: int = MAX_CHARS, overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    sentences = split_sentences(text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current)
            current = current[-overlap_chars:] + s
        else:
            current += s
    if current:
        chunks.append(current)
    return chunks


def simple_embed(text: str) -> dict[str, float]:
    text = text.lower()
    counts: dict[str, float] = {}
    for i in range(len(text) - 1):
        g = text[i:i+2]
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


class DocIndex:
    """文档块索引：块 + 向量 + source，持久化到 JSON。"""

    def __init__(self) -> None:
        self.chunks: list[dict] = []   # [{"source", "text", "vector"}]

    def add(self, source: str, text: str) -> None:
        self.chunks.append({"source": source, "text": text, "vector": simple_embed(text)})

    def search(self, question: str, k: int = TOP_K) -> list[dict]:
        qv = simple_embed(question)
        scored = sorted(self.chunks, key=lambda c: cosine_similarity(qv, c["vector"]), reverse=True)
        return [{"source": c["source"], "text": c["text"]} for c in scored[:k]]

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(
            [{"source": c["source"], "text": c["text"]} for c in self.chunks],
            ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        for c in json.loads(path.read_text(encoding="utf-8")):
            self.add(c["source"], c["text"])


# ---------- RAG 流程（本周核心，TODO） ----------
def is_txt_or_md(file:Path) -> bool:
    if not file.is_file() or file.name.startswith("."):
        return  False
    suffix = file.suffix.lower()
    if suffix == ".txt" or suffix == ".md":
        return True
    
def load_docs(doc_dir: Path = DOC_DIR) -> list[dict]:
    """读取 doc_dir 下所有 .txt/.md 文件，返回 [{"source": 文件名, "text": 全文}]。

    目录不存在或没有文件时给出明确提示（返回空列表并打印）。
    """
    # TODO 1
    docs = []
    if not doc_dir.is_dir():
        print("目录不存在")
        return []
    for f in doc_dir.iterdir():
        if is_txt_or_md(f):
            text = f.read_text(encoding="utf-8")
            docs.append({"source":f.name,"text":text})
    if not docs:
        print("目录下没有.txt/.md文件")
    return docs

def split_documents(docs: list[dict]) -> list[dict]:
    """给每个文档分块，返回 [{"source", "text"}, ...]（用 chunk_by_sentences）。"""
    # TODO 2
    sourced_docs = []
    for doc in docs:
        chunks = chunk_by_sentences(doc.get("text"))
        for chunk in chunks:
            sourced_docs.append({"source":doc.get("source"),"text":chunk})
    return sourced_docs

def build_index(chunks: list[dict]) -> DocIndex:
    """把分块构建成 DocIndex 并保存到 INDEX_FILE，打印 "已索引 N 个片段"。
    chunks:[{"source":...,"text":...}]"""
    # TODO 3
    doc_index = DocIndex()
    for chunk in chunks:
        doc_index.add(chunk.get("source"),chunk.get("text"))
    count = len(doc_index.chunks)
    print(f"已索引{count}个片段")
    doc_index.save(INDEX_FILE)
    return doc_index


def make_synthesis_prompt(chunks: list[dict]) -> str:
    """构造基于片段回答的 system prompt（练习 4 的完整版，含来源标注与防幻觉要求）。"""
    # TODO 4
    fragments = []
    contexts = ""
    for i,chunk in enumerate(chunks):
        fragment = f"【片段{i+1} | 来源:{chunk.get("source")}】\n{chunk.get("text")}"
        fragments.append(fragment)
    contexts = "\n\n".join(fragments)
    sys_prompt = f"""你是一位文档信息回答助手，有着很强的信息检索和总结能力。要求：
    1.你只能从下面的片段中获取信息来回答用户的问题，不能编造（也就是说下面的片段是你唯一的信息来源）。
    2.在回答末尾时，要标注好你的答案的来源。
    3.如果片段中的信息不足以回答问题，则回复"文档中没有相关信息"，不需要猜测和编造
    下面是你的信息:
    {contexts}
    一个例子：假设信息中有这样一段"【片段5：小明今年25岁】 | 来源：小明.txt"
    用户问：小明今年几岁
    你的回答需要包括：小明今年25岁。来源：小明.txt
    """
    return sys_prompt


def retrieve_and_answer(client: OpenAI, index: DocIndex, question: str) -> tuple[str, list[dict]]:
    """检索 top-k 块 -> 构造 prompt -> 模型回答。

    返回 (回答文本, 本轮用到的块列表)。回答时打印 "📎 依据片段: ..."。
    """
    # TODO 5
    chunks = index.search(question)
    sys_prompt = make_synthesis_prompt(chunks)
    messages = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": question}]
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3        # 事实问答用低温度，保持稳定
    )
    answer = resp.choices[0].message.content
    # 依据片段用简短、分行、截断的格式展示；答案由调用方打印（只打印一次）
    print("📎 依据片段:")
    for i, c in enumerate(chunks, 1):
        print(f"  [{i}] {c['source']}: {c['text'][:50]}...")
    return answer, chunks


def evaluate(index: DocIndex, qa_pairs: list[dict], k: int = TOP_K) -> float:
    """hit rate@k：答案所在文档是否出现在检索结果里。打印每个问题的命中情况。"""
    # TODO 6
    hits = 0
    for qa in qa_pairs:
        sources = [c.get("source") for c in index.search(qa.get("question"), k)]
        hit = qa.get("answer_source") in sources
        print(f"{'✅' if hit else '❌'} {qa.get('question')} -> 答案应在 {qa.get('answer_source')}")
        hits += hit
    # hit rate 只由调用方（main）打印一次
    return hits / len(qa_pairs) if qa_pairs else 0.0
        

def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key


def main() -> None:
    """REPL：/ingest /sources /eval /exit + 直接提问。"""
    try:
        client = OpenAI(api_key=load_api_key(), base_url=BASE_URL)
    except ValueError as e:
        print(e)
        return
    index = DocIndex()
    index.load(INDEX_FILE)
    print(f"已加载 {len(index.chunks)} 个索引片段（/ingest 重建）")
    last_chunks: list[dict] = []
    try:
        while True:
            user_input = input("> ")
            if user_input == "/ingest":
                docs = load_docs()
                if docs:
                    chunks = split_documents(docs)
                    build_index(chunks)
                    index = DocIndex()
                    index.load(INDEX_FILE)
            elif user_input == "/sources":
                if last_chunks:
                    for i, c in enumerate(last_chunks, 1):
                        print(f"[{i}] {c['source']}: {c['text'][:60]}...")
                else:
                    print("（还没有回答过问题）")
            elif user_input == "/eval":
                print(f"hit rate@{TOP_K}: {evaluate(index, QA_PAIRS):.2f}")
            elif user_input == "/exit":
                break
            elif not user_input.strip():
                continue
            else:
                if not index.chunks:
                    print("索引为空，先执行 /ingest")
                    continue
                try:
                    answer, last_chunks = retrieve_and_answer(client, index, user_input)
                    print(answer)
                except Exception as e:
                    print(f"回答失败: {e}")
    except KeyboardInterrupt:
        print("\n程序已退出")


if __name__ == "__main__":
    main()
