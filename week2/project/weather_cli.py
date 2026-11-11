"""城市天气查询 CLI：输入城市名（支持中文），查询当前天气和未来几天预报。

用法：
    python weather_cli.py 北京
    python weather_cli.py 北京 上海 广州            # 并发查询多个城市
    python weather_cli.py 北京 --days 3             # 显示未来 3 天预报

用到的两个公共 API（免费、无需 Key）：
    地理编码: https://geocoding-api.open-meteo.com/v1/search?name={城市}&count=1&language=zh
    天气预报: https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
              &current=temperature_2m,weather_code,wind_speed_10m
              &daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days={days}

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations

import argparse
import asyncio
import httpx
from pydantic import BaseModel, ValidationError

GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 天气码 -> 中文描述（可自行扩充）
WEATHER_CODES: dict[int, str] = {
    0: "晴朗", 1: "基本晴朗", 2: "多云", 3: "阴天",
    45: "雾", 48: "雾凇",
    51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨",
    71: "小雪", 73: "中雪", 75: "大雪",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    85: "阵雪", 86: "强阵雪",
    95: "雷暴", 96: "雷暴伴冰雹", 99: "强雷暴伴冰雹",
}


# ---------- pydantic 模型 ----------
class GeocodeResult(BaseModel):
    name: str
    latitude: float
    longitude: float


class CurrentWeather(BaseModel):
    temperature_2m: float
    weather_code: int
    wind_speed_10m: float


class DailyWeather(BaseModel):
    time: list[str]
    temperature_2m_max: list[float]
    temperature_2m_min: list[float]


class Forecast(BaseModel):
    current: CurrentWeather
    daily: DailyWeather


# ---------- 核心函数 ----------
async def geocode(client: httpx.AsyncClient, city: str) -> GeocodeResult:
    """调 GEO_URL 查城市经纬度。

    提示：resp.json() 结构 {"results": [{"name":.., "latitude":.., "longitude":..}, ...]}
    要求：results 为空时 raise ValueError(f"未找到城市: {city}")
    """
    # TODO 1
    try:
        resp = await client.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh",
            timeout = 10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results",[])
        if not results:
            raise ValueError(f"未找到城市: {city}")
        return GeocodeResult.model_validate(results[0])
    except Exception as e:
        raise ValueError(f"查询失败:{e}")


async def fetch_forecast(client: httpx.AsyncClient, lat: float, lon: float, days: int) -> Forecast:
    """调 FORECAST_URL，用 Forecast.model_validate(resp.json()) 建模返回。

    提示：用 params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto",
                    "forecast_days": days}
    """
    # TODO 2
    resp = await client.get(
        "https://api.open-meteo.com/v1/forecast",
        params={"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code,wind_speed_10m",
                    "daily": "temperature_2m_max,temperature_2m_min", "timezone": "auto",
                    "forecast_days": days},
        timeout=10
    )
    data = resp.json()
    try:
        fc = Forecast.model_validate(data)
        return fc
    except ValidationError as e:
        errors = e.errors()
        detail = ";".join(f"{err["loc"][0]}:{err["msg"]}" for err in errors)
        raise ValueError (f"校验失败:{detail}")


def describe(code: int) -> str:
    """用 WEATHER_CODES 查天气码描述，查不到返回 "未知"（不要抛异常）。"""
    # TODO 3
    if code in WEATHER_CODES.keys():
        return WEATHER_CODES.get(code)
    else:
        return "未知"


def format_report(city: str, fc: Forecast) -> str:
    """把 Forecast 格式化成多行文本。

    期望输出示例：
    === 北京 ===
    当前: 3.2°C, 多云, 风速 5.0 km/h
    未来 3 天:
      01-15: 最高 1.2°C / 最低 -6.3°C
      01-16: 最高 4.0°C / 最低 -4.1°C
    ...
    提示：daily.time[i] 是 "2025-01-15"，取 [5:] 得到 "01-15"
    """
    # TODO 4
    desc = describe(fc.current.weather_code)
    lines = [f"=== {city} ===", f"当前: {fc.current.temperature_2m}°C, {desc}, 风速 {fc.current.wind_speed_10m} km/h"]
    lines.append(f"未来 {len(fc.daily.time)} 天:")
    for i in range(len(fc.daily.time)):  # 安全取前3个
        date_str = fc.daily.time[i][5:]  # 取 MM-DD
        max_t = fc.daily.temperature_2m_max[i]
        min_t = fc.daily.temperature_2m_min[i]
        lines.append(f"  {date_str}: 最高 {max_t}°C / 最低 {min_t}°C")
    return "\n".join(lines)

async def fetch_one(client:httpx.AsyncClient,city:str,days:int) ->str:
    try:
        g_res =await geocode(client=client,city=city)
        fc =await fetch_forecast(client,g_res.latitude,g_res.longitude,days) 
        repo = format_report(city,fc)
        return repo
    except Exception as e:
        return f"=== {city} ===\n错误: {e}"

async def fetch_many(cities: list[str], days: int) -> list[str]:
    """并发查询所有城市，返回报告字符串列表。

    提示：async with httpx.AsyncClient() as client:
        async def one(city): 先 await geocode 的异步版本，再 fetch_forecast，返回 format_report
    注意：httpx 异步客户端是 AsyncClient，方法都要 await；练习里练过 gather。
    错误处理：单个城市失败时返回 f"=== {city} ===\n错误: {e}"，不要中断其他城市。
    """
    # TODO 5
    async with httpx.AsyncClient() as client:
        tasks = [fetch_one(client,city,days) for city in cities]
        return await asyncio.gather(*tasks)
    


def main() -> None:
    """argparse：cities 位置参数（nargs="+"），--days 默认 1；输出所有报告。"""
    # TODO 6
    parser = argparse.ArgumentParser(description="天气查询工具")
    parser.add_argument("cities",nargs="+",help="要查询的城市（可多个）")
    parser.add_argument("--days",type=int,default=1,help="未来预报天数")
    args = parser.parse_args()
    reports = asyncio.run(fetch_many(args.cities,args.days))
    for report in reports:
        print(report)
        print("-" * 40)


if __name__ == "__main__":
    main()
