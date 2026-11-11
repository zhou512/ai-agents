# 第七周：记忆与状态（让 Agent 记住你）

> 目标：理解 Agent 的两类记忆（短期/长期），掌握向量检索原理，实现一个**带长期记忆的对话助手**：检索注入 + 事实抽取 + 文件持久化。
> 验收产出：`memory_chat.py`——重启程序后仍能回忆"你之前告诉过我的事"。

---

## 0. 为什么需要"记忆"

模型本身**无状态**——每轮对话都是独立的。你上周写的 ReAct 循环里，历史是靠 messages 手动携带的，这就是最原始的"记忆"。但它有两个硬伤：

1. **上下文窗口有限**：聊 100 轮后历史太长，超窗口报错
2. **成本线性增长**：每轮都带着全部历史 = 同样的 token 重复付费

所以 Agent 需要两类记忆：

| 类型 | 是什么 | 管理方式 |
|---|---|---|
| **短期记忆** | 当前会话的对话历史 | 滑动窗口裁剪 / 摘要压缩 |
| **长期记忆** | 跨会话的重要信息（用户叫什么、偏好什么） | 向量检索：存起来，需要时按相关性取回 |

本周核心是**长期记忆**：怎么存（向量）、怎么取（相似度检索）、怎么注入（拼进上下文）、怎么写入（事实抽取）。

---

## 1. 向量检索原理（手写版，零依赖）

**核心问题**：一堆记忆条目里，怎么找出"和当前问题最相关"的几条？

**思路**：把文本变成**向量**（一串数字），然后用**相似度**排序。

### 1.1 文本 → 向量（字符 n-gram）

中文没有空格分词，最简单的特征化：**n-gram**（连续 n 个字符的片段）。

```python
def char_ngrams(text: str, n: int = 2) -> list[str]:
    text = text.lower()
    return [text[i:i+n] for i in range(len(text) - n + 1)]

# "我喜欢喝咖啡" -> ["我喜", "喜欢", "欢喝", "喝咖", "咖啡"]
```

然后统计每个 n-gram 的出现次数，就得到一个**稀疏向量**（字典形式）：

```python
def simple_embed(text: str) -> dict[str, float]:
    counts: dict[str, float] = {}
    for g in char_ngrams(text):
        counts[g] = counts.get(g, 0) + 1
    norm = math.sqrt(sum(v*v for v in counts.values()))   # L2 归一化
    if norm == 0:
        return {}
    return {k: v / norm for k, v in counts.items()}
```

> 效果："我喜欢喝咖啡" 和 "我每天喝咖啡" 共享 `咖啡`/`喝咖` 等 n-gram → 向量靠近；和 "下雨天记得带伞" 几乎不共享 → 向量远离。**这就是"语义相关性"的最朴素实现。**

### 1.2 余弦相似度

两个向量的相似度用**夹角余弦**衡量（1 = 完全相同，0 = 无关）：

```python
def cosine_similarity(v1: dict, v2: dict) -> float:
    dot = sum(v1.get(k, 0) * v2.get(k, 0) for k in set(v1) | set(v2))
    n1 = math.sqrt(sum(x*x for x in v1.values()))
    n2 = math.sqrt(sum(x*x for x in v2.values()))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)
```

### 1.3 检索 = 算一遍相似度，取 top-k

```python
def search(store, query: str, k: int = 3) -> list[tuple[str, float]]:
    qv = simple_embed(query)     #单位化后的n-grams向量
    scored = [(item["text"], cosine_similarity(qv, item["vector"]))
              for item in store]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
```

### 1.4 生产环境用什么？（重要）

手写 n-gram 向量是**教学方案**，能让你理解原理。真实产品用 **embedding 模型 API**（把文本变成几百维的语义向量，理解同义词/上下文）：

- OpenAI `text-embedding-3-small`
- 智谱 `embedding-3`、通义 `text-embedding-v3`、硅基流动 `BAAI/bge-m3`（均 OpenAI 兼容接口）
- 本地：`sentence-transformers`（需装 torch）

**原理完全一样**：文本 → 向量 → 余弦相似度 → top-k。只是向量更"聪明"。

---

## 2. 记忆系统的两大动作

### 2.1 检索注入（提问前）—— 让模型"想起来"

每次用户提问，先用问题检索最相关的记忆，拼进 system 提示词：

```python
context = store.search(question, k=3)
system = f"""你是一个乐于助人的助手。
以下是用户过去提到过的信息（可能相关，也可能不相关）：
{chr(10).join(f"- {text}" for text, score in context)} 
如果与当前问题相关请参考，无关请忽略。"""
```
(chr(10)就是换行符)

