# 第十周：多 Agent 协作——让 Agent 们像团队一样工作

> 目标：理解三种多 Agent 协作模式（主管分派 / 流水线 / 辩论），用 LangGraph 实现一个"研究员 + 写手 + 主编"的报告工坊（带评审打回环）。
> 验收产出：`report_workshop.py`——给定主题，多个 Agent 协作产出带评审意见的终稿。

---

## 0. 为什么需要多 Agent？（先想清楚，别为了多而多）

单 Agent 的边界：

| 单 Agent 的问题 | 多 Agent 的解法 |
|---|---|
| 一个 system prompt 塞下所有角色 → 角色混淆、上下文互相污染 | **每个 Agent 只有一种角色**，prompt 短而聚焦 |
| 又要调研、又要写、又要检查 → 都做但都不精 | **专业分工**：调研的不写，写的不自审 |
| 让模型"自己检查自己" → 自我纠错能力弱 | **引入独立评审者**：外部视角才挑得出毛病 |

**反面警告（重要）**：多 Agent ≠ 更好。代价是**每个环节一次模型调用**——成本 ×N、延迟 ×N、失败点 ×N。**单 Agent 能解决的事，不要上多 Agent**。"评审"这种自我纠错需求，才值得多花一次调用。

---

## 1. 三种经典协作模式（都只是图的不同形状）

### 模式 1：Orchestrator-Worker（主管分派）
一个**主管 LLM** 决定"下一步该叫哪个工人"——路由不写死，由主管动态决策。

```
                ┌─→ worker_A（研究）
supervisor ─────┼─→ worker_B（写作）
 (LLM 路由)     └─→ worker_C（评审）
```

**关键**：主管的路由 = 第九周学的"条件边"，只是条件不是写死的规则，而是**主管自己用 LLM 判断**。本质上是把第九周"模型决定调哪个工具"升级成"模型决定调哪个 Agent"。

### 模式 2：Pipeline（流水线）
固定顺序，前一个的输出是后一个的输入。简单可靠，适合流程确定的场景。

```
researcher → writer → reviewer →（终稿）
```

### 模式 3：Debate（辩论 / 多专家投票）
多个独立 Agent 各自回答，一个裁判（或规则）选优。

```
expert_A 观点 ──┐
expert_B 观点 ──┼──→ judge → 结论
expert_C 观点 ──┘
```

---

## 2. 本项目模式：Pipeline + 评审反馈环

本项目的"报告工坊"用的是模式 2 的升级版——流水线 + **评审打回环**（这比纯流水线更有 Agent 味，也复用了第九周的"环"）：

```
START → 研究员（产出调研要点）→ 写手（写初稿）
                                     │
                  ┌──────────────────┘
                  ▼
              主编（评审：通过 / 打回+意见）
                  │ 通过 → END（输出终稿）
                  │ 打回 → 回到写手（带着评审意见重写）→ 主编再审…
                  └──（最多 MAX_ROUNDS 轮）
```

**每个 Agent 的独立性体现在哪？** 每个节点用**自己的角色 system prompt** 调用模型，只通过 state 字段交换**结构化中间产物**（notes / draft / review_comments）——Agent 之间不共享对话历史，只共享"工作成果"。这是多 Agent 和单 Agent 带长历史最本质的区别。

---

## 3. Agent 与中间产物的设计要点

### 3.1 角色 prompt 只描述自己

```python
RESEARCHER_PROMPT = """你是项目研究员。你的任务：围绕主题输出调研要点。
要求：输出 3-5 条要点，每条 1-2 句，聚焦事实与数据，不要写结论性文章。"""

WRITER_PROMPT = """你是报告写手。根据【调研要点】撰写初稿。
要求：结构清晰（引言/正文/结语），语言专业。如果【主编意见】存在，必须根据意见修改。"""
```

**每个 system 都不知道"其他 Agent 存在"以外的全局信息**——只需要知道自己要产出什么格式。角色简单，prompt 才不会被稀释。

### 3.2 中间产物要"结构化"

不要让 Agent 输出散文再靠下一个 Agent 猜——定义好字段（notes / draft / comments），各自只填自己的字段。**多 Agent 的工程质量 = 中间接口的质量**（和团队协作的接口设计同理）。

