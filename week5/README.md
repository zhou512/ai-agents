# 第五周：Function Calling（工具使用）—— Agent 的正式起点

> 目标：掌握 tool schema 定义与"模型决定 → 你执行 → 结果回填"的循环，实现一个带 3 个真实工具（天气/时间/计算）的 Agent 聊天助手。
> 验收产出：`tool_agent.py`——能回答"北京的天气？顺便算一下 2^10"这种需要连续调用多个工具的问题。

---

## 0. 为什么本周是 Agent 的起点

**Agent = LLM + 工具 + 循环**。前四周你学会了调用 LLM 和调用 API；本周把它们接起来——让**模型自己决定**调用哪个工具、以什么参数调用，你负责执行并把结果喂回给模型。这就是第 6 周手写 ReAct 的最简形态。

**一句话原理：模型不执行任何外部操作，它只输出"调用意图"（函数名 + JSON 参数），由你的代码执行。**

---

## 1. 核心循环（务必理解这张图）

```
用户提问
   │
   ▼
┌────────────┐   返回 tool_calls?   ┌──────────────────────┐
│  调用 LLM   │ ──────────────────► │ 你执行工具（真实代码）  │
│            │ ◄────────────────── │ 把结果作为 tool 消息回填 │
└────────────┘     再次调用 LLM     └──────────────────────┘
   │
   └── 没有 tool_calls → 输出最终回答
```

- **第一轮**：模型看用户问题 + 工具列表，如果觉得需要外部信息，就返回 `tool_calls`（想调用哪个函数、传什么参数）
- **执行**：你的代码真实调用函数，拿到结果
- **回填**：把结果以 `role: "tool"` 的消息发回给模型（**必须带 model 返回的 `tool_call_id`**）
- **再调用**：模型结合工具结果给出最终回答（或继续调用下一个工具）

---

## 2. tools 参数结构（JSON Schema）

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气",          # 模型靠它决定用哪个工具！
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名，如 北京"},
                },
                "required": ["city"],
            },
        },
    },
]
```

**关键认知：`description` 就是模型的"说明书"**——写清楚"这个工具做什么、参数是什么"，模型才能选对。参数结构就是 JSON Schema（第四周学的 JSON 概念的直接应用）。

> 小贴士：JSON Schema 是描述"JSON 数据长什么样"的通用规范（字段名、类型、是否必填）。你在第四周用 pydantic 做的事，JSON Schema 是它的"通用格式版本"——pydantic 是 Python 里的实现，JSON Schema 是跨语言的标准。

---

## 3. 最小实现（完整可跑，先看懂再动手）

```python
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")

messages = [{"role": "user", "content": "计算 (2+3)*4 等于多少"}]

for turn in range(3):                        # 循环上限，防止死循环
    resp = client.chat.completions.create(model="deepseek-chat", messages=messages, tools=TOOLS)
    msg = resp.choices[0].message

    if not msg.tool_calls:                   # 模型不调工具了 → 这就是最终回答
        print(msg.content)
        break

    messages.append(msg)                     # 1. 先把 assistant 消息（含 tool_calls）加进历史
    for tc in msg.tool_calls:                # 2. 逐个执行工具
        name = tc.function.name
        args = json.loads(tc.function.arguments)
        result = execute_tool(name, args)    # 你的真实函数
        messages.append({                    # 3. 回填结果（必须带 tool_call_id）
            "role": "tool",
            "tool_call_id": tc.id,
            "content": str(result),
        })
