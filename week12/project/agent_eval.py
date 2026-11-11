"""可插拔 Agent 评测工具：对任意"问题→回答"的 Agent 跑测试集，输出指标报告。

用法：
    python agent_eval.py                 # 内置示例：好/坏两个 Agent 对比
    python agent_eval.py --json          # 输出 JSON 结果（供程序消费）

评测维度：正确性（规则+LLM-judge）/ 效率（耗时）/ 成本（token 估算）。

把被测对象换成你自己的 Agent：定义一个 agent_fn(question) -> str 的函数，
传给 run_eval_suite 即可（见文件底部 sample_agent_good 的写法）。

安装：uv pip install openai
前置：设置环境变量 DEEPSEEK_API_KEY（或项目目录 .env）

按 TODO 1 → TODO 7 的顺序完成。
"""
from __future__ import annotations
from json import JSONDecodeError
import json
import os
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()
MODEL = "deepseek-chat"
BASE_URL = "https://api.deepseek.com"
PRICES = (0.27, 1.10)   # 输入/输出 每百万 token 美元
CASES_FILE = Path(__file__).parent / "golden_set.json"

# 示例测试集（可扩展；也可改成从 CASES_FILE 读）
GOLDEN_SET = [
    {"question": "装饰器的本质是什么？",
     "expect_contains": ["接收函数", "返回函数"],
     "criteria": "是否准确解释装饰器是'接收函数并返回函数的函数'",
     "category": "概念"},
    {"question": "装饰器和普通函数调用的区别是什么？",
     "expect_contains": ["函数"],
     "criteria": "是否说明装饰器在不改原函数代码的情况下增强其功能",
     "category": "对比"},
    {"question": "什么时候应该用装饰器？",
     "expect_contains": ["日志", "计时", "权限", "缓存"],   # 任一命中即可
     "criteria": "是否给出装饰器的实际应用场景",
     "category": "应用"},
]


# ---------- 被测 Agent（可插拔；换你自己的就替换这些函数） ----------
client : OpenAI | None = None
def load_api_key() -> str:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("未找到 API Key：请设置环境变量 DEEPSEEK_API_KEY")
    return key

def make_client() -> OpenAI:
    global client
    if not client:
        client = OpenAI(api_key=load_api_key(),base_url=BASE_URL)
    return client

def _ask(question: str, system_prompt: str) -> str:
    """调 DeepSeek 回答（不带工具，评测"回答质量"用）。"""
    resp = make_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": question}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def sample_agent_good(question: str) -> str:
    """好 Agent：专业的 Python 老师角色。"""
    return _ask(question, "你是资深 Python 老师，回答准确、举例清晰。")


def sample_agent_bad(question: str) -> str:
    """坏 Agent：故意写坏——回答固定且错误，用于演示评测能暴露差距。"""
    return "装饰器就是语法糖，没什么特别的。"


# ---------- 评测核心（TODO） ----------
def load_cases(path: Path = CASES_FILE) -> list[dict]:
    """读测试集 JSON；文件不存在时用内置 GOLDEN_SET（打印提示）。"""
    # TODO 1
    try:
        cases_json = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return GOLDEN_SET
    try:
        cases = json.loads(cases_json)
        if not isinstance(cases,list):
            print("测试集格式不合法")
            return []
        else:
            return cases
    except JSONDecodeError as e:
        print(f"json解析失败：{e}")


def rule_checker(answer: str, expect_contains: list[str], require_all: bool = False) -> bool:
    """检查回答是否包含期望内容。

    require_all=True  -> 必须包含全部；False -> 包含任一即可。
    期望: rule_checker("装饰器是接收函数并返回函数的函数", ["接收函数", "返回函数"]) -> True
    期望: rule_checker("装饰器就是语法糖", ["接收函数", "返回函数"]) -> False
    """
    if require_all:
        for word in expect_contains:
            if word not in answer:
                return False
        return True
    else:
        for word in expect_contains:
            if word in answer:
                return True
        return False

    
def structural_checker(answer_json: str, required_fields: dict) -> tuple[bool, str]:
    try:
        answer = json.loads(answer_json)
    except JSONDecodeError as e:
        return False, f"json校验失败，传入的不是合法json，错误信息:{e}"

    required_keys = set(required_fields.keys())
    if not required_keys <= set(answer.keys()):
        missing = required_keys - set(answer.keys())
        return False, f"answer中缺少应有的字段: {', '.join(missing)}"

    type_map = {"str": str, "int": int, "list": list, "dict": dict}
    for key, expected_type_name in required_fields.items():
        expected_type = type_map.get(expected_type_name)
        if expected_type is None:
            continue
        if not isinstance(answer.get(key), expected_type):
            return False, f"{key}字段不是合法的{expected_type_name}类型"
    return True, ""

