# AI Agent 学习计划（16 周 · 面向职业发展）

> 适用对象：有编程经验（但 Python/ML 不熟）的学生；每周可投入 10 小时以上；目标是今后的求职与职业发展。
> 总时长：约 16 周（每周 ≥10 小时，合计约 160 小时）。

---

## 一、学习路线总览

| 阶段 | 周期 | 主题 | 核心产出 |
|---|---|---|---|
| 阶段 0 | 第 1–2 周 | Python 与工程基础 | 命令行小工具 + API 脚本 |
| 阶段 1 | 第 3–5 周 | LLM 应用基础（API / Prompt / 工具调用） | 带工具调用的聊天助手 |
| 阶段 2 | 第 6–8 周 | Agent 核心原理（ReAct / 记忆 / RAG） | 手写 ReAct Agent + 文档问答 |
| 阶段 3 | 第 9–11 周 | 框架与实战（LangGraph 等） | 多 Agent 项目 + 端到端项目 |
| 阶段 4 | 第 12–13 周 | 进阶工程化（评测 / 安全 / 部署 / MCP） | 可部署的 Agent 服务 |
| 阶段 5 | 第 14–16 周 | 作品集与求职 | 博客 + 作品集 + 简历 + 面试准备 |

**核心原则**：先手写理解原理，再学框架；每个阶段必须有可展示的产出；用"输出倒逼输入"（写博客、做项目）巩固知识。

---

## 二、阶段 0：Python 与工程基础（第 1–2 周）

> 目标：补齐 Python 与工程工具链，达到能独立写 Agent 代码的水平。

### 第 1 周：Python 速成 + 工具链
- 已有编程经验，重点学 Python 特色语法：类型注解、异常、装饰器、生成器、列表/字典推导式、`dataclass`。
- 环境：VS Code + Jupyter；用 `uv` 或 `conda` 管理虚拟环境；git + GitHub 基本操作。
- **资源**：廖雪峰 Python 教程（速刷前 2/3）、Python 官方 Tutorial、W3Schools 快速参考。
- **产出**：写一个命令行小工具（如：按文件名/日期批量整理下载文件夹）。

### 第 2 周：网络请求 + 数据建模
- `requests`/`httpx` 发起 HTTP 请求；`async/await` 异步基础（Agent 大量依赖异步）。
- JSON 处理、`pydantic` 做数据校验与结构化模型。
- **资源**：httpx 官方文档、pydantic 官方文档。
- **产出**：写一个调用公开 API 的程序（天气/汇率/新闻），把结果用 pydantic 结构化并输出。

---

## 三、阶段 1：LLM 应用基础（第 3–5 周）

> 目标：能熟练调用大模型 API，掌握 Prompt 与工具调用（Function Calling）——这是 Agent 的地基。

### 第 3 周：理解 LLM 与 API
- 核心概念：Token、上下文窗口、温度等采样参数；模型能做什么、不能做什么。
- 选一个 API 上手：推荐 **DeepSeek**（便宜、国内可直连）或 OpenAI/通义千问。学会：对话补全、流式输出、错误处理与重试、成本估算。
- **资源**：DeepSeek / OpenAI 官方文档；李宏毅关于 LLM 的公开课（B 站有中文字幕）。
- **产出**：一个流式输出的聊天 CLI。

### 第 4 周：Prompt 工程
- system/user 消息结构、few-shot 示例、思维链（Chain-of-Thought）、结构化输出（JSON mode）。
- 初步认识提示注入（Prompt Injection）风险。
- **资源**：OpenAI Prompt Engineering Guide；DeepLearning.AI《ChatGPT Prompt Engineering for Developers》（免费短课，2 小时）。
- **产出**：信息抽取工具——从一段简历/新闻中提取结构化字段（姓名、技能、日期等）。

### 第 5 周：Function Calling / 工具使用
- 学会定义 tool schema，让模型在需要时调用你提供的函数；理解"模型生成调用请求 → 你执行 → 结果回填"的循环。
- 自己实现 2–3 个工具：查天气、算数/代码执行、查数据库。
- **资源**：OpenAI Function Calling 文档、Anthropic Tool Use 文档。
- **产出**：一个能"查天气 + 计算 + 查资料"的聊天助手。

✅ **里程碑自检**：能不看教程独立完成一个 Function Calling 应用，并能讲清楚工具调用的数据流。

---

## 四、阶段 2：Agent 核心原理（第 6–8 周）

> 目标：理解 Agent = LLM + 规划 + 工具 + 记忆 + 行动，并**手写**一个最小实现，避免"只会用框架不懂原理"。

