# 第九周：LangGraph 与主流框架——把你的手写 Agent 升级成图

> 目标：理解 Agent 框架解决什么问题，掌握 LangGraph 核心概念（State/Node/Edge），把第六周手写的 ReAct Agent 翻译成图结构。
> 验收产出：`langgraph_agent.py`——用 LangGraph 重写的工具调用 Agent。

---

## 0. 为什么这周值得学（你的视角和其他人不一样）

大部分人学框架是从零开始——你已经有 8 周底子了。**"先手写、再上框架"是最佳学习路径**：框架封装的东西你都手写过一遍，这周你看到的不是"黑魔法"，而是"哦，原来它把我的 while 循环变成了图"。

**先想清楚：框架到底解决了什么？**

| 手写时的痛点 | 框架的答案 |
|---|---|
| while 循环 + 条件判断控制流程 | **图**：节点 + 有向边（含条件边），流程一目了然 |
| messages 手动 append、手动回滚 | **State**：reducer 自动累积/覆盖 |
| 循环没有可视化，出错靠 print 猜 | 图的每一步都可**可视化/打断/检查** |
| 会话状态全靠自己维护 | **Checkpointer**：持久化、断点续跑、时间旅行 |
| 多 Agent 协作要自己拼 | 框架原生支持多图嵌套、子图 |

**注意这个类比**：LangGraph 之于 Agent，就像 React 之于前端——不写 React 也能做网页，但写了之后"状态管理、组件复用、调试"都有人替你操心。你不是必须用它，但它是当前（2025）Agent 工程的主流选择。

---

## 1. LangGraph 四个核心概念（务必吃透）

### 1.1 State（状态）—— 图里流动的数据

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END, add_messages

class State(TypedDict):
    messages: Annotated[list, add_messages]   # add_messages = 追加模式
    question: str                             # 普通字段 = 覆盖模式
```

**reducer 是关键**：每个 node 返回的 dict 会"合并"进 State。`add_messages` 表示"新消息追加到列表"，普通字段则是"直接覆盖"。这解决了你手写时"messages 该 append 还是该替换"的纠结——**声明一次，框架管理**。

### 1.2 Node（节点）—— 一个处理单元（就是你的一个函数）

```python
def greet(state: State) -> dict:
    return {"messages": [{"role": "assistant", "content": f"你好！你说：{state['question']}"}]}
```

node 接收当前 State，返回**要更新的部分**（dict）。——这和你手写时"函数接收 messages 返回新消息"完全一样！

### 1.3 Edge（边）—— 谁连谁；Conditional Edge 是 if 语句

```python
def route(state: State) -> str:
    return "weather" if "天气" in state["question"] else "general"

graph.add_conditional_edges("classify", route, {"weather": "weather_node", "general": "general_node"})
```

### 1.4 组装、编译、运行

```python
graph = StateGraph(State)
graph.add_node("greet", greet)
graph.add_edge(START, "greet")
graph.add_edge("greet", END)
app = graph.compile()                       # 编译
result = app.invoke({"question": "你好", "messages": []})   # 运行：返回最终 State
```

**循环 = 条件边回指自己**（图论里的环）：
```python
graph.add_conditional_edges("count", should_continue, {"continue": "count", "end": END})
```

---

## 2. 核心洞察：把第六周的手写 ReAct 翻译成图

这是本周最重要的心智练习。对照看：

| 第六周手写代码 | LangGraph 对应物 |
|---|---|
| `messages` 列表传来传去 | `State.messages` + `add_messages` reducer |
| `while True` + `break` | 条件边回指自己 / 指向 END |
| `react_step()`（调模型 + 解析） | `call_model` node |
| `execute_tool()` | `tools` node |
| `if final_answer: return` | 条件边 → END |
| `messages.append(...)` | node 返回 `{"messages": [...]}`，reducer 自动加 |

**一个循环 = 一个环**。你的 Agent 图长这样：

```
START → call_model ──有 tool_calls──→ tools → call_model（回到自己，形成环）
          │
          └──无 tool_calls──→ END
