# AI Agent 学习记录：13 周，从调 API 到能部署的服务

这是一份**用AI排的 13 周课**(这个README也是AI写的)。出发点是：
「Agent = LLM + 工具 + 记忆 + 循环」这句话我看了很多遍，但讲不出所以然，
所以决定每周做一个能跑的东西，一周一周把这句话拆开。

## 三条原则

1. **先手写，再框架。** 第 6 周不用任何框架手写 ReAct 循环，第 9 周才引入 LangGraph，
   然后把同一条链路重写一遍做对照——不然「会用框架」和「知道框架在干什么」是两回事。
2. **每周必须有一个能跑的产出。** 只看文档不算完成，跑不起来就不算做完。
3. **每周写复盘。** 踩过的坑单独记在
   [`AI-Agent学习复盘-常见错误清单.md`](AI-Agent学习复盘-常见错误清单.md)，
   比笔记本身有用——同一类错误（异步没 await、工具 schema 写错、上下文塞爆、
   结构化输出解析失败）反复出现，说明是模式问题不是运气问题。

## 课程表

| 周 | 主题 | 产出 |
|---|---|---|
| 1 | Python 速成 + 工程工具链 | 独立仓库 [week1-project](https://github.com/zhou512/week1-project)：按类型/日期整理下载目录的 CLI |
| 2 | 网络请求 + 数据建模 | `week2/project/weather_cli.py`：httpx + pydantic 拉天气并用模型结构化 |
| 3 | 理解 LLM 与 API | `week3/project/chat_cli.py`：流式输出的对话 CLI（DeepSeek + OpenAI SDK） |
| 4 | Prompt 工程 | `week4/project/resume_extractor.py`：简历 → 结构化字段，JSON mode |
| 5 | Function Calling | `week5/project/tool_agent.py` + `tools.py`：模型发起调用 → 我执行 → 结果回填 |
| 6 | **手写 ReAct（无框架）** | `week6/project/mini_agent.py`：自己解析 `Thought/Action/Observation`，最多 6 步，`ast` 白名单算数（不用 `eval`） |
| 7 | 记忆与状态 | `week7/project/memory_chat.py`：跨轮记忆的存取与裁剪 |
| 8 | RAG | `week8/project/doc_qa.py`：切块、建索引、检索、拼上下文 |
| 9 | LangGraph | `week9/project/langgraph_agent.py`：同一件事改用图来编排，和 week6 对照 |
| 10 | 多 Agent 协作 | `week10/project/report_workshop.py`：规划者 / 写作者 / 审校者分工 |
| 11 | **端到端大作业** | `week11/project/arxiv_research_agent.py`：arXiv 论文调研多 Agent 工作流 |
| 12 | 评测 | `week12/project/agent_eval.py`：golden set + 规则匹配 + LLM judge + 耗时/成本统计 |
| 13 | 服务化部署 | 独立仓库 [arxiv-research-agent](https://github.com/zhou512/arxiv-research-agent)：FastAPI 服务（pydantic 校验、LRU 缓存、SSE 进度、成本累计、单页前端） |

## 几个我觉得值得看的点

- **week6 的 ReAct 是手写的**：不用 function calling API，让模型输出
  `Thought / Action / Action Input` 的文本协议，我用正则解析、执行工具、把
  `Observation` 塞回对话，循环到 `Final Answer` 或步数上限。
  这样能看清「Agent 循环」到底哪一步会崩（解析不到 Action、工具返回太长、模型忘了格式）。
- **week9 是同一件事的第二种写法**：LangGraph 把 week6 的 while 循环变成节点 + 边，
  状态在节点之间传递。两版放在一起，框架到底替你做了什么就很清楚。
- **week12 开始用数字说话**：正确率（规则命中 + LLM judge）、平均耗时、token 成本。
  没有评测之前，我对自己 Agent 的「感觉还行」基本都是错的。
- **week13 是工程收尾**：把命令行里的东西变成 HTTP 服务——参数校验返回 422、
  相同问题走缓存、长任务用 SSE 推进度、把每次调用的成本累加进 `/stats`。

## 怎么跑

每个 `weekN/` 目录下有独立的 `README.md`（当周目标、原理、验收清单），
项目代码在 `weekN/project/`：

```bash
uv pip install openai httpx pydantic python-dotenv fastapi uvicorn langgraph langchain-openai
export DEEPSEEK_API_KEY="sk-..."      # PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."
python week6/project/mini_agent.py
```

`.env` 里有 key，不提交（见 `.gitignore`）。week11 / week13 的 arXiv 调研会调用网络。

## 一点说明

- 项目文件里保留着 `# TODO 1 … # TODO 5` 的注释，那是我把每周任务拆成的**步骤编号**
  （代码已经实现），不是待办事项。
- `weekN/exercises.py` 是当周的语法/小练习草稿，不重要，没有收进仓库。
- `week1/` 和 `week13/project/` 各自是**独立仓库**（`week1-project`、`arxiv-research-agent`），
  已经单独发布，所以这里不再重复跟踪——它们不出现在本仓库的文件树里。