### 第 6 周：ReAct 范式（本周最重要）
- 读透 ReAct 论文（Yao et al., 2022）与 Lilian Weng《LLM Powered Autonomous Agents》。
- 读 Anthropic《Building Effective Agents》工程博客。
- **手写**（不依赖任何框架）：一个最小 ReAct Agent——循环执行"思考（Thought）→ 行动（Action/调用工具）→ 观察（Observation）→ 继续"。
- **产出**：`mini_agent/` 目录，包含手写 Agent 源码 + 一个 demo（如自动查资料回答问题）。

### 第 7 周：记忆与状态
- 短期记忆（对话历史与上下文窗口管理、滑动窗口/摘要压缩）。
- 长期记忆（向量数据库存储历史经验，按相关性召回）。
- **资源**：各类 Agent 框架的 memory 文档；《Designing Large Language Model Applications》相关章节。
- **产出**：给手写 Agent 加上长期记忆——多轮对话后仍能回忆起更早的信息。

### 第 8 周：RAG 入门（检索增强生成）
- 嵌入（Embedding）、向量检索、Chunking、重排序（Rerank）；RAG 与 Agent 的关系；RAG 效果如何评估。
- **资源**：DeepLearning.AI《Building and Evaluating Advanced RAG》；LlamaIndex 入门文档。
- **产出**："个人文档问答 Agent"——上传自己的课程资料/笔记，Agent 能基于内容回答。

✅ **里程碑自检**：能不看代码讲清 ReAct 每一步；能独立完成一个带记忆和检索的 Agent。

---

## 五、阶段 3：框架与实战（第 9–11 周）

> 目标：掌握主流框架，做出 1 个完整的多 Agent 项目和 1 个端到端项目。

### 第 9 周：主流框架选型与上手
- 对比：**LangGraph**（图状态机，工程化强）、OpenAI Agents SDK（官方、轻量）、smolagents（Hugging Face，简洁）、CrewAI（多角色友好）、AutoGen。
- **推荐路线**：主攻 LangGraph 或 OpenAI Agents SDK 之一，再用 1–2 天浏览其他框架知道各自定位。
- **资源**：LangGraph 官方教程（agents 系列）；Hugging Face smolagents 免费课程。
- **产出**：用框架重写第 6 周的手写 Agent，写一篇对比笔记（手写 vs 框架的取舍）。

### 第 10 周：多 Agent 协作
- 协作模式：orchestrator-worker（主管分派）、pipeline（流水线）、debate（辩论评审）；图状态机与条件分支；人工介入（human-in-the-loop）。
- **资源**：LangGraph 多 Agent 教程；浏览 MetaGPT / AutoGen 论文或 Demo。
- **产出**："研究员 + 写手"协作 Agent：一个负责检索资料，一个负责撰写报告，最后汇总成文。

### 第 11 周：端到端实战项目 A
从以下选题中选一个（或自拟，标准是"真实解决一个问题"）：
1. 个人知识库问答机器人（含 Web/命令行界面）；
2. 自动整理邮件/周报的 Agent；
3. 论文/资讯调研 Agent（自动爬取、总结、生成调研报告）；
4. 代码审查 Agent（读 PR，给建议）。
- 要求工程化：配置文件、日志、错误处理、单元测试、README。
- **产出**：完整项目 + GitHub 仓库。

✅ **里程碑自检**：有一个能演示的完整项目，能向别人讲清架构图。

---

## 六、阶段 4：进阶与工程化（第 12–13 周）

> 目标：从"能跑"到"能上生产、能讲清楚质量"，这是面试和实习中拉开差距的部分。

### 第 12 周：评测、可观测性与安全
- Agent 评测：任务完成率、正确率、成本、延迟；了解 AgentBench、GAIA 等评测基准。
- Trace 工具：Langfuse / LangSmith 记录每一步调用，定位失败原因。
- 安全：提示注入防护、工具权限最小化、内容安全策略。
- MCP（Model Context Protocol）：了解标准化工具接入协议（Anthropic 提出，生态增长很快）。
- **资源**：AgentBench/GAIA 论文摘要；Langfuse 文档；MCP 官方规范。

### 第 13 周：生产化与 Agent 前沿应用
- 部署：FastAPI 包装成服务、Docker 打包、流式响应；限流与成本优化（模型路由、缓存、降级）。
- 了解前沿应用：编程 Agent（SWE-agent、Cline 的原理）、计算机操作 Agent（Computer Use）。
- **产出**：把第 11 周项目部署成一个可访问的 Web 服务（本地或免费云）。

✅ **里程碑自检**：能回答"你的 Agent 效果怎么评估？失败怎么办？成本怎么控？"。

---

## 七、阶段 5：作品集与求职（第 14–16 周）

### 第 14 周：打磨作品集
- 精选 1–2 个项目精修：README（背景/架构图/效果截图/运行方式）、Demo 视频。
- 写技术博客：至少 1 篇深度长文（如"从零手写一个 ReAct Agent"），同步发布到中文平台（知乎/掘金）+ 可考虑英文版（Dev.to）。
- **理由**：作品集 + 博客是应届生/实习申请中最重要的差异化信号。