```

画出来之后，流程的每个出口都看得见——这就是框架比 while 循环强的地方：**控制流可见、可打断、可测试**。

---

## 3. 其他框架速览（知道定位即可）

| 框架 | 特点 | 适合 |
|---|---|---|
| **LangGraph**（本周） | 图结构、状态管理、生产级 | 复杂/多 Agent/需要持久化 |
| **OpenAI Agents SDK** | 官方、轻量、上手快 | OpenAI 生态、快速原型 |
| **smolagents** | Hugging Face、极简、代码即行动 | 学习与轻量任务 |
| **CrewAI** | 角色化（Role/Task/Process） | 多角色协作场景 |

**选型建议**：工具链跟着生态走（用 LangChain 生态选 LangGraph，用 OpenAI 全家桶选 Agents SDK）。你已经懂底层，选型时看的是"状态管理、持久化、调试能力"而不是"会不会用"。

---

## 4. 环境准备

```powershell
cd D:\ai-agents\week9
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install langgraph openai
$env:DEEPSEEK_API_KEY = "sk-你的key"
```

> ⚠️ LangGraph 版本迭代较快（0.2 → 0.4+），核心 API（StateGraph/START/END/add_messages）稳定；如果你装到的版本报 ImportError，把报错发我。参考资料：https://langchain-ai.github.io/langgraph/

---

## 5. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 1（四个核心），练习 1–2 | ☐ |
| Day 2 | 2.5h | 概念 1.3~1.4（条件边/循环），练习 3–4 | ☐ |
| Day 3 | 2.5h | 概念 2（手写→图翻译），练习 5，搭 langgraph_agent 骨架 | ☐ |
| Day 4 | 2.5h | 完成 langgraph_agent + 自检 + git 提交 | ☐ |

---

## 6. 动手练习（exercises.py，纯图机制，不需要 API Key）

1. **hello_graph**：单 node 图——输入问题，node 返回固定问候，跑通 compile/invoke
2. **branch_graph**：条件分支——问题含"天气"走 weather 提示 node，否则走 general node
3. **loop_graph**：循环计数——node 自环 N 次后经条件边结束（理解"环 = 循环"）
4. **message_state_graph**：add_messages reducer——两个 node 先后追加消息，验证 State 自动累积
5. **设计题（不写代码）**：把第六周 `react_step`/`react_loop` 翻译成 node/edge 清单，写清每个 node 干什么、条件边怎么判——这就是 langgraph_agent 的蓝图

---

## 7. 本周项目：langgraph_agent.py（图版工具 Agent）

**需求**：用 LangGraph 重写第六周 mini_agent 的功能（工具调用循环），工具复用：safe_calculate / get_weather / get_time。

```powershell
python langgraph_agent.py
你> 北京的天气？顺便算 2 的 10 次方
（内部：call_model → tools → call_model → ... 循环直到无 tool_calls）
最终回答: ...
```

**骨架 TODO**：
1. `AgentState`：TypedDict（messages 用 add_messages）
2. `call_model(state)`：调 LLM（带 tools），把响应转成**纯 dict** 返回（含 tool_calls）
3. `execute_tools(state)`：遍历最后一条 assistant 消息的 tool_calls，执行并回填 tool 消息
4. `should_continue(state)`：最后一条消息有 tool_calls → 返回 "tools"，否则返回 END
5. `build_graph()`：StateGraph 组装（START → call_model → 条件边 → tools/END），compile 返回 app
6. `main()`：输入问题 → `app.invoke` → 打印最终回答 + 友好错误

**验收标准**：
- "算 (2+3)*4" → 只走一轮工具调用即回答
- "北京的天气？顺便算 2^10" → 走多轮（环）再回答
- 未知工具/工具报错 → 模型能自愈（错误作为 tool 消息回填）
- 画得出自己这张图的 node/edge（写进 README 或注释）

**扩展挑战**：给 compile 加 `checkpointer`（`from langgraph.checkpoint.memory import MemorySaver`），验证多轮对话状态持久化；`app.stream(...)` 看每一步中间状态。

---

## 8. 自检清单（Day 4 结束前）

- [ ] 能说清 LangGraph 的 State/Node/Edge/条件边分别对应手写代码的什么
- [ ] 能解释 reducer（add_messages）解决什么问题
- [ ] 能画出"循环 = 条件边回指自己"的图
- [ ] 能说出 LangGraph vs 手写的 3 个优势、2 个代价
- [ ] langgraph_agent 完整跑通，能说出每个 node 的执行顺序

---

## 9. 参考

- LangGraph 官方教程：https://langchain-ai.github.io/langgraph/tutorials/
- LangGraph 概念文档：https://langchain-ai.github.io/langgraph/concepts/
- 对比：LangGraph vs 手写（Reddit/社区讨论可搜）