**要点**：检索结果只是"参考材料"，模型自己判断相关性——宁可多给几条，不可漏。

### 2.2 事实抽取（回答后）—— 让模型"记住"

对话结束后，让模型用 JSON 提取"值得长期记住的用户信息"：

```python
prompt = """从这段对话中提取值得长期记住的用户信息（名字、偏好、重要事实）。
只输出 JSON 数组，如 ["用户叫小明", "用户喜欢喝咖啡"]。没有就输出 []。"""
```

**去重**：入库前先和已有记忆算相似度，>0.85 就跳过（防止重复累积）。

---

## 3. 短期记忆管理（本周次要内容）

- **滑动窗口**：messages 只保留最近 N 条（第三周做过）
- **摘要压缩**：把旧历史让模型概括成一段，替换掉原文（练习 6）

---

## 4. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 1（向量原理），练习 1–3 | ☐ |
| Day 2 | 2.5h | 练习 4–5（分块 + VectorStore） | ☐ |
| Day 3 | 2.5h | 概念 2 + 练习 6（摘要），搭 memory_chat 骨架 | ☐ |
| Day 4 | 2.5h | 完成 memory_chat + 自检 + git 提交 | ☐ |

---

## 5. 动手练习（exercises.py，都是独立小函数）

1. **char_ngrams**：提取字符 n-gram
2. **simple_embed**：文本 → 归一化特征向量
3. **cosine_similarity**：余弦相似度
4. **chunk_text**：长文本分块（简单版按字符硬切）
5. **VectorStore** 类：`add(text)` / `search(query, k)` / `save(path)` / `load(path)`（JSON 持久化）
6. **summarize_messages**：把对话历史压缩成一段摘要（真实调用 API）

每个练习都有期望输出，离线可测（除 6）。

---

## 6. 本周项目：memory_chat.py（带长期记忆的对话助手）

**需求**：聊天助手，能记住跨会话的用户信息。

```powershell
python memory_chat.py

你> 我叫小明，我 25 岁
助手> 你好小明！我记住了。
你> /memories
1. 用户叫小明，25 岁
你> （重启程序）
你> 我叫什么？
助手> 你叫小明。      ← 记忆检索注入生效！
```

**流程**：
1. 启动：从 `memories.json` 加载记忆库
2. 每轮提问：**检索注入**（top-3 相关记忆拼进 system）→ 模型回答
3. 回答后：**事实抽取**（JSON）→ 去重入库 → 持久化
4. 命令：`/memories` 查看、`/forget` 清空、`/exit`

**骨架 TODO（从易到难）**：
1. `retrieve_context(store, question, k)`：检索记忆，拼成参考材料文本（含"未检索到"的情况）
2. `build_messages(question, context)`：构造 system（注入记忆）+ user
3. `chat_once(client, question, store)`：检索 → 构造 → 回答（打印"📎 检索到的记忆"便于观察）
4. `extract_facts(client, question, answer)`：JSON mode 抽取事实（含解析失败重试一次）
5. `save_facts(store, facts)`：相似度去重（>0.85 跳过）+ `store.save()`
6. `main()`：加载记忆 → REPL（命令 + 流程串联）+ 友好错误

**验收标准**：
- 会话中说"我叫小明"，重启程序后问"我叫什么"能答对
- `/memories` 显示去重后的记忆列表
- 不相关问题不会触发错误记忆（检索注入的"相关性由模型判断"生效）
- 程序崩溃/关闭后记忆不丢失（memories.json 持久化）

**扩展挑战**：加 `chunk_text` 处理长文本记忆；记忆超过 N 条时淘汰最旧。

---

## 7. 自检清单（Day 4 结束前）

- [ ] 能解释"模型为什么需要长期记忆"（窗口有限 + 成本 + 跨会话）
- [ ] 能画出手写向量检索的三步（n-gram → 余弦 → top-k）
- [ ] 能说清"检索注入"和"事实抽取"各自在什么时候发生
- [ ] 知道生产环境用什么替代手写向量（embedding API）
- [ ] memory_chat 重启后能回忆用户信息

---

## 8. 参考

- 向量检索/RAG 入门：https://www.promptingguide.ai/zh/applications/rag
- 余弦相似度：https://zh.wikipedia.org/wiki/%E4%BD%99%E5%BC%A6%E7%9B%B8%E4%BC%BC%E5%BA%A6
- Lilian Weng《LLM Powered Autonomous Agents》（记忆章节）：https://lilianweng.github.io/posts/2023-06-23-agent/
