# 第八周：RAG（检索增强生成）—— 让 Agent 读懂你的文档

> 目标：掌握 RAG 三段式 pipeline（索引 → 检索 → 生成），实现一个"个人文档问答 Agent"；学会用测试问题集**评估**检索质量。
> 验收产出：`doc_qa.py`——把你的课程笔记/资料做成知识库，问它"某某概念是什么"能给出带出处的回答，并报告检索命中率。

---

## 0. RAG 是什么？和第七周什么关系？

**RAG（Retrieval-Augmented Generation，检索增强生成）** = 先检索文档片段，再让模型基于片段回答。

它和第七周的长期记忆**是同一个架构**，只是数据源不同：

| | 第七周：长期记忆 | 第八周：RAG |
|---|---|---|
| 存什么 | 对话中抽取的用户事实 | 你的文档（笔记/资料） |
| 架构 | 向量化 + 检索 + 注入 | **完全一样** |
| 回答依据 | 零散的"记忆" | 结构化的"知识库" |

一句话：**RAG 是把"记住你"升级成"读懂你的文档"**。它是当前 LLM 应用最主流的落地形态（客服问答、法律/医疗知识库、企业内部文档助手都是它）。

---

## 1. RAG 三段式 pipeline（本周的"圣图"）

```
【离线：索引 Indexing】（建一次，可复用）
文档 → 分块（chunk）→ 每块向量化 → 存索引

【在线：问答 Generation】
用户问题 ──向量化──→ 检索 top-k 相关块 ──拼进 prompt──→ 模型回答（带出处）
                      ↑
                 【检索 Retrieval】
```

三段分别对应本周的三个技能：**分块策略、检索（第七周已会）、生成 prompt**。

---

## 2. 分块策略（本周第一个新技能）

上一周分块是"按字符硬切"——会把一句话切成两半，检索时命中"半个观点"，模型回答就会残缺。

**本周升级：按句子边界分块 + 相邻块重叠**

```python
def split_sentences(text: str) -> list[str]:
    """按中文/英文句末标点切句。"""
    import re
    parts = re.split(r"(?<=[。！？.!?])", text)
    return [p.strip() for p in parts if p.strip()]

def chunk_by_sentences(text: str, max_chars: int = 100, overlap_chars: int = 20) -> list[str]:
    """按句聚合成分块：句子放得下就攒着，放不下就开新块；相邻块尾部重叠。"""
    sentences = split_sentences(text)
    chunks, current = [], ""
    for s in sentences:
        if len(current) + len(s) > max_chars and current:
            chunks.append(current)
            # 新块以上一块末尾 overlap_chars 个字符开头（保住跨块的信息）
            current = current[-overlap_chars:] + s
        else:
            current += s
    if current:
        chunks.append(current)
    return chunks
```

**为什么重叠有用**：一个观点可能跨块边界——比如"装饰器的本质是……"在块 A 结尾，"……闭包"在块 B 开头。重叠让两块都带上一部分上下文，检索任一块都能回答完整。

**块大小的权衡**：太小 → 上下文碎片化；太大 → 检索不精准 + 浪费 token。中文笔记一般 100~300 字/块，可调。

---

## 3. 生成阶段的 prompt（防幻觉的关键）

检索到的块只是"素材"，模型可能忽略素材自己编——所以 prompt 必须约束：

```python
def make_synthesis_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n".join(
        f"【片段 {i+1}｜来源: {c['source']}】\n{c['text']}" for i, c in enumerate(chunks)
    )
    return f"""你是文档问答助手。请只根据下面的文档片段回答问题。

{context}

问题：{question}

要求：
1. 回答必须基于以上片段，不要编造
2. 回答末尾用括号标注依据的片段来源，如（来源: notes_python.md）
3. 片段中没有答案时，直接说"文档中没有相关信息"，不要猜测
"""
```

**两条防幻觉铁律**：① 只根据片段回答；② 没有就明说"没有"。比"让它自由发挥再指望它诚实"可靠得多。

---

## 4. 评估：怎么证明你的 RAG 真的有用（本周第二个新技能，也是宏观技能）

> 上一周说过：评测是全行业最缺的能力。RAG 做得好不好，**不能靠感觉**，要靠数字。

**方法：测试问题集 + 命中率**

1. 准备几个测试问题，每个问题**知道答案在哪份文档里**：

```python
QA_PAIRS = [
    {"question": "Python 装饰器的本质是什么？", "answer_source": "notes_python.md"},
    {"question": "什么是闭包？",                "answer_source": "notes_python.md"},
    {"question": "HTTP 状态码 404 是什么意思？", "answer_source": "notes_web.md"},
]
```

2. 每个问题检索 top-k，**看答案所在文档是否在结果里**：

```python
def hit_rate_at_k(index, qa_pairs, k=3) -> float:
    hits = 0
    for qa in qa_pairs:
        sources = {c["source"] for c in index.search(qa["question"], k=k)}
        if qa["answer_source"] in sources:
            hits += 1
    return hits / len(qa_pairs) if qa_pairs else 0.0
```