### 第 15 周：面试准备
- Agent 系统设计题：如"设计一个客服 Agent / 文档问答 Agent"，练习按 需求→架构→数据→评测→风险 的结构作答。
- 深挖高频问题：ReAct 原理、RAG 全流程与优化、Prompt 注入防护、评测方法论、框架选型理由。
- 保持刷题手感（每天 1 小时算法题，很多公司仍考）。

### 第 16 周：求职落地
- 简历：按"项目背景 / 我做了什么 / 量化成果"重写项目经历。
- 开源贡献：给 smolagents / LangGraph / LangChain 提 issue 或 PR（哪怕修文档）。
- 岗位方向：搜索"Agent 工程师 / LLM 应用工程师 / AI 应用开发实习生"类 JD，对照查漏补缺。
- 投递 + 复盘：每轮面试后记录问题与回答，迭代。

---

## 八、每周节奏模板（10 小时）

| 时间 | 内容 | 备注 |
|---|---|---|
| 3h | 理论学习（课程/文档/论文） | 边看边记笔记 |
| 4h | 动手编码 | 当天学当天写 |
| 2h | 输出（博客/笔记/复盘） | 每周至少 1 篇笔记 |
| 1h | 复习与梳理 | 整理到 Notion/Obsidian |

---

## 九、推荐资源清单（按阶段收藏）

**书籍**
- 《Designing Large Language Model Applications》（O'Reilly，Suhas Pai）——RAG 与 Agent 应用设计，配合第 7–8 周。
- 《AI Engineering》（O'Reilly，Chip Huyen）——偏评估与工程，配合第 12 周。

**课程（免费为主）**
- DeepLearning.AI 系列短课：Prompt Engineering、Function Calling、RAG、Building Agents with OpenAI、LangGraph 系列。
- Hugging Face smolagents 课程（hands-on，强烈推荐）。
- 李宏毅 LLM 公开课（B 站）。
- 书生·浦语 InternLM 实战营（免费，含 Agent 实战，国产大模型生态）。
- DataWhale 开源教程（Agent 实战）。

**必读文章/文档**
- Anthropic《Building Effective Agents》：https://www.anthropic.com/research/building-effective-agents
- Lilian Weng《LLM Powered Autonomous Agents》：https://lilianweng.github.io/posts/2023-06-23-agent/
- OpenAI Cookbook、DeepSeek 文档、MCP 规范。

**必读论文（按优先级）**
1. ReAct: Synergizing Reasoning and Acting in Language Models（2022）
2. Reflexion: Language Agents with Verbal Reinforcement Learning
3. Toolformer: Language Models Can Teach Themselves to Use Tools
4. Generative Agents: Interactive Simulacra of Human Behavior
5. MetaGPT / AutoGen（多 Agent 代表）
6. AgentBench / GAIA（评测基准）

**关注渠道**
- Hugging Face Blog、LangChain/LangGraph Blog、Anthropic Engineering。
- X/Twitter：@AndrewYNg、@CHIPHuyen、@hwchase17、@jerryjliu0。
- 中文社区：知乎 AI 话题、掘金、DataWhale 公众号。

---

## 十、常见误区提醒

1. **不要一上来就学 LangChain**——先手写 ReAct，否则遇到问题无从下手（框架盲）。
2. **不要只抄代码不改**——每个项目都要自己改需求、加功能。
3. **不用深钻模型训练细节**——除非目标岗位是算法工程师；Agent 岗位核心是应用工程能力（API、RAG、评测、部署）。
4. **不要闷头学不输出**——博客、开源贡献、竞赛（智谱/百度/阿里的大模型应用大赛、Kaggle LLM 类目）都是履历亮点。
5. **保持跟随行业**——Agent 领域半年一变，每周花 1 小时扫一遍 Hacker News / 公众号即可。

---

## 十一、进度追踪表

| 周次 | 主题 | 完成情况（✓/✗/进行中） | 本周产出 |
|---|---|---|---|
| 1 | Python 速成 + 工具链 | | |
| 2 | 网络请求 + 数据建模 | | |
| 3 | LLM 与 API | | |
| 4 | Prompt 工程 | | |
| 5 | Function Calling | | |
| 6 | ReAct 手写实现 | | |
| 7 | 记忆与状态 | | |
| 8 | RAG 入门 | | |
| 9 | 框架上手 | | |
| 10 | 多 Agent 协作 | | |
| 11 | 端到端项目 A | | |
| 12 | 评测/安全/MCP | | |
| 13 | 生产化部署 | | |
| 14 | 作品集与博客 | | |
| 15 | 面试准备 | | |
| 16 | 求职落地 | | |