```

---

## 4. 工具设计三原则

1. **description 要精准**：模型看不到你的代码，只能靠 description 判断。`"计算数学表达式"` 比 `"计算"` 好得多。
2. **工具要容错**：工具内部出错时，把错误信息**作为结果回填**给模型（"除数为 0"），让模型自己处理，而不是让程序崩溃。
3. **安全：绝对不要用 `eval`**。用 `ast` 解析 + 白名单节点（不知道 eval/AST 是什么？读下面的**附录 A**）。

---

## 附录 A：eval 和 AST 到底是什么？（本周必读）

### A.1 eval —— 把字符串当"代码"执行

`eval` 是 Python 内置函数，把字符串当作 Python 代码执行并返回结果：

```python
eval("2 + 3")          # -> 5
eval("2 ** 10")        # -> 1024
```

听起来很方便？问题来了——**它能执行任意代码**：

```python
# ⚠️ 危险示例，千万不要运行！
eval("__import__('os').system('dir')")   # 执行系统命令，列出目录！
```

- `__import__('os')`：导入系统库
- `.system('dir')`：调用系统命令

**用户输入的任何字符串如果进了 eval，就等于把你的电脑交给对方**——这叫 RCE（远程代码执行），是最严重的漏洞之一。我们的聊天助手输入来自用户，所以**永远不要用 eval**。

> 想安全地体会一下"eval 能执行任意代码"？（下面这行只读取目录路径，无副作用，可以运行）
> ```python
> # print(eval("__import__('os').getcwd()"))   # 打印当前工作目录——证明 eval 真的执行了代码
> ```

### A.2 AST —— 代码的"解剖图"（只读，不执行）

AST（Abstract Syntax Tree，抽象语法树）是 Python 解析代码时生成的**结构树**。**关键：解析（parse）≠ 执行（run）**。`ast.parse` 只是把代码拆开看结构，什么都不运行：

```python
import ast
tree = ast.parse("2 + 3 * 4", mode="eval")
print(ast.dump(tree, indent=2))
```

输出（表达式被拆成了一棵树）：

```
Expression(
  body=BinOp(
    left=Constant(value=2),
    op=Add(),
    right=BinOp(
      left=Constant(value=3),
      op=Mult(),
      right=Constant(value=4))))
```

- `BinOp` = 二元运算节点（+ - * / **）
- `Constant` = 数字/字符串等字面量节点
- 如果是恶意输入 `__import__('os').system('dir')`，树里会出现 `Call`（函数调用）和 `Attribute`（`.system` 属性访问）节点

### A.3 白名单思路：只放行"认识的安全节点"

安全计算器的思路：**遍历这棵树，只允许白名单里的节点类型（数字、四则运算、幂、正负号），其他一律拒绝**。白名单比黑名单安全——黑名单永远列不全坏人，白名单只放行好人。

```python
import ast, operator

OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

def safe_calculate(expression: str) -> float:
    tree = ast.parse(expression, mode="eval")   # 1. 解析成树（不执行）

    def eval_node(node):
        # 2. 递归遍历，白名单放行
        if isinstance(node, ast.Expression):          # 树根
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value                          # 数字 -> 直接返回
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = eval_node(node.left), eval_node(node.right)
            return OPS[type(node.op)](left, right)     # 二元运算 -> 先算两边
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            val = eval_node(node.operand)
            return val if isinstance(node.op, ast.UAdd) else -val
        raise ValueError(f"不支持的表达式节点: {type(node).__name__}")   # 其他一律拒绝

    return eval_node(tree)
