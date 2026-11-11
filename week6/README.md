# 第六周：手写 ReAct Agent（不依赖任何框架）

> 目标：理解 ReAct（Reasoning + Acting）范式，不依赖任何框架手写一个最小 Agent：**思考 → 行动 → 观察 → 继续 → 最终回答**。
> 验收产出：`mini_agent.py`——手写 ReAct 循环 + 3 个真实工具，能回答问题并打印完整思维过程。

---

## 0. 为什么必须手写一遍

第五周的 Function Calling 是"框架帮你做"的工具调用；**ReAct 是它的理论根基和前身**。手写一遍的意义：

1. 真正理解 Agent 循环的本质——以后用 LangGraph 等框架，你知道底层在做什么
2. 面试高频题："ReAct 是什么？循环怎么设计？为什么需要 max_steps？"
3. ReAct 的文本协议不依赖 API 的 function calling 支持，任何 LLM 都能跑

---

## 1. ReAct 是什么

**论文**：ReAct: Synergizing Reasoning and Acting in Language Models（Yao et al., 2022，https://arxiv.org/abs/2210.03629）

**核心思想**：让模型**一边推理（Reasoning）一边行动（Acting）**——推理指导行动，行动结果反馈推理，交替进行直到得出答案。

| 对比 | 特点 | 缺陷 |
|---|---|---|
| 纯推理（思维链 CoT） | 只推理不行动 | 遇到"需要查外部信息"的问题只能瞎编 |
| 纯行动（简单工具 prompt） | 只行动不编排 | 多步任务不知道怎么串联 |
| **ReAct（本周）** | 推理↔行动交替 | 需要解析输出、控制循环（复杂度上升） |

---

## 2. 循环图解（本周的"圣图"）

```
问题：北京天气怎么样？
──────────────────────────────────────
Thought: 用户想知道北京的天气，我需要查询
Action: get_weather
Action Input: {"city": "北京"}
──────────────────────────────────────  ← 你的代码执行工具
Observation: 北京:多云，温度为28.3,风速8.2
──────────────────────────────────────
Thought: 我已经拿到天气信息，可以回答了
Final Answer: 北京现在 28.3°C，多云，风速 8.2 km/h
```

**关键点**：
- 模型的输出是**结构化文本协议**（Thought / Action / Action Input / Final Answer），不是 function calling API
- 你的代码负责四件事：**调用模型 → 解析文本 → 执行工具 → 把 Observation 回填**，然后循环
- **终止条件**：模型输出 Final Answer，或达到 MAX_STEPS（防死循环）

---

## 3. 文本协议 vs Function Calling（和第五周对比）

| 维度 | ReAct 文本协议（本周） | Function Calling（第五周） |
|---|---|---|
| 模型输出 | 自由文本，需要正则解析 | 结构化 `tool_calls`，API 保证格式 |
| 兼容性 | 任何 LLM 都行 | 需要支持 tool 的模型 |
| 解析成本 | 可能解析失败（要容错） | 无需解析 |
| 出错处理 | 解析失败 → 让模型重来 | 天然结构化 |
| 学习价值 | **理解循环本质** | 生产主流方案 |

**两种都该会**：手写 ReAct 让你懂原理，function calling 让你做产品。本周正是检验第五周学习效果的机会——工具你都会了，本周的核心是**循环和解析**。

---

## 4. 解析逻辑（本周的核心代码）

```python
import json, re

def parse_react_output(text: str) -> dict:
    """从模型输出中解析 Thought / Action / Action Input / Final Answer。"""
    result = {}
    m = re.search(r"Thought:\s*(.+)", text)
    if m: result["thought"] = m.group(1).strip()
    m = re.search(r"Action:\s*(\w+)", text)
    if m: result["action"] = m.group(1)
    m = re.search(r"Action Input:\s*(\{.+?\})", text, re.DOTALL)
    if m: result["action_input"] = json.loads(m.group(1))
    m = re.search(r"Final Answer:\s*(.+)", text, re.DOTALL)
    if m: result["final_answer"] = m.group(1).strip()
    return result
```

**容错要点**：模型输出经常不规范（字段缺失、Action Input 跨行、混入废话）。解析失败时，把 Observation 设为 **"无法解析你的输出，请严格按照 Thought/Action/Action Input 格式重新输出"**，让模型重来——不要崩溃。

---

## 5. system prompt 设计（第四周 few-shot 的直接应用）

要求：
1. **列出工具**：名字 + 参数 + 作用（模型靠这个选工具）
2. **严格格式说明**："一次只输出一种：Thought 或 Final Answer"
3. **给 1 个完整 few-shot 示例**（一轮工具调用 + Final Answer）——模型会模仿示例格式
4. 强调 Action Input 是 JSON

