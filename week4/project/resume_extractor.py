"""简历信息抽取 CLI：读入简历文本，提取结构化信息。

用法：
    python resume_extractor.py resume.txt
    python resume_extractor.py resume.txt --format json

流程：读文件 -> few-shot prompt（JSON 模板 + 示例）-> JSON mode
     -> pydantic 校验 -> 校验失败反馈给模型重试（最多 3 次）-> 输出

前置：设置环境变量 DEEPSEEK_API_KEY（PowerShell: $env:DEEPSEEK_API_KEY = "sk-..."），
      或在项目目录创建 .env（内容一行 DEEPSEEK_API_KEY=sk-...）。

按 TODO 1 → TODO 6 的顺序完成。
"""
from __future__ import annotations
from dotenv import load_dotenv
import argparse
import json
import os
from pathlib import Path
from json import JSONDecodeError
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ValidationError
load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
MAX_RETRIES = 3

# 输出字段模型
class Resume(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    skills: list[str]
    education: list[str]
    years_experience: float | None = None


def load_api_key() -> str:
    """从环境变量读取 Key；缺失时尝试同目录 .env（可用 python-dotenv 或手写解析）。"""
    # TODO 1
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到apikey")
    return key


def read_resume(path: str) -> str:
    """读取简历文件文本；文件不存在或为空时给出明确错误。"""
    # TODO 2
    try:
        with open(path,"r",encoding="utf-8") as f:
            content = f.read()
            if not content.strip():
                raise ValueError("文件为空")
            return content
    except FileNotFoundError:
        raise FileNotFoundError("文件不存在")
    except Exception as e:
        raise IOError(f"读取错误：{e}")


def build_messages(text: str) -> list[dict]:
    """构造 messages。

    system 要求：
    - 角色：资深简历信息抽取助手
    - 任务：从简历文本提取结构化信息，只根据文本内容，不要编造
    - 格式：只输出 JSON（prompt 里必须含 "json" 字样！），字段：
      {"name": "...", "email": "...", "phone": "...",
       "skills": [...], "education": [...], "years_experience": ...}
      缺失字段用 null
    - 给 1 个 few-shot 示例（自己编一小段简历 + 对应 JSON）
    """
    # TODO 3
    sys_prompt = "你是资深简历信息抽取助手，任务：从简历文本提取结构化信息，只根据文本内容，不要编造，格式只输出 JSON（prompt 里必须含 \"json\" 字样！），字段：{\"name\": \"...\", \"email\": \"...\", \"phone\": \"...\",\"skills\": [...], \"education\": [...], \"years_experience\": ...},缺失字段用 null。下面是一段示例：输入：我是李明，邮箱为48979823@163.com，手机号码为17718456879，我擅长ue5引擎的使用以及游戏制作，我本科毕业于华中科技大学，硕士毕业于哈尔滨工业大学，已经有6年的相关工作经验了。输出：{\"name\": \"李明\", \"email\": \"48979823@163.com\", \"phone\": \"17718456879\",\"skills\": [\"ue5引擎使用\",\"游戏制作\"], \"education\": [\"华中科技大学(本)\",\"哈尔滨工业大学(硕)\"], \"years_experience\": 6}"
    messages = [{"role":"system","content":sys_prompt},{"role":"user","content":text}]
    return messages


def extract_json(client: OpenAI, messages: list[dict]) -> dict:
    """JSON mode 调用 + json.loads 解析。解析失败抛异常（留给上层重试）。

    提示：create(..., response_format={"type": "json_object"})
         content = resp.choices[0].message.content
         return json.loads(content)   # 失败抛 json.JSONDecodeError
    """
    # TODO 4
    resp = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return json.loads(content)   # 解析失败让 JSONDecodeError 原样抛出，交给上层重试


def validate_resume(data: dict) -> tuple[Resume | None, str]:
    """pydantic 校验。成功返回 (Resume, "")；失败返回 (None, 错误信息)。"""
    # TODO 5
    try:
        res = Resume.model_validate(data)
        return res,""
    except ValidationError as e:
        return None, str(e)

def extract_resume(client: OpenAI, text: str) -> Resume:
    """组合抽取：extract_json + validate_resume，失败时把错误反馈给模型重试。

    提示：重试时 messages 要追加：
        - assistant 消息：模型上次的输出（原文）
        - user 消息：f"上述 JSON 校验失败：{错误信息}，请修正后重新输出合法 JSON"
    最多 MAX_RETRIES 次；全部失败抛异常（带上最后一次错误）。
    """
    last_error:JSONDecodeError | ValidationError | None = None
    messages = build_messages(text)
    for attempt in range(MAX_RETRIES):
        try:
            data = extract_json(client,messages)
        except (JSONDecodeError,OpenAIError) as e:
            last_error = e
            messages.append({"role": "assistant", "content": "（模型未输出合法 JSON）"})
            messages.append({"role": "user", "content": f"输出不是合法 JSON：{e}，请修正后重新输出"})
            continue
        resume,error = validate_resume(data)
        if not error:
            return resume
        last_error = ValueError(error)
        messages.append({"role":"assistant","content":json.dumps(data)})
        messages.append({"role":"user","content":f"上述 JSON 校验失败：{error}，请修正后重新输出合法 JSON"})
    raise RuntimeError(f"抽取失败（{MAX_RETRIES} 次尝试后）：{last_error}")

def format_readable(r: Resume) -> str:
    """把 Resume 格式化成人类可读文本。"""
    lines = [
        f"姓名: {r.name}",
        f"邮箱: {r.email or '无'}",
        f"电话: {r.phone or '无'}",
        f"技能: {', '.join(r.skills) if r.skills else '无'}",
        f"教育: {'; '.join(r.education) if r.education else '无'}",
        f"工作年限: {r.years_experience if r.years_experience is not None else '未知'}",
    ]
    return "\n".join(lines)


def main() -> None:
    """argparse：位置参数 resume 文件；--format {text,json} 默认 text。友好错误处理。"""
    # TODO 7
    parser = argparse.ArgumentParser(description="抽取简历工具")
    parser.add_argument("path",type=Path,help="待抽取信息的简历")
    parser.add_argument("--format",choices=["json","text"],default="text",help="输出格式，可选择text或json，默认text")
    args = parser.parse_args()
    resume_path = args.path
    output_format = args.format
    try:
        api_key = load_api_key()
    except ValueError as e:
        print(e)
        return
    
    client = OpenAI(api_key=api_key,base_url=BASE_URL)
    try:
        text = read_resume(resume_path)
    except FileNotFoundError as e:
        print(e)
        return
    except IOError:
        print("文件为空")
        return
    try:
        rs = extract_resume(client,text)
        if output_format == "text":
            resp_text = format_readable(rs)
            print(f"简历信息：\n{resp_text}")
        else:
            resp_json = rs.model_dump_json()
            print(f"简历信息：\n{resp_json}")
    except RuntimeError as e:
        print(e)
        return

if __name__ == "__main__":
    main()
