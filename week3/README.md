# 第三周：理解 LLM 与 API（DeepSeek + OpenAI SDK）

> 目标：理解 LLM 核心概念（Token / 上下文窗口 / 采样参数），掌握 LLM API 调用：对话补全、多轮消息、流式输出、错误重试、成本估算。
> 验收产出：一个带流式输出的聊天 CLI（`chat_cli.py`），支持 `/clear`、`/cost`、`/temp` 命令。

---

## 0. 为什么本周至关重要

**大模型 API 就是 Agent 的"大脑"**。到目前为止学的 httpx、pydantic、异步，都是为这一周做准备——Agent 框架（LangGraph 等）的底层，本质上就是封装了"调用 LLM API"这件事。这一周你会第一次真正"和 AI 对话"，而它完全是你自己写的代码。

---

## 1. 前置准备：注册 DeepSeek，获取 API Key（约 15 分钟）

1. 打开 https://platform.deepseek.com 注册账号
2. 进入"API Keys"页面 → 创建 API Key（格式 `sk-...`）→ **复制保存**（只显示一次）
3. 充 10 块钱就够用很久（DeepSeek 很便宜，一个练习对话只要几分钱）
4. 可选的另一家（都兼容 OpenAI 格式）：通义千问 https://dashscope.console.aliyun.com 、智谱 https://open.bigmodel.cn

> ⚠️ **安全铁律：API Key 永远不要提交到 git！** 它等于你的钱包。本周稍后会把 `.env` 加进 `.gitignore`。

## 2. 环境准备

```powershell
cd D:\ai-agents\week3
Remove-Item .venv -Recurse -Force -ErrorAction SilentlyContinue   # 清掉我在沙箱里建的残次 venv
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install openai

# 设置 API Key（PowerShell 会话内临时生效）
$env:DEEPSEEK_API_KEY = "sk-你的key"
```

**验证安装**：
```powershell
python -c "import openai; print(openai.__version__)"
```

---

## 3. 核心概念（必读）

### 3.1 Token —— 模型的最小处理单位

- 模型读写的不是"字"，是 **token**（词元）。计费、上下文窗口都以 token 为单位。
- 粗略换算：**1 个中文字 ≈ 1~1.5 token，1 个英文字 ≈ 0.25 token**（"你好" ≈ 3 token，"hello" ≈ 1-2 token）。
- 实际 token 数由模型的分词器决定，练习 1 会做一个估算器帮你建立直觉。

### 3.2 上下文窗口（Context Window）

- 一次对话中，**输入 + 输出**总共不能超过窗口大小（DeepSeek 约 64K~128K token，以官方文档为准）。
- 超出会报错（context length exceeded）——Agent 开发里最常见的坑之一。
- **推论：messages 历史越长越贵**。控制历史长度 = 控制成本（这是后面"记忆管理"的雏形）。

### 3.3 采样参数（Sampling Parameters）

| 参数 | 作用 | 常用值 |
|---|---|---|
| `temperature` | 随机性：0 接近确定（复读机），越高越有创意 | 0.7（默认），写代码用 0.2，头脑风暴用 1.0+ |
| `max_tokens` | 输出上限 | 默认/按需 |
| `stream` | 是否流式返回（边生成边输出） | 对话类应用建议 True |
| `top_p` | 核采样，一般和 temperature 二选一调 | 默认 |

### 3.4 messages 结构 —— 三角色

```python
messages = [
    {"role": "system", "content": "你是资深 Python 老师，回答要简洁。"},  # 系统设定（可选但强烈建议）
    {"role": "user",   "content": "什么是装饰器？"},                     # 用户
    {"role": "assistant", "content": "装饰器是……"},                     # 助手（模型自己的历史回复）
    {"role": "user",   "content": "举个例子"},                           # 继续追问
]
```
**多轮对话 = 把历史 messages 全部带上重新发一次**（模型本身无状态，这是 Agent 记忆的起点）。

### 3.5 模型选择

| 模型 | 用途 |
|---|---|
| `deepseek-chat` | 通用对话、代码（默认选它） |
| `deepseek-reasoner` | 复杂推理（思维链），更慢更贵 |

### 3.6 费用

- DeepSeek 按 token 计费，价格会变，**以官方定价页为准**：https://api-docs.deepseek.com/quick_start/pricing
- 参考价（2025 年底，输入/输出每百万 token）：deepseek-chat 约 `$0.27 / $1.10`；deepseek-reasoner 约 `$0.55 / $2.19`
- 项目里做了一个 `/cost` 命令帮你实时看花了多少钱