```python
SYSTEM_PROMPT = """你是一个能使用工具回答问题的智能体。

可用工具：
- get_weather(city: str): 查询城市当前天气
- safe_calculate(expression: str): 计算数学表达式（幂用 **）
- get_time(timezone: str = "Asia/Shanghai"): 获取时区当前时间

严格按以下格式输出（一次只输出一种）：
Thought: 你的推理过程
Action: 工具名
Action Input: JSON 格式参数，如 {"city": "北京"}

当你获得足够信息后输出：
Thought: 我现在知道了答案
Final Answer: 最终回答

示例：
用户问题：上海的天气？
Thought: 需要查询上海的天气
Action: get_weather
Action Input: {"city": "上海"}
Observation: 上海:晴朗，温度为31.1,风速14.5
Thought: 我已经知道上海的天气了
Final Answer: 上海现在 31.1°C，晴朗，风速 14.5 km/h
"""
```

---

## 6. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 1~3 + 解析逻辑 4，练习 1 | ☐ |
| Day 2 | 2.5h | prompt 设计 5，练习 2–3 | ☐ |
| Day 3 | 2.5h | 练习 4（react_loop），搭 mini_agent 骨架 | ☐ |
| Day 4 | 2.5h | 完成 mini_agent + 自检 + git 提交 | ☐ |

---

## 7. 动手练习（exercises.py）

1. **parse_react_output**：解析各种格式的模型输出（正常 / 缺字段 / Action Input 跨行 / 带 Final Answer）
2. **build_react_prompt**：构造 system prompt（工具描述 + 格式 + few-shot 示例）
3. **react_step**：单步循环——调模型 → 解析 → 执行工具 → 返回 (最终回答 or None, 是否结束)
4. **react_loop**：完整循环——直到 Final Answer 或 max_steps，打印每一步的 Thought/Action/Observation
5. **对比笔记**（不写代码，写观察）：ReAct 文本协议 vs 第五周 function calling，列出至少 5 条差异

---

## 8. 本周项目：mini_agent.py（手写 ReAct Agent）

**需求**：手写 ReAct 循环（**不用 function calling API、不用框架**），自带 3 个工具。

```powershell
python mini_agent.py

你> 北京的天气怎么样？顺便算一下 (2+3)*4
Thought: 需要查询北京的天气
Action: get_weather
Action Input: {"city": "北京"}
🔧 Observation: 北京:多云，温度为28.3,风速8.2
Thought: 还需要计算 (2+3)*4
Action: safe_calculate
Action Input: {"expression": "(2+3)*4"}
🔧 Observation: 20
Thought: 两个信息都拿到了
Final Answer: 北京现在 28.3°C，多云。另外 (2+3)*4 = 20。
```

**骨架 TODO（从易到难）**：
1. `parse_react_output(text)`：正则解析（含容错）
2. `build_react_prompt()`：构造 system prompt
3. `react_step(client, messages, registry)`：单步（调模型 → 解析 → 执行 → Observation 回填），打印过程，返回 (最终回答 or None, 是否结束)
4. `react_loop(client, question, registry, max_steps=6)`：完整循环
5. `main()`：REPL + `/tools` `/clear` `/exit` + 友好错误

**验收标准**：
- "北京的天气" → 完整轨迹：Thought → Action → Observation → Final Answer
- "算 (2+3)*4，然后查上海天气" → 连续多轮工具调用
- 模型输出不规范（解析失败）→ 容错重来，不崩溃
- 未知工具名 → Observation 返回错误，模型自己纠正
- max_steps 超限 → 明确提示"达到最大步数"

**扩展挑战**：解析失败时统计失败次数，连续 2 次失败就终止（防死循环）；给循环加 total_tokens 统计。

---

## 9. 自检清单（Day 4 结束前）

- [ ] 能画出 ReAct 循环图并解释每个环节
- [ ] 能说清 ReAct 与 CoT、与 function calling 的区别
- [ ] 能写出解析逻辑并处理"模型输出不规范"的情况
- [ ] 知道为什么需要 max_steps
- [ ] mini_agent 完整跑通，思维过程可视化

---

## 10. 参考

- ReAct 论文：https://arxiv.org/abs/2210.03629
- Lilian Weng《LLM Powered Autonomous Agents》：https://lilianweng.github.io/posts/2023-06-23-agent/
- Anthropic《Building Effective Agents》：https://www.anthropic.com/research/building-effective-agents