```

**它为什么安全**：恶意输入的树里有 `Call` 和 `Attribute` 节点，`eval_node` 不认识它们 → 直接抛 `ValueError`，代码根本没有执行的机会。

**动手实验**（感受 AST）：
```powershell
# 看 "2+3*4" 的树结构
python -c "import ast; print(ast.dump(ast.parse('2+3*4', mode='eval'), indent=2))"
# 看恶意输入的树结构（会看到 Call 和 Attribute 节点，正是白名单拒绝的原因）
python -c "import ast; print(ast.dump(ast.parse(\"__import__('os').system('dir')\", mode='eval'), indent=2))"
```

---

## 5. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 1~2 + 示例 3 看懂，练习 1–2 | ☐ |
| Day 2 | 2.5h | 练习 3–4（注册表 + 分发） | ☐ |
| Day 3 | 2.5h | 练习 5–6（工具循环），搭 tool_agent 骨架 | ☐ |
| Day 4 | 2.5h | 完成 tool_agent + 自检 + git 提交 | ☐ |

---

## 6. 动手练习（exercises.py）

1. **build_calc_schema**：手写 `safe_calculate` 工具的 JSON Schema
2. **safe_calculate**：ast 白名单安全求值（`(2+3)*4 -> 20.0`；`__import__('os')...` 必须被拒绝）
3. **register_tools**：工具注册表 `{name: function}`（safe_calculate + 自拟 1 个）
4. **execute_tool**：按名字分发执行（参数是 JSON 字符串；未知工具返回错误字符串）
5. **single_tool_turn**：完整单次工具循环（模型选工具 → 执行 → 回填 → 最终回答）
6. **multi_tool_turn**：多工具循环——"北京的天气？顺便算 2^10"应连续触发两个工具

---

## 7. 本周项目：tool_agent.py（工具版聊天助手）

**需求**：交互式助手，能调用 3 个真实工具：

| 工具 | 功能 | 实现要点 |
|---|---|---|
| `get_weather(city)` | 查城市天气 | 复用第二周 Open-Meteo（geocoding + forecast） |
| `get_time(city)` | 查时区时间 | `datetime` + `zoneinfo` |
| `safe_calculate(expr)` | 安全计算 | ast 白名单，绝不用 eval |

```powershell
python tool_agent.py

你> 北京的天气怎么样？
🔧 调用工具: get_weather(city=北京) -> 北京 当前 28.3°C ...
北京现在是 28.3°C，天气晴朗。

你> 那上海呢？顺便算一下 2 的 10 次方
🔧 调用工具: get_weather(city=上海) -> ...
🔧 调用工具: safe_calculate(expression=2**10) -> 1024
...
```

**命令**：`/tools` 列出工具、`/clear` 清空、`/exit` 退出。
**关键设计**：每次调用工具都要 `print("🔧 调用工具: ...")`——**让你亲眼看到模型在"思考"什么**，这是理解 Agent 最重要的一环。

**骨架 TODO（从易到难）**：
1. `safe_calculate(expr)`：ast 白名单求值
2. `get_weather(city)`：httpx 调 Open-Meteo，返回人可读字符串
3. `get_time(city)`：zoneinfo 返回当前时间
4. `execute_tool(name, args)`：注册表分发；工具出错返回错误字符串（不崩溃）
5. `agent_turn(client, messages)`：单轮——有 tool_calls 就执行并回填（打印调用过程），否则返回最终回答
6. `run_agent(client, user_input)`：循环 agent_turn，MAX_TURNS=5，超限给提示
7. `main()`：REPL + `/tools` `/clear` `/exit` + 友好错误

**验收标准**：
- "北京天气" → 正确调用 get_weather 并回答
- "北京的天气？顺便算 2^10" → 一次会话内连续调用两个工具
- "用未知工具名"或工具抛错 → 模型能自己处理（不崩溃）
- 输入恶意表达式（如 `__import__('os').system('dir')`）→ 被 safe_calculate 拒绝

**扩展挑战**：加一个 `save_note(title, content)` 工具（写入本地文件），让模型具备"记忆"能力。

---

## 8. 自检清单（Day 4 结束前）

- [ ] 能画出"模型决定 → 你执行 → 回填 → 再调用"的循环图
- [ ] 能说清为什么 tool 消息必须带 `tool_call_id`
- [ ] 能解释为什么不能用 eval、ast 白名单为什么安全
- [ ] 工具出错时程序不崩溃，错误能回填给模型
- [ ] tool_agent 能连续调用多个工具回答复杂问题

---

## 9. 参考

- DeepSeek Function Calling：https://api-docs.deepseek.com/guides/function_calling
- OpenAI Function Calling：https://platform.openai.com/docs/guides/function-calling
- Anthropic Tool Use：https://docs.anthropic.com/en/docs/build-with-claude/tool-use
