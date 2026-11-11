# 第二周：网络请求 + 数据建模（httpx + pydantic）

> 目标：写出"调用 API → pydantic 校验建模 → 格式化输出"的完整程序；掌握异步编程。
> 验收产出：城市天气查询 CLI（`weather_cli.py`），支持并发查询多个城市。

---

## 0. 开始前的提醒

- 如果第一周的 organizer 还没 push 到 GitHub，**先花 10 分钟完成它**——这是本周开始前的收尾。
- 本周所有练习和项目会请求真实公共 API（Open-Meteo，免费、无需 API Key）。
- 教程基于 Open-Meteo 官方文档编写；**请在你自己的终端里运行**，如果请求失败，把报错信息发给我。

---

## 1. 为什么本周对 Agent 至关重要

| 本周知识 | 在 Agent 里的用处 |
|---|---|
| HTTP / httpx | Agent 调用的一切外部工具本质都是 HTTP 请求；LLM API 本身也是 |
| 异步 async/await | 一个 Agent 常要并发调用多个工具、多次模型请求，异步 = 性能关键 |
| pydantic | Agent 框架用 pydantic 定义工具参数 schema、校验模型输出——第 5 周 Function Calling 直接用到 |

---

## 2. 环境准备

```powershell
cd D:\ai-agents\week2
uv venv .venv
.\.venv\Scripts\Activate.ps1
uv pip install httpx pydantic
```

> 每个项目独立虚拟环境——这就是上周学的"虚拟环境"的实际应用。

---

## 3. 知识点（务必亲手敲）

### 3.1 HTTP 基础（20 分钟）

- **URL 结构**：`协议://域名/路径?参数1=值1&参数2=值2`
- **方法**：GET（取数据）、POST（提交数据）——本周只用 GET
- **状态码**：`200` 成功 / `404` 找不到 / `429` 请求太频繁（要重试！）/ `500` 服务器错误
- **响应体**：现代 API 基本都是 JSON

**现在做**：浏览器打开下面的地址，看看返回的 JSON 长什么样：

```
https://api.open-meteo.com/v1/forecast?latitude=39.9&longitude=116.4&current=temperature_2m,weather_code,wind_speed_10m
```

#{"latitude":39.89455,"longitude":116.35983,"generationtime_ms":0.08869171142578125,"utc_offset_seconds":0,"timezone":"GMT","timezone_abbreviation":"GMT","elevation":49.0,"current_units":{"time":"iso8601","interval":"seconds","temperature_2m":"°C","weather_code":"wmo code","wind_speed_10m":"km/h"},"current":{"time":"2026-08-29T01:30","interval":900,"temperature_2m":21.7,"weather_code":3,"wind_speed_10m":0.6}}

### 3.2 httpx 同步请求（重点：timeout！）

```python
import httpx

resp = httpx.get(
    "https://api.open-meteo.com/v1/forecast",
    params={"latitude": 39.9, "longitude": 116.4, "current": "temperature_2m"},
    timeout=10,                      # 必须设！不设可能挂死几分钟
)
resp.raise_for_status()              # 4xx/5xx 直接抛异常，不静默
data = resp.json()                   # 自动把 JSON 转成 Python dict
print(data["current"]["temperature_2m"])
```

> **requests vs httpx**：两者用法几乎一样，但 httpx 支持 HTTP/2 和异步，Agent 生态（LangChain 等）底层常用 httpx。我们直接学 httpx。

### 3.3 JSON

```python
import json
s = json.dumps({"a": 1}, ensure_ascii=False)   # dict -> 字符串
d = json.loads(s)                               # 字符串 -> dict
```
实际开发中**不要手动 `json.loads(resp.text)`**，直接用 `resp.json()`（自动处理编码）。

### 3.4 pydantic（v2）数据建模

```python
from pydantic import BaseModel, ValidationError

class Current(BaseModel):
    temperature_2m: float
    weather_code: int
    wind_speed_10m: float

data = {"temperature_2m": 3.2, "weather_code": 2, "wind_speed_10m": 5.0}
c = Current.model_validate(data)      # v2 的写法；校验+转换一步完成
print(c.temperature_2m)               # 3.2
print(c.model_dump_json())            # 输出 JSON 字符串

try:
    Current.model_validate({"temperature_2m": "abc", "weather_code": 2, "wind_speed_10m": 5.0})
except ValidationError as e:
    print(e)                          # 类型错误会被捕获并给出详细说明
```

**嵌套模型**（API 响应几乎都是嵌套的）：

```python
class Daily(BaseModel):
    time: list[str]
    temperature_2m_max: list[float]

class Forecast(BaseModel):
    current: Current
    daily: Daily

fc = Forecast.model_validate(真实API返回的dict)
```

> ⚠️ pydantic v1 用 `parse_obj()` / `dict()`，v2 用 `model_validate()` / `model_dump()`。网上老教程很多是 v1，注意区分。装到的是 v2。

