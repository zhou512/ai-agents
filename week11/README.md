# 第十一周：大作业——arXiv 论文调研多 Agent（端到端实战）

> 这是整个课程的收官项目：把 10 周技能组合成一个**能用、能 demo、面试能讲**的完整应用。
> 验收产出：`arxiv_research_agent.py`——输入研究主题，自动搜索 arXiv 真实论文，多 Agent 协作产出带真实链接的调研报告。

---

## 0. 项目一句话

**输入**："AI Agent 综述"
**输出**：一份调研报告（概述 / 各论文要点 / 趋势 / 真实链接），由三个 Agent 协作完成。

```
── 阶段一：工作流（结构化字段，路线 A）──
START → [搜索] 真实 arXiv API 抓 top-5 论文
      → [研究员] 逐篇提炼核心贡献
      → [写手] 写综述初稿（含真实链接）
      → [主编] 评审 ──通过──→ 保存 report.md
                    └──打回──→ 写手修改（≤2 轮）

── 阶段二：报告后自由问答（聊天消息流，路线 B + add_messages）──
用户："第三篇的方法论能展开讲讲吗？" → 多轮对话（历史累积）→ /exit
```

**一个项目两种状态模式（本项目最大的架构看点）**：

| 阶段 | 状态模式 | 为什么 |
|---|---|---|
| 工作流 | 普通字段（papers/notes/draft/verdict 是对象） | 没有消息流，是结构化管道——字段型中间产物最清晰 |
| 问答 | `messages: Annotated[list, add_messages]` | 存在"会自然累积的聊天消息流"——reducer 的主场 |

> 判断标准（通用）：**有没有"会自然累积的同类消息流"？** 有 → reducer；没有 → 字段。
> 问答阶段用 Route B（ChatOpenAI）是因为 `add_messages` 会把消息转成 langchain 对象——必须全程 langchain（第九周教训的正解用法）。

**它综合了你 10 周学到的东西**：

| 技能 | 出处 | 用在哪 |
|---|---|---|
| 真实 HTTP API + 数据解析 | 第 2 周 | 调 arXiv API、解析 Atom XML |
| Prompt 工程（角色/格式/JSON） | 第 4 周 | 三个 Agent 的角色 prompt |
| 多 Agent 协作 + 评审环 | 第 10 周 | 整张图的结构 |
| LangGraph（含第九周的坑） | 第 9 周 | 图编排（记得 write→review 那条边！） |
| JSON mode + 解析容错 | 第 4 周 | 主编的裁决输出 |
| 工具封装思维 | 第 5/6 周 | search_arxiv 独立成函数 |

---

## 1. arXiv API（已验证，免费无需 key）

```python
import httpx

def search_arxiv(topic: str, max_results: int = 5) -> list[dict]:
    """搜索 arXiv 论文，返回 [{"title", "url", "summary"}, ...]。

    注意：必须用 https（http 会 301）；httpx 默认不跟随重定向。
    """
    resp = httpx.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": f"all:{topic}", "start": 0, "max_results": max_results},
        timeout=20,
    )
    root = ET.fromstring(resp.text)
    papers = []
    for entry in root.findall(f"{ATOM}entry"):
        papers.append({
            "title": entry.findtext(f"{ATOM}title", "").strip().replace("\n", " "),
            "url": entry.findtext(f"{ATOM}id", "").strip(),
            "summary": entry.findtext(f"{ATOM}summary", "").strip(),
        })
    return papers
```

**重要细节（我踩过/验证过的）**：
- **用 `https://`**：`http://` 会 301，httpx 默认不跟重定向 → 空响应
- XML 命名空间：所有标签要带前缀 `{http://www.w3.org/2005/Atom}`
- 摘要可能很长（几百到上千字）——**进 LLM 前截断到 ~400 字**，省 token 也防上下文膨胀
- **礼貌使用**：每次搜索间 `time.sleep(3)`；只搜一次 demo 没问题
- 真实局限：`all:ReAct` 会搜到天体物理的 ReACT——搜索相关性一般，报告让模型"如实总结搜到的内容"即可（这也是个可以讲的工程决策：**不假装结果完美，让下游 Agent 知道输入的质量**）

---

## 2. 架构与 State

```python
class ResearchState(TypedDict):
    topic: str                      # 用户主题
    papers: list                    # [{"title","url","summary"}, ...]（已截断）
    notes: str                      # 研究员提炼的各论文贡献
    draft: str                      # 写手初稿
    verdict: str                    # approve / revision
    comments: str                   # 主编意见
    rounds: int                     # 打回次数
```

> 沿用第十周的教训：**纯字段、不用 reducer**；跨 Agent 只交换结构化中间产物。

