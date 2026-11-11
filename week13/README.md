# 第十三周：生产化部署——把 Agent 变成可访问的服务

> 目标：用 FastAPI 把你的 Agent 包装成 HTTP 服务（含 pydantic 校验、流式响应、健康检查、成本统计、缓存与限流），了解 Docker 与 Agent 前沿应用。
> 验收产出：`agent_service.py`——启动后可用 `curl`/浏览器访问的问答服务，带 `/stats` 成本监控。

---

## 0. 为什么这周重要：从 demo 到产品

你 11 周的 Agent 都是"命令行里自己玩"。**服务化的意义：别人能用你的 Agent**——前端、其他服务、同事，都通过 HTTP 调用它。这也是"部署"在工程岗位里的常规含义。

**关键心智：Agent = 黑盒函数**。你的 arXiv 大作业本质是：

```python
def my_agent(question: str) -> str: ...   # 输入问题，输出回答
```

服务化 = 在这层壳外面套 HTTP 层，**Agent 本身一行不用改**。这周的一切都建立在这个可插拔结构上。

---

## 1. 服务化的分层（先想清楚拆几层）

| 层 | 职责 | 对应代码 |
|---|---|---|
| **接口层** | 收 HTTP 请求、校验参数、返回 JSON | FastAPI 路由 + pydantic 模型 |
| **业务层** | 调你的 Agent（黑盒） | `agent_fn(question)` |
| **横切层** | 缓存 / 限流 / 统计 / 错误处理 | 装饰器或中间件 |

**顺序**：先接口层跑通 → 再接业务层 → 最后加横切层。别一上来全堆上。

---

## 2. FastAPI 最小入门（pydantic 是你的老朋友了）

第四周的 pydantic 直接复用——FastAPI 用它做**请求校验和响应模型**：

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="我的 Agent 服务")

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000, description="用户问题")
    temperature: float | None = None          # 可选参数

class AskResponse(BaseModel):
    answer: str
    cost_usd: float

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    try:
        answer = my_agent(req.question)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent 调用失败: {e}")
    return AskResponse(answer=answer, cost_usd=0.0)
```

**启动**：
```powershell
uvicorn agent_service:app --reload --port 8000
# 浏览器/curl 访问：
#   http://127.0.0.1:8000/health
#   curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"question": "什么是装饰器？"}'
```

**三个要点**：
1. **参数校验交给 pydantic**（`Field(min_length=...)`）——别自己在函数里 if 判断
2. **永远返回结构化错误**（`HTTPException` + detail），不要把裸 traceback 发给用户
3. **`response_model` 声明输出结构**——文档（/docs 自动生成）和调用方都受益

---

## 3. 流式响应（SSE）——聊天体验的关键

**为什么流式**：用户等完整回答要几秒；流式让第一个字 0.5 秒就出现（TTFT，time-to-first-token）——体验差异巨大。

```python
from fastapi.responses import StreamingResponse
import asyncio, json

def stream_answer(question: str):
    """生成器：逐块产出 SSE 格式内容。"""
    for chunk in my_agent_stream(question):          # 你的 Agent 的流式版本
        yield f"data: {json.dumps({'delta': chunk}, ensure_ascii=False)}\n\n"

@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    return StreamingResponse(stream_answer(req.question),
                             media_type="text/event-stream")
```

SSE 格式：`data: {JSON}\n\n`（每个事件以空行结尾）。前端用 EventSource/fetch 逐块读。

> 如果 Agent 目前是同步的，先做同步版；流式版需要 Agent 支持逐块产出（DeepSeek API 的 stream=True 你第三周就学过）——**这是扩展挑战**。

---

## 4. 健康检查与成本统计（横切层的两个基本件）

```python
# 进程内统计（真实产品用 Redis/Prometheus，这里演示概念）
STATE = {"calls": 0, "total_tokens": 0, "total_cost_usd": 0.0}

@app.get("/stats")
def stats() -> dict:
    return STATE
```

**为什么 /health 和 /stats 重要**：
- `/health`：负载均衡/容器编排（K8s/Docker）靠它判断实例活没活
- `/stats`：线上成本可视化的第一步——没有数字，优化无从谈起（第十二周精神）

---

## 5. 缓存与限流（成本优化的两个杠杆）

**缓存**：相同问题在短时间内重复调用 = 白烧钱。加一层"问题 → 回答"缓存：

```python
class AnswerCache:
    def __init__(self, maxsize: int = 100):
        self.data: dict[str, tuple[str, float]] = {}   # question -> (answer, time)
        self.maxsize = maxsize
        self.hits = 0
        self.misses = 0

    def get(self, question: str) -> str | None:
        entry = self.data.get(question)
        if entry:
            self.hits += 1
            return entry[0]
        self.misses += 1
        return None

    def put(self, question: str, answer: str) -> None:
        if len(self.data) >= self.maxsize:      # 简单淘汰：清空（LRU 是进阶）
            self.data.clear()
        self.data[question] = (answer, time.time())
```

**限流**：防止刷爆你的钱包（有人循环调你的接口）。滑动窗口计数：

```python
import time
class SlidingWindowLimiter:
    """每 key 每分钟最多 limit 次。"""
    def __init__(self, limit: int = 10, window: float = 60.0):
        self.limit, self.window = limit, window
        self.records: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.time()
        times = [t for t in self.records.get(key, []) if now - t < self.window]
        if len(times) >= self.limit:
            self.records[key] = times
            return False
        times.append(now)
        self.records[key] = times
        return True