---

## 4. 知识点代码示例（务必亲手敲）

### 4.1 最基础的调用

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
# base_url 必须指到 DeepSeek，否则 SDK 默认连 OpenAI 官方

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "你好，用一句话介绍自己"}],
)
print(resp.choices[0].message.content)      # 回复文本
print(resp.usage.prompt_tokens, resp.usage.completion_tokens)   # 本次用了多少 token
```

### 4.2 流式输出（聊天应用的标准做法）

```python
stream = client.chat.completions.create(
    model="deepseek-chat",
    messages=[{"role": "user", "content": "讲一个冷笑话"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta.content
    if delta:                       # 有些 chunk 的 delta 是 None
        print(delta, end="", flush=True)   # flush=True 立即输出，不要攒着
print()
```

### 4.3 错误处理与重试（指数退避）

```python
import time
from openai import OpenAIError

for attempt in range(3):
    try:
        resp = client.chat.completions.create(model="deepseek-chat", messages=messages)
        break
    except OpenAIError as e:
        wait = 2 ** attempt           # 0s → 2s → 4s，指数退避
        print(f"第 {attempt+1} 次失败: {e}，{wait} 秒后重试")
        time.sleep(wait)
```

> 429（限流）、5xx（服务端错误）都值得重试；4xx 里的 401（key 错）重试没用。

---

## 5. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 注册 key + 概念 3.1~3.2 + 示例 4.1，练习 1–2 | ☐ |
| Day 2 | 2.5h | 概念 3.3~3.4 + 练习 3–4（温度实验） | ☐ |
| Day 3 | 2.5h | 流式 + 重试（4.2~4.3）+ 练习 5–6 | ☐ |
| Day 4 | 2.5h | 完成 chat_cli 项目 + 自检 + git 提交 | ☐ |

---

## 6. 动手练习（exercises.py）

1. **estimate_tokens**：按中英文规则估算文本 token 数（建立直觉）
2. **chat_once**：单轮对话，返回回复
3. **chat_with_history**：传完整 messages（含 system），验证 system 指令生效
4. **explore_temperature**：同一问题在 temperature=0 和 1.5 下各问 3 次，对比稳定性
5. **chat_stream**：流式输出（边生成边打印）
6. **chat_with_retry**：捕获 OpenAIError + 指数退避重试
7. **estimate_cost**（可选）：按价格表算费用

---

## 7. 本周项目：chat_cli.py（流式聊天 CLI）

**需求**：交互式聊天，流式输出，内置命令。

```powershell
python chat_cli.py

你> 讲个笑话
（流式输出……）
（本轮: 输入 24 token / 输出 180 token）
你> /cost
累计费用: $0.0002
```

**命令**：`/help` 帮助、`/clear` 清空历史、`/cost` 看累计费用、`/temp 0.9` 调温度、`/exit` 退出。

**骨架 TODO（从易到难）**：
1. `load_api_key()`：环境变量 + `.env` 文件读取，都没有给友好报错
2. `make_client()`：创建 OpenAI 客户端
3. `estimate_cost()`：token → 美元
4. `chat_stream()`：流式对话，返回 (完整回复, 输入token, 输出token)
5. `run_repl()`：主循环（messages 历史管理 + 命令分发）
6. `main()`：组装入口

**验收标准**：
- 输入问题能流式看到回答逐字出现
- `/cost` 显示的金额和累计 token 正确
- `/clear` 后模型"忘记"之前对话
- 没设 API Key 时给出明确提示而不是一堆 traceback
- 多轮对话上下文正确（问"我叫小明"后问"我叫什么"）

**扩展挑战**：加 `/system <文本>` 临时改系统提示词；历史超过 N 条时自动丢弃最早的对话（控制成本）。

---

## 8. 自检清单（Day 4 结束前）

- [ ] 能解释 token、上下文窗口、temperature 的含义
- [ ] 能说出 messages 三个角色，以及"多轮对话为什么要带全部历史"
- [ ] 能写出流式输出代码，并知道为什么用 `flush=True`
- [ ] 知道哪些错误该重试、为什么用指数退避
- [ ] chat_cli 全部命令跑通，API Key 没有泄漏到 git

---

## 9. 参考链接

- DeepSeek API 文档：https://api-docs.deepseek.com
- DeepSeek 定价：https://api-docs.deepseek.com/quick_start/pricing
- OpenAI Python SDK：https://github.com/openai/openai-python