---

## 3. 三个 Agent 的角色设计

```python
RESEARCHER_PROMPT = """你是论文调研员。用户给了一个研究主题，并提供了搜到的论文（标题+摘要）。
任务：逐篇提炼"这篇论文的核心贡献"，每条 1-2 句，聚焦：解决了什么问题、用什么方法、关键结果。
输出格式：编号列表。每篇论文都覆盖到；如果某篇摘要与主题明显无关，注明"与主题相关性低"。"""

WRITER_PROMPT = """你是调研报告写手。根据【调研要点】撰写约 400-600 字的调研报告。
结构：## 概述 → ## 代表性论文（每篇：标题链接+贡献）→ ## 趋势观察。
论文链接要用原始 URL。如果【主编意见】不为空，必须按意见修改后输出全文。"""

REVIEWER_PROMPT = """你是主编。审阅【初稿】。
只输出 JSON（必须含 "json" 字样）：
{"verdict": "approve" 或 "revision", "comments": "意见"}
标准：是否覆盖所有论文、要点是否准确、结构是否清晰、链接是否保留。"""
```

---

## 4. 里程碑（10 小时，4 天）

| 天 | 目标 | 验收 |
|---|---|---|
| Day 1 | 跑通 `search_arxiv("AI Agent")`，打印论文列表 | 能看到真实论文标题和 URL |
| Day 2 | research_node + writer_node 跑通 | 输出一份有论文要点的初稿 |
| Day 3 | review_node + 环 + build_graph，**整图 mock 测试** | 打回-重写环生效；不踩第十周"漏边"的坑 |
| Day 4 | 阶段二问答图（ChatOpenAI + add_messages）+ 收尾 | 多轮问答有历史记忆；**两种状态模式都能讲** |

---

## 5. 验收标准（自己照着打勾）

- [ ] `python arxiv_research_agent.py` 输入主题 → 控制台显示流程（[搜索]/[研究员]/[写手]/[主编] 各带前缀）
- [ ] 报告包含真实论文链接（现场点开验证）
- [ ] 报告结构：概述 / 代表性论文 / 趋势观察
- [ ] 主编能打回，写手能按意见重写（把 REVIEWER_PROMPT 改成"第一版必打回"验证一次）
- [ ] 摘要截断生效（观察 token 用量合理）
- [ ] report.md 保存成功，格式是 Markdown
- [ ] 报告生成后进入问答阶段，**多轮追问上下文正确**（问"第三篇讲了什么"再追问"它和第一篇比呢"，模型记得前文）——验证 add_messages 累积生效

---

## 6. 面试讲法（demo 时说的话术）

1. **开场**："我给论文调研做了个多 Agent 系统——搜索接的是真实的 arXiv API"
2. **演示**：输入主题，指出每个 Agent 的产出（打印前缀就是干这个的）
3. **架构决策**："搜索是固定第一步（流水线），因为主题总要先搜；但评审用打回环而不是固定两遍——因为修改轮数应该由质量决定，不是拍脑袋"
4. **踩过的坑**（加分项，展示工程成熟度）："LangGraph 编译不检查节点连通性，我漏过一条边导致 review 节点根本没执行——所以我现在跑整图测试"
5. **已知局限**："arXiv 搜索相关性一般，我的研究员会如实标注无关论文——**不假装输入完美**是 Agent 工程的重要原则"
6. **状态模式选型**（这是全项目最亮的一点）："同一个项目我用了两种状态模式——工作流阶段论文/草稿/裁决是结构化字段，因为它们是对象不是消息；报告后问答阶段才有消息流，那里我用 `add_messages` 累积历史。**状态的模式要跟着数据的类型走**——这是我 11 周踩坑换来的判断力"

---

## 7. 扩展挑战（有余力再做）

- **工具化搜索**：让研究员通过 function calling 自己决定搜什么（而不是固定第一步）
- **中文化报告**：研究员提炼中文要点，报告全中文
- **记忆（第 7 周）**：记住用户搜过的主题，下次推荐相关方向
- **多轮追问**：输出报告后问"你对哪篇感兴趣？"展开单篇精读
- **HTML 版报告**：链接可点击的网页版

---

## 8. 安装与目录

```powershell
cd D:\ai-agents\week11
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install openai langgraph langchain-openai httpx
$env:DEEPSEEK_API_KEY = "sk-你的key"
```

项目结构：`project/arxiv_research_agent.py`（主程序）、`project/report.md`（输出，加进 .gitignore 可选）

**去写吧——这是你自己的第一个完整产品。** 遇到问题随时把报错发我；完成后我帮你做最终验收，并且可以帮你把 11 周的学习历程整理成一份**简历项目描述** 🚀