```

**原则**：缓存挡"重复请求"，限流挡"恶意/失控请求"——两个都是省钱护栏。

---

## 6. Docker 打包（可选扩展；没装 Docker 就看概念）

把服务镜像化，任何机器 `docker run` 即用：

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "agent_service:app", "--host", "0.0.0.0", "--port", "8000"]
```

```powershell
docker build -t my-agent .
docker run -p 8000:8000 -e DEEPSEEK_API_KEY=sk-... my-agent
```

概念：镜像 = 可复现的环境快照；容器 = 隔离的运行单元。**API Key 用环境变量注入，绝不写进镜像**（第八周教训）。

---

## 7. 前沿应用了解（Agent 的前沿形态，知道即可）

- **编程 Agent**：SWE-bench 时代的产物——给 Agent 一个 GitHub issue，它改代码跑测试。代表：SWE-agent、Cline、Devin
- **Computer Use**：让模型"看屏幕、点鼠标、敲键盘"操作真实软件。Anthropic Computer Use / OpenAI Operator
- **你的位置**：这些是"工具调用"的极端延伸——工具从"天气 API"变成"终端/浏览器"。原理（模型决定→你执行→回填）你已经全懂了，只是执行层换成更强大的工具

---

## 8. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 概念 0~2（分层/FastAPI），练习 1–2 | ☐ |
| Day 2 | 2.5h | 概念 3~4（流式/健康统计），练习 3–4 | ☐ |
| Day 3 | 2.5h | 概念 5（缓存限流），练习 5–6，搭 agent_service | ☐ |
| Day 4 | 2.5h | 完成 agent_service + curl 实测 + （可选）Docker | ☐ |

---

## 9. 动手练习（exercises.py，全部本地可测，需要 fastapi）

1. **build_minimal_app**：FastAPI 应用，GET /health 返回 {"status": "ok"}
2. **define_schemas**：AskRequest（question 必填、1-2000 字）/ AskResponse（answer + cost_usd）——用 pydantic Field
3. **sse_format**：把文本切成块，产出 SSE 格式字符串（`data: {...}\n\n`）
4. **AnswerCache**：缓存类（get/put/命中率统计；超 maxsize 清空）
5. **SlidingWindowLimiter**：滑动窗口限流（allow(key) 逻辑）
6. **test_endpoints**：用 `fastapi.testclient.TestClient` 对最小 app 发请求，验证 /health 200 和 /ask 的校验（缺 question 应 422）

---

## 10. 本周项目：agent_service.py（问答 Agent 服务化）

**需求**：把"问题→回答"的 Agent 包成 FastAPI 服务（内置一个问答 Agent 作为被测对象，可换成你的 arXiv 问答阶段）。

```powershell
uvicorn agent_service:app --reload --port 8000
# 浏览器打开 http://127.0.0.1:8000/docs 就能交互测试！
```

**端点**：
- `GET /health` → {"status": "ok"}
- `POST /ask` → {answer, cost_usd, elapsed_ms}（pydantic 校验）
- `GET /stats` → 进程内累计（calls / total_tokens / total_cost / cache_hits）
- 缓存：相同问题直接返回缓存答案（命中率进 /stats）
- 错误：Agent 调用失败 → HTTPException 结构化错误

**骨架 TODO**：
1. `AskRequest` / `AskResponse`（pydantic + Field 约束）
2. `ask_agent(question)`：内置问答 Agent（统计 token → 返回 (answer, usage)）
3. 缓存接入：/ask 先查缓存，未命中才调 Agent
4. `/ask` 路由：校验 → 缓存 → Agent → 统计 → 响应
5. `/stats` + `/health` 路由
6. `main`/启动说明 + 简单 `if __name__` 自测（TestClient 打一发）

**验收标准**：
- `uvicorn` 启动无报错，/docs 可交互
- `curl -X POST .../ask -d '{"question":"什么是装饰器？"}'` 返回 JSON 回答 + cost
- 连续两次相同问题 → 第二次走缓存（/stats 里 cache_hits +1）
- 缺 question / 超长 question → 422 结构化错误（不是裸 traceback）
- /stats 数字在增长且合理

**扩展挑战**：把第 12 周评测的 `/eval` 端点也接进来（服务自带质检）；SSE 流式版；Docker 镜像化。

---

## 11. 自检清单（Day 4 结束前）

- [ ] 能画出"接口层/业务层/横切层"并说出各自职责
- [ ] 为什么参数校验交给 pydantic 而不是手写 if？
- [ ] 缓存和限流各自防的是什么？为什么是"省钱护栏"？
- [ ] /health 和 /stats 在生产里分别被谁用？
- [ ] agent_service 用 curl 完整跑通（含缓存命中与 422 错误）

---

## 12. 参考

- FastAPI 官方教程：https://fastapi.tiangolo.com/tutorial/
- SSE 规范：https://developer.mozilla.org/zh-CN/docs/Web/API/Server-sent_events
- uvicorn：https://www.uvicorn.org
- Anthropic Computer Use / 各家编程 Agent 博客