**hit rate@3 = 0.9** 意味着：90% 的问题，正确答案所在的文档块被检索到了。低于 0.7 就该怀疑分块策略或向量质量；接近 1.0 则说明检索这关过了，剩下的问题在生成质量。

**评估是"宏观视野"的具体化**：不评估 = 靠玄学调参；评估 = 每次改动都有数字说话。这是你上上周问"宏观 vs 底层"时，我说的"全行业最缺的能力"——第八周就学它。

---

## 5. 生产级升级路径（了解即可）

教学版用了手写 n-gram 向量 + JSON 文件。生产环境：

| 环节 | 教学版 | 生产版 |
|---|---|---|
| 向量化 | 手写 n-gram | embedding API（智谱/通义/硅基流动 bge-m3） |
| 存储检索 | JSON + 线性扫描 | 向量数据库（Milvus / pgvector / Chroma） |
| 排序 | 只有相似度 | **Rerank**：先用便宜检索召回 top-50，再用精排模型重排取 top-3 |
| 分块 | 按句 | 语义分块 / 结构感知分块（按 Markdown 标题） |

架构一模一样，只是零件换成工业级的。**你现在理解的是架构，零件随时能换。**

---

## 6. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 0~2（RAG/分块），练习 1–2 | ☐ |
| Day 2 | 2.5h | 概念 3（synthesis prompt），练习 3–4 | ☐ |
| Day 3 | 2.5h | 概念 4（评估），练习 5–6，搭 doc_qa 骨架 | ☐ |
| Day 4 | 2.5h | 完成 doc_qa + 自检 + git 提交 | ☐ |

---

## 7. 动手练习（exercises.py）

1. **split_sentences**：按中英文句末标点切句
2. **chunk_by_sentences**：按句聚合分块 + 相邻重叠（不切断句子）
3. **chunk_docs_with_source**：多文档 → 带 source 元数据的分块列表
4. **make_synthesis_prompt**：构造带来源标注的 RAG 回答 prompt
5. **ask_with_context**：真实 API——问题 + 分块 → 基于分块回答
6. **hit_rate_at_k**：测试问题集评估检索命中率

---

## 8. 本周项目：doc_qa.py（个人文档问答 Agent）

**需求**：把 `docs/` 目录下的 .txt/.md 文档做成知识库，提问得到带出处的回答。

```powershell
# 准备：docs/ 下放 2-3 个你的笔记文件（如 notes_python.txt、notes_web.md）
python doc_qa.py

> /ingest                    # 扫描 docs/，分块 + 索引，保存到 index.json
> 装饰器的本质是什么？
📎 依据片段: [1] notes_python.txt: "装饰器是..."
装饰器本质上是一个接收函数并返回函数的函数。（来源: notes_python.txt）
> /sources                   # 显示最近一次回答用了哪些块
> /eval                      # 跑内置测试问题集，报告 hit rate
> /exit
```

**骨架 TODO（从易到难）**：
1. `load_docs(doc_dir)`：读取 .txt/.md，返回 `[{"source": 文件名, "text": 全文}]`
2. `split_documents(docs, max_chars, overlap)`：用按句分块给每个文档分块，保留 source
3. `DocIndex`：`build(chunks)`（向量化 + 持久化 index.json）/ `load` / `search(question, k)`（返回带 source 的块）
4. `retrieve_and_answer(client, index, question)`：检索 top-k → synthesis prompt → 模型回答（返回回答 + 用到的块）
5. `evaluate(index, qa_pairs, k=3)`：hit rate@k
6. `main()`：REPL（`/ingest` `/sources` `/eval` `/exit` + 直接提问），友好错误

**验收标准**：
- `/ingest` 后重启程序无需重建（index.json 持久化）
- 问"笔记里出现过的概念"能答对并标注来源文件
- 问笔记里没有的内容 → 回答"文档中没有相关信息"，不编造
- `/eval` 报告 hit rate 数字（准备 5+ 个测试问题）
- 分块不切断句子（抽查 index.json 里的块）

**扩展挑战**：给评估加"回答质量"人工打分项；用 Rerank 思路（先用相似度取 top-10，再用模型或规则精排取 top-3）。

---

## 9. 自检清单（Day 4 结束前）

- [ ] 能画出 RAG 三段式 pipeline 并说出每段做什么
- [ ] 能说清"按句分块 + 重叠"比"硬切"好在哪
- [ ] synthesis prompt 里两条防幻觉铁律是什么
- [ ] 能解释 hit rate@k 怎么算、低分说明什么问题
- [ ] doc_qa 对自有笔记回答正确且带出处，/eval 报告命中率

---

## 10. 参考

- DeepLearning.AI《Building and Evaluating Advanced RAG》：https://www.deeplearning.ai/short-courses/
- LlamaIndex 文档：https://docs.llamaindex.ai
- RAG 概念（Prompting Guide 中文）：https://www.promptingguide.ai/zh/applications/rag