### 3.5 async/await 异步（本周核心）

**为什么需要异步**：网络请求大部分时间在**等**（等服务器响应）。同步代码等待时 CPU 闲着；异步代码等待时可以去发别的请求。

```python
import asyncio
import httpx

async def fetch(client: httpx.AsyncClient, city: str) -> dict:
    resp = await client.get(f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1")
    return resp.json()

async def main():
    async with httpx.AsyncClient() as client:          # 复用连接，不要每次新建
        results = await asyncio.gather(                # 并发发起所有请求
            fetch(client, "北京"), fetch(client, "上海"), fetch(client, "广州")
        )
    print(results)

asyncio.run(main())        # 程序入口
```

**串行 vs 并发**（每个请求 0.3 秒）：

| 方式 | 3 个请求 | 10 个请求 |
|---|---|---|
| 同步串行 | ~0.9s | ~3s |
| 异步并发 | ~0.3s | ~0.3s |

**关键认知**：异步不提升单个请求的速度，提升的是"并发等待"的效率。Agent 一次要查 N 个工具时，这就是天壤之别。

---

## 4. 时间分配（10 小时，4 天）

| 天 | 时长 | 内容 | 完成 ✓ |
|---|---|---|---|
| Day 1 | 2.5h | 3.1 + 3.2 + 3.3，exercises.py 第 1–2 题 | ☐ |
| Day 2 | 2.5h | 3.4 pydantic，exercises.py 第 3、5 题 | ☐ |
| Day 3 | 2.5h | 3.5 async，exercises.py 第 4 题，开始 weather_cli | ☐ |
| Day 4 | 2.5h | 完成 weather_cli + 自检 + git 提交 | ☐ |

---

## 5. 动手练习（exercises.py）

1. **fetch_status**：请求一个 URL，返回 `(状态码, 耗时秒)`，必须设 timeout。
2. **geocode**：调地理编码 API 查城市经纬度（练 params + 取嵌套字段）。
3. **validate_weather**：用 pydantic 校验 dict，失败时返回错误信息而非崩溃。
4. **fetch_all / compare_sync_async**：异步并发 vs 同步串行，实测时间差距。
5. **fetch_forecast**：用嵌套 pydantic 模型建模真实 API 响应。

---

## 6. 本周项目：weather_cli.py（城市天气查询）

**需求**：输入城市名（支持中文），查询当前天气和未来几天预报。

```powershell
python weather_cli.py 北京
python weather_cli.py 北京 上海 广州          # 并发查询多个城市
python weather_cli.py 北京 --days 3           # 显示未来 3 天预报
```

**用到的两个 API**（均免费无需 Key）：

1. 地理编码（城市名 → 经纬度）：
   ```
   https://geocoding-api.open-meteo.com/v1/search?name=北京&count=1&language=zh
   # 返回 {"results": [{"name": "北京", "latitude": 39.9075, "longitude": 116.39723, ...}]}
   ```
2. 天气预报（经纬度 → 天气）：
   ```
   https://api.open-meteo.com/v1/forecast?latitude=39.9&longitude=116.4&current=temperature_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days=3
   # 返回 {"current": {"temperature_2m": 3.2, "weather_code": 2, "wind_speed_10m": 5.0}, "daily": {...}}
   ```

**骨架 TODO（从易到难）**：
1. `geocode()`：调地理编码 API，找不到城市抛 `ValueError`
2. `fetch_forecast()`：调预报 API，用 `Forecast.model_validate()` 建模
3. `describe()`：天气码 → 中文描述
4. `format_report()`：格式化输出（当前温度/天气/风速 + 未来几天）
5. `fetch_many()`：`AsyncClient` + `asyncio.gather` 并发查多个城市
6. `main()`：argparse（`cities` 多个位置参数 + `--days`），捕获异常打印友好错误

**验收标准**：
- 单城市查询正确显示温度与天气描述
- 多城市查询并发完成，每个城市各输出一段报告
- 不存在的城市给出友好错误（如"未找到城市: 火星"），不崩溃
- 每个请求都有 timeout，API 挂掉时程序能在几秒内报错退出

**扩展挑战**：加 `--format json`（输出 pydantic 的 JSON）；给 429 加指数退避重试。

---

## 7. 自检清单（Day 4 结束前）

- [ ] 能解释 GET/POST、200/404/429 的含义
- [ ] 知道为什么必须设置 timeout
- [ ] 能给任意嵌套 JSON 写出对应的 pydantic 模型并校验
- [ ] 能说清 async/await 为什么对 Agent 重要，并手写一个 `asyncio.gather` 示例
- [ ] weather_cli 单城市、多城市、`--days` 全部跑通
- [ ] 本周项目已提交 GitHub

---

## 8. 参考链接

- Open-Meteo 文档：https://open-meteo.com/en/docs
- httpx 文档：https://www.python-httpx.org
- pydantic v2：https://docs.pydantic.dev