### 3.3 评审要有"裁决"

评审输出必须可路由：`{"verdict": "approve" | "revision", "comments": "..."}`——用第四周的 JSON mode + 解析技能。**裁决字段是图的"红绿灯"**。

---

## 4. 环境准备

```powershell
cd D:\ai-agents\week10
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install openai langgraph
$env:DEEPSEEK_API_KEY = "sk-你的key"
```

---

## 5. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 0~1（三种模式），练习 1–2 | ☐ |
| Day 2 | 2.5h | 概念 2~3（本项目模式/设计要点），练习 3–4 | ☐ |
| Day 3 | 2.5h | 练习 5（设计题），搭 report_workshop 骨架 | ☐ |
| Day 4 | 2.5h | 完成 report_workshop + 自检 + git 提交 | ☐ |

---

## 6. 动手练习（exercises.py）

1. **parse_plan**：解析主管输出的任务清单（JSON 文本 → 任务列表，纯本地）
2. **parse_review**：解析评审输出（verdict + comments，纯本地）
3. **agent_call**：通用子 Agent 调用封装——`(system 角色, 内容) → 回复`（调 API 一次，感受"每个 Agent 一次调用"）
4. **supervisor_pick**：主管选择——让模型从给定选项里选下一步，返回选项名（JSON 输出；这就是主管路由的最小实现）
5. **设计题（不写代码）**：同一任务"写一篇关于 AI Agent 的科普文章"分别用 主管分派/流水线/辩论 三模式画图，写清 node、edge、条件边，并说清各自优劣

---

## 7. 本周项目：report_workshop.py（多 Agent 报告工坊）

**需求**：输入主题 → 研究员调研 → 写手初稿 → 主编评审（可打回重写，最多 MAX_ROUNDS 轮）→ 输出终稿与评审历史。

```powershell
python report_workshop.py
> 写一篇 500 字的短文，介绍 Python 装饰器
[研究员] 调研要点: 1. 装饰器是…… 2. ...
[写手] 初稿: ...
[主编] 评审: 通过 ✅（或：打回 ❌ - 需要补充示例）
...
最终输出（终稿）: ...
```

**骨架 TODO（从易到难）**：
1. `research_node(state)`：角色 prompt → 输出 notes（打印 "[研究员]" 前缀）
2. `write_node(state)`：基于 topic + notes + review_comments → 输出 draft
3. `review_node(state)`：JSON mode 输出 `{"verdict": ..., "comments": ...}` → 解析写入 state（打印 "[主编] 评审"）
4. `should_continue(state)`：verdict=revision 且 rounds < MAX_ROUNDS → 回 "write"；否则 END
5. `build_graph()`：组装（环：review → write）
6. `main()`：REPL + 打印流程

**验收标准**：
- 一次正常流程：研究员 → 写手 → 主编（通过）→ 终稿
- 让主编**故意刁难一次**（比如改 system 要求"第一版必须打回一次"）→ 验证打回环生效、写手根据意见重写
- rounds 超限能优雅结束（不无限循环）
- 每个 Agent 输出带角色前缀，流程清晰可读

**扩展挑战**：给研究员加检索工具（接第八周 DocIndex）——研究员变成"带 RAG 的研究员"；加 debate 模式对比（两个写手各写一版，裁判选优）。

---

## 8. 自检清单（Day 4 结束前）

- [ ] 能画出三种协作模式的图并说出适用场景
- [ ] 能说清"每个 Agent 一次调用"的成本含义，以及什么时候**不该**用多 Agent
- [ ] 能解释"中间产物结构化"为什么是多 Agent 工程质量的关键
- [ ] 评审的 verdict 为什么是图的"红绿灯"
- [ ] report_workshop 跑通打回-重写环

---

## 9. 参考

- LangGraph 多 Agent 教程：https://langchain-ai.github.io/langgraph/tutorials/multi_agent/
- Anthropic《Building Effective Agents》（多 Agent 章节）：https://www.anthropic.com/research/building-effective-agents
- MetaGPT（多 Agent 论文/开源）：https://github.com/geekan/MetaGPT