def judge_case(client: OpenAI, question: str, answer: str, criteria: str) -> dict:
    """让 LLM 按评分锚点打分，返回 {"score": 1-5, "reason": "..."}。

    system 要求（缓解偏置的关键）：
    - 评分锚点：1=完全错误/编造，2=大部分错误，3=部分正确，4=基本正确有小瑕疵，5=准确完整
    - "先给理由再给分"；只输出 JSON {"score": 整数, "reason": "理由"}
    期望: 对"装饰器的本质？" 回答 "装饰器是接收函数并返回函数的函数" -> score >= 4
    """
    sys_prompt = """你是一个给某个问题的回答打分的助理，你会收到一个问题，一个答案，一个评分标准，你需要根据评分标准对答案进行评价，输出要求如下：
    1.评分锚点：1=完全错误/编造，2=大部分错误，3=部分正确，4=基本正确有小瑕疵，5=准确完整。
    2.先给评分的理由，再给出分数。
    3.输出格式：只输出 JSON {"score": 整数, "reason": "理由"}，不要有任何多余字段
    期望：对"装饰器的本质？" 回答 "装饰器是接收函数并返回函数的函数"，你的输出应类似于：{"score": 4, "reason": "回答简洁准确"}"""
    messages = [{"role":"system","content":sys_prompt},{"role":"user","content":f"对于{question}这个问题，回答：{answer}，评分标准：{criteria},请给出你的评价"}]
    for _ in range(2):
        resp = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.3
        )
        content = resp.choices[0].message.content
        is_valid, error = structural_checker(content, {"score": "int", "reason": "str"})
        if is_valid:
            return json.loads(content)
        # 校验失败：把错误反馈给模型，进入下一轮重试
        messages.append({"role":"assistant","content":f"输出的json校验失败，请严格按照输出格式输出，错误信息:{error}"})
    # 重试耗尽才放弃（return 必须在循环外！）
    print("评分失败，已达到最大尝试次数2次")
    return {"score": -1, "reason": ""}


def run_case(agent_fn, case: dict, llm_judge, judge_client: OpenAI | None = None) -> dict:
    content = agent_fn(case.get("question"))
    rule_pass = rule_checker(content, case.get("expect_contains"), False)
    result = {
        "question": case.get("question"),
        "answer": content,
        "rule_pass": rule_pass,
        "category": case.get("category")
    }
    if llm_judge and judge_client:
        llm_comment = judge_case(judge_client, case.get("question"), content, case.get("criteria"))
        result["score"] = llm_comment.get("score", -1)
        result["reason"] = llm_comment.get("reason", "")
    return result

def run_eval_suite(agent_fn, cases: list[dict],llm_judge, judge_client: OpenAI | None = None) -> dict:
    """批量评测：对每个用例 run_case，汇总指标。

    metrics: {"total", "rule_pass", "rule_rate", "avg_score", "failures"}
    """
    # TODO 5
    total_score = 0
    total_passes = 0
    total_failures = 0
    failure_cases = []
    for case in cases:
        record = run_case(agent_fn,case,llm_judge,judge_client)
        if llm_judge:
            if record.get("score",-1) >= 0:
                total_score += record["score"]
            else:
                total_failures += 1
                failure_cases.append({"question":f"{record.get("question")}","answer":f"{record.get("answer")}"})
        if record["rule_pass"]:
            total_passes += 1
    return {"total":len(cases),"rule_pass":total_passes,"rule_rate":(total_passes / len(cases)) if len(cases) else 0,"avg_score": total_score / (len(cases) - total_failures) if llm_judge and len(cases) - total_failures else -1,"failures":total_failures,"failure_cases":failure_cases}

def report(metrics: dict, agent_name: str) -> str:
    """把指标格式化成人类可读报告（markdown 风格）。"""
    # TODO 6
    failure_description = ""
    for failure in metrics.get("failure_cases"):
        failure_description += f"测试问题：{failure.get("question")},答案:{failure.get("answer")}\n"
    ans_str = f"评测的agent对象名称为：{agent_name},本次测试共{metrics.get("total")}个用例，其中通过rule_check的有{metrics.get("rule_pass")}个，rule_check的通过率为{metrics.get("rule_rate"):.2%}，平均分为{metrics.get("avg_score"):.2f}，共评测失败{metrics.get("failures")}次。"
    if failure_description:
        ans_str += f"评测失败的问答分别为：{failure_description}"
    return ans_str


# ---------- 入口 ----------

def main() -> None:
    """跑好/坏两个示例 Agent 的对比评测并打印报告；--json 输出原始指标。"""
    # TODO 7
    client = OpenAI(api_key=load_api_key(),base_url=BASE_URL)
    parser = argparse.ArgumentParser(description="agent评测工具")
    parser.add_argument("--json",action="store_true",help="查看原始json字符串")
    args = parser.parse_args()
    if args.json:
        report_good = json.dumps(run_eval_suite(sample_agent_good,GOLDEN_SET,True,client))
        report_bad = json.dumps(run_eval_suite(sample_agent_bad,GOLDEN_SET,True,client))
    else:
        report_good = report(run_eval_suite(sample_agent_good,GOLDEN_SET,True,client),"deepseek-chat")
        report_bad = report(run_eval_suite(sample_agent_bad,GOLDEN_SET,True,client),"not an agent")
    print(f"好agent：{report_good}\n\n坏agent:{report_bad}")



if __name__ == "__main__":
    main()
