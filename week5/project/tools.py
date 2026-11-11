from __future__ import annotations
import httpx
import ast
import json
import operator
import os
from pydantic import BaseModel, ValidationError
from openai import OpenAI
from dotenv import load_dotenv
OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
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

class WeatherCurrent(BaseModel):
    temperature_2m: float
    weather_code: int
    wind_speed_10m: float

class DailyWeather(BaseModel):
    time: list[str]
    temperature_2m_max: list[float]
    temperature_2m_min: list[float]


class Forecast(BaseModel):
    current: WeatherCurrent
    daily: DailyWeather

def geocode(city: str) -> tuple[float, float]:
    """用 Open-Meteo 地理编码 API 查城市，返回第一个结果的 (纬度, 经度)。

    URL: https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh
    期望: geocode("北京") -> (39.9075, 116.39723) 左右
    查不到时 raise ValueError(f"未找到城市: {city}")
    提示：resp.json() 的结构是 {"results": [{"name":..., "latitude":..., "longitude":...}, ...]}
    """
    resp = httpx.get(
            f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=zh",
            timeout=10,
        )
    resp.raise_for_status()
    data = resp.json()
    results = data.get("results")
    if not results:
        raise ValueError(f"未找到城市:{city}")
    ans = (data["results"][0]["latitude"],data["results"][0]["longitude"])
    return ans

def fetch_forecast(lat: float, lon: float, days: int = 3) -> Forecast:
    """请求预报 API，用 Forecast.model_validate(resp.json()) 建模返回。

    URL: https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}
         &current=temperature_2m,weather_code,wind_speed_10m
         &daily=temperature_2m_max,temperature_2m_min&timezone=auto&forecast_days={days}
    期望: fetch_forecast(39.9075, 116.39723).current.temperature_2m 是 float
    """
    resp = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude":lat,
            "longitude":lon,
            "current":"temperature_2m,weather_code,wind_speed_10m",
            "daily":"temperature_2m_max,temperature_2m_min",
            "timezone":"auto",
            "forecast_days":days
        },
        timeout=10
    )
    data = resp.json()
    fc = Forecast.model_validate(data)
    return fc

def get_weather(city:str) -> str:
    lat,lon = geocode(city)
    fc =  fetch_forecast(lat,lon,1)
    weather_desc = f"{city}:{WEATHER_CODES.get(fc.current.weather_code,"未知")}，温度为{fc.current.temperature_2m},风速{fc.current.wind_speed_10m}"
    return weather_desc

def safe_calculate(expression: str) -> float:
    """用 ast 白名单求值，绝不用 eval。

    期望: safe_calculate("(2+3)*4") -> 20.0
    期望: safe_calculate("2 ** 10") -> 1024.0
    期望: safe_calculate("__import__('os').system('dir')") -> 抛 ValueError/异常（必须被拒绝！）

    提示（详细版，先看 README 附录 A 弄懂 eval 和 AST 再写）：
    1) tree = ast.parse(expression, mode="eval")   # 解析成树（不执行！）
    2) 定义一个内部递归函数 eval_node(node)：
       - ast.Expression             -> 递归 eval_node(node.body)
       - ast.Constant 且值是 int/float -> 返回 node.value
       - ast.BinOp 且 type(node.op) 在 OPS 里 -> 先递归算左右子节点，再 OPS[type(node.op)](左, 右)
       - ast.UnaryOp 且 op 是 UAdd/USub -> 递归算 operand，正号返回原值，负号取反
       - 其他任何节点（Call、Attribute 等）-> raise ValueError(f"不支持的表达式节点: {type(node).__name__}")
    3) return eval_node(tree)
    """
    tree = ast.parse(expression,mode="eval")
    def eval_node(node):
        if isinstance(node,ast.Expression):
            return eval_node(node.body)
        if isinstance(node,ast.Constant) and isinstance(node.value,(float,int)):
            return node.value
        if isinstance(node,ast.BinOp) and type(node.op) in OPS:
            left,right = eval_node(node.left),eval_node(node.right)
            return OPS[type(node.op)](left,right)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            val = eval_node(node.operand)
            return val if isinstance(node.op,ast.UAdd) else -val
        raise ValueError(f"不支持的表达式节点:{type(node).__name__}")
    return eval_node(tree)

def execute_tool(registry: dict, name: str, args_json: str) -> str:
    """按名字分发执行。

    - args_json 是 JSON 字符串，先 json.loads 成 dict，再 f(**args) 调用
    - 未知工具 -> 返回 f"未知工具: {name}"（字符串，不抛异常）
    - 参数不匹配（TypeError）-> 返回错误字符串
    期望: execute_tool({"hello": lambda name: f"你好，{name}！"}, "hello", '{"name": "小李"}')
        -> "你好，小李！"
    """
    args = json.loads(args_json)
    f = registry.get(name)
    if not f:
        return f"未知工具:{name}"
    try:
        res = f(**args)
        return res
    except TypeError as e:
        return f"参数不匹配:{e}"