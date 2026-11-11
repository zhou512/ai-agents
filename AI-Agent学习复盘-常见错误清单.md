# AI Agent 学习复盘：验收中发现的常见错误清单

> **用途**：复习专用。汇总我在每周项目验收时从你代码里发现的真实 bug：现象 → 根因 → 正确写法 → 学习点。
> **建议**：每两周通读一遍；写新项目前扫一眼"通用心法"；面试前重点看最后的"考点映射"。

---

## 〇、通用心法（跨周高频错误模式，最重要）

1. **类型混淆**：`set` 没有 `append`（用 `add`）；`dict + list` 不合法（要 `[dict] + list`）；先想清楚手里的变量是 list/dict/set/实例还是类。
2. **异常语义**：
   - 自己 `raise` 的异常会被自己的 `except` 接住 → 先想清楚异常是谁抛的、该谁接；
   - **裸 `raise` 只在 except 块内有效**，块外用会抛 `RuntimeError: No active exception to re-raise`；
   - `except Exception` 过宽会吞掉编程错误（调试时宁可让错误冒出来）；
   - 某些异常类**不能手工构造**（`JSONDecodeError` 需要 doc/pos 参数）。
3. **异步三连**：
   - 忘了 `()`：`httpx.AsyncClient` 是类，`httpx.AsyncClient()` 才是实例；
   - 忘了 `await`：`asyncio.gather()` 返回 Future 不是结果——用 `type()` 检查变量；
   - 连接池不共享：AsyncClient 的生命周期应匹配"一批请求"，不是"单个请求"。
4. **括号与拼写**：行尾多一个 `.`；API 参数名拼错（`temperatuure_2m_max`）——报错先查拼写和括号。
5. **哨兵值 vs 异常**：重试耗尽后应该 `raise` 真实异常，而不是返回 `("0", 0, 0)` 假装成功。
6. **计时用 `time.perf_counter()`**，且**同一段计时只用同一个时钟**（混用 time.time 会得到 -17.8 亿秒）。
7. **PEP8 与整洁**：关键字参数 `=` 两侧不加空格；逗号后加空格；不遮蔽内置函数（`format`→`output_format`）；删未用 import。
8. **安全**：API Key 必须进 `.gitignore`（`.env`/`.venv/`）；对用户输入保持提示注入意识。
9. **文档与实现一致**：docstring 承诺"返回 (None, 错误)"就别抛异常；说"会 raise"就别打印后返回 None。
10. **修改的连锁反应**：修 A 可能破坏 B——每改完一处，把相关失败路径重新跑一遍（本周最生动的案例）。
11. **调试 print 用完删掉**：调试完的 `print` 会污染 Agent 的工具输出（safe_calculate 里留了 4 行 debug print，每次计算都刷屏）。
12. **字典查找用 `.get()`**：`registry[name]` 在 `if not f` 判空**之前**就抛 KeyError——"先取后判"顺序错了，未知 key 该用 `registry.get(name)`。
13. **工具执行层必须容错**：Agent 调用工具时，任何工具异常（网络、恶意输入、坏 JSON）都要转成错误字符串**回填给模型**，而不是让程序崩溃或退出会话。
14. **报错信息要准确**：达到循环上限时该说"达到最大轮数（5）"，而不是"已重试4次"——`for` 循环结束后循环变量是 `MAX-1`，别拿它数次数。
15. **"碰巧正确"比"直接报错"更危险**：逻辑依赖巧合兜底（如"先 add 再 search 命中自己 → continue"），条件一变就爆，而且毫无规律可查。写完问自己："我是不是靠运气才不出错的？"
16. **重构时检查语句归属**：改结构时 `return`/`save` 等语句容易被带进循环或错误层级（`return count` 进了 for 循环 → 只处理第一条就返回，静默丢数据）。改完务必用**多条数据**用例验证——单条测试发现不了循环类 bug。
17. **输出职责单一**：一个内容只从一处打印。函数要么"返回结果给调用方打印"，要么"自己打印完不再重复返回"——别混着来（第 6 周"打印重复"教训的另一形态：`retrieve_and_answer` 打印了答案，`main` 又打一遍）。
18. **防幻觉的第一道防线是数据边界，不是提示词**：空输入必须**短路**（条件边走提示节点/直接结束），绝不把空数据喂给模型——大模型在输入缺失时会"体面地编造"（论文、数据、结论，编得条理清晰毫不心虚）。提示词里的"禁止编造"只是纵深防御，不是主防线。

---

## 一、第一周：organizer.py（文件整理工具）

### Bug 1：`set()` 调 `.append()` → 必然崩溃
- **现象**：`AttributeError: 'set' object has no attribute 'append'`
- **根因**：`used_name[target_dir] = set()` 创建集合，却用 `append` 添加元素
- **正确写法**：集合用 `.add()`；注解写 `dict[Path, set[str]]`
- **学习点**：set（去重/无序）与 list（有序/可重复）的方法不通用

### Bug 2：重名冲突只检查一次
- **现象**：`report(1).txt` 本身已被占用时仍会选中它 → 覆盖或报错
- **根因**：`if` 只判断一次，没有继续找空名字
- **正确写法**：
  ```python
  num = 1
  while new_name in used_names[target_dir]:
      new_name = f"{stem}({num}){suffix}"
      num += 1
  ```

### 风格项
- `import datetime` 写在文件中间 → 移到顶部
- `if dry_run == False` → `if not dry_run`
- 类型注解与实际使用类型不一致（`list[str]` vs `set()`）

---

## 二、第二周：exercises.py + weather_cli.py（网络请求与异步）

### 2.1 练习文件

**Bug 1：计时混用两个时钟**
- **现象**：耗时返回 `-1787965854` 秒（荒谬值）
- **根因**：`t0 = time.time()` 但结束用 `time.perf_counter()`——两个时钟起点不同，相减是起点差
- **正确写法**：两头都用 `time.perf_counter()`
- **学习点**：同一段计时必须用同一个时钟；计时一律用 perf_counter

**Bug 2：`except ValueError` 捕不到 KeyError/IndexError**
- **现象**：城市不存在时 `data["results"][0]` 抛 IndexError，程序崩溃
- **根因**：IndexError/KeyError ≠ ValueError，`except ValueError` 接不住；且没做判空
- **正确写法**：
  ```python
  results = data.get("results", [])
  if not results:
      raise ValueError(f"未找到城市: {city}")
  ```

**Bug 3：raise 后立刻被自己的 except 接住**
- **现象**：`geocode("火星xzz")` 打印后返回 None，而不是抛异常
- **根因**：`raise ValueError(...)` 被同函数 `except ValueError: print(...)` 吞掉
- **学习点**：自己抛的自己接 = 把错误信息藏起来；要么不 try，要么 except 里 `raise`

**Bug 4：API 参数拼写错误**
- **现象**：`daily="temperatuure_2m_max,..."`（多一个 u）→ API 忽略该参数 → pydantic 校验失败
- **学习点**：报错先查拼写；pydantic 模型恰好是抓这种错的工具

### 2.2 weather_cli 项目

**Bug 5：argparse 位置参数 vs 可选参数**
- **现象**：`python weather_cli.py 北京` 报 `required: days`；`北京 上海` 报 `invalid int value: '上海'`
- **根因**：`parser.add_argument("days", ...)` 少了 `--`，days 变成了必填位置参数
- **正确写法**：`parser.add_argument("--days", type=int, default=1, ...)`

**Bug 6：`async with httpx.AsyncClient` 少了括号**
- **现象**：`'type' object does not support the asynchronous context manager protocol`
- **根因**：类对象 ≠ 实例；类没有 `__aenter__`
- **学习点**：`ClassName` 是类，`ClassName()` 才是实例

**Bug 7：`return asyncio.gather(*tasks)` 少了 await**
- **现象**：`fetch_many` 返回 `<class 'asyncio.tasks._GatheringFuture'>`，for 循环出错
- **正确写法**：`return await asyncio.gather(*tasks)`
- **学习点**：async 函数里想"拿到结果"必须 `await`；用 `type()` 检查返回值是 Future 还是结果

**Bug 8：`except Exception` 过宽**
- **现象**：`AsyncClient` 少了括号这种编程错误，被包装成"查询失败: ..."——根本看不出真实原因
- **学习点**：开发阶段让错误冒出来；只捕获已知异常（httpx.HTTPError 等）

**Bug 9：每个城市新建一个 AsyncClient**
- **根因**：连接池未共享，`fetch_one` 内各自 `async with AsyncClient()`
- **正确写法**：`fetch_many` 建一个 client 传给所有任务

**Bug 10：判空对象不对**
- `if not data:` 检查整个响应，实际应该 `if not results:` 检查结果列表

---

## 三、第三周：chat_cli.py（LLM 对话 CLI）

**Bug 1：REPL 中途 API 错误直接崩溃**
- **根因**：`chat_stream` 无错误处理，`run_repl` 未捕获 OpenAIError
- **正确写法**：run_repl 里 try/except OpenAIError，打印友好错误 + 弹出失败消息 + continue

**Bug 2：`/temp` 用 `in` 判断**
- **现象**：输入"什么是/temp命令"也会触发温度调整
- **正确写法**：`user_msg.startswith("/temp")`

**Bug 3：历史无限增长**
- **根因**：messages 只增不减 → 超上下文窗口
- **正确写法**：加 `MAX_COUNT`，超了丢最旧对话（保留 system）

**Bug 4：`messages[0] + messages[...]` 类型错误**
- **现象**：`TypeError: unsupported operand type(s) for +: 'dict' and 'list'`（对话超过 20 条时触发）
- **根因**：`messages[0]` 是 dict，切片是 list，dict + list 不合法
- **正确写法**：`[messages[0]] + messages[-(max_count - 1):]`

**Bug 5：重试耗尽返回哨兵值 `("0", 0, 0)`**
- **根因**：假装成功，把 "0" 存进历史；上层 `except OpenAIError` 成了死代码
- **正确写法**：重试耗尽后 `raise` 最后一个异常

**Bug 6：401 也重试（白等 7 秒）**
- **学习点**：只重试瞬时错误（429/5xx/超时）；认证错误（401/400）直接放弃：
  ```python
  except AuthenticationError:
      raise
  ```

**Bug 7：except 块外裸 `raise` → RuntimeError**
- **现象**：`RuntimeError: No active exception to re-raise`
- **正确写法**（last_error 模式）：
  ```python
  last_error = None
  for attempt in range(3):
      try:
          ...
          return result
      except SomeError as e:
          last_error = e
          ...
          time.sleep(wait)
  raise last_error
  ```

---

## 四、第四周：resume_extractor.py（简历抽取，JSON mode + pydantic + 重试）

**Bug 1：行尾多余 `.` → 整个文件无法运行**
- **现象**：`data = extract_json(client, build_messages(text)).` → `SyntaxError: invalid syntax`
- **学习点**：改完代码先 `python -m py_compile 文件`，语法错误会让整个文件都跑不了

**Bug 2：手工构造 `JSONDecodeError("文本")` → TypeError**
- **现象**：`TypeError: JSONDecodeError.__init__() missing 2 required positional arguments: 'doc' and 'pos'`
- **根因**：JSONDecodeError 是 ValueError 的特殊子类，构造签名是 `(msg, doc, pos)`
- **正确写法**：不要捕获后重新包装，让原始异常传播，或在 except 里裸 `raise`
- **学习点**：不是所有异常都能 `SomeError("自定义消息")` 手工构造

**Bug 3：`ValidationError("字符串")` 手工构造 → TypeError**
- **现象**：`ValidationError.__new__() missing 1 required positional argument: 'line_errors'`
- **正确写法**：pydantic 校验失败返回错误信息字符串，不重新构造异常

**Bug 4：`load_api_key` 缺 key 时返回 None**
- **现象**：`api_key=None` → OpenAI 构造抛异常 → traceback；main 里的 except 是死代码
- **正确写法**：`if not key: raise ValueError("未找到 API Key...")`，main 里 `except ValueError` 友好提示

**Bug 5：few-shot 示例是无效 JSON**
- **现象**：`"skills": [ue5引擎使用,游戏制作]` 数组元素没加引号
- **学习点**：给模型的示例本身必须是合法的，模型会模仿示例格式

**Bug 6：`--format json` 输出的是 Python dict repr**
- **现象**：`print(f"{data}")` 输出单引号、None，不是合法 JSON
- **正确写法**：`json.dumps(data, ensure_ascii=False, indent=2)` 或 pydantic 的 `model_dump_json()`

**Bug 7：`format` 遮蔽内置函数**
- **正确写法**：`output_format`

**Bug 8（本周新发现）：修复产生的连锁反应**
- 现象 1：模型输出非 JSON 时，`except` 里引用未赋值的 `data` → NameError
- 现象 2：`validate_resume` 改成返回 `(None, error)` 后，`extract_resume` 没有显式处理"返回错误"路径 → 反馈消息不再追加，`last_error` 是 None → 最终 raise 一个没意义的错误
- **根因**：把"抛异常"改成"返回错误"后，调用方仍按旧逻辑写
- **正确写法**（返回/异常二选一，并显式处理两种路径）：
  ```python
  def extract_resume(client, text) -> Resume:
      messages = build_messages(text)
      last_error: Exception | None = None
      for attempt in range(MAX_RETRIES):
          try:
              data = extract_json(client, messages)      # 解析/API 失败：异常路径
          except (JSONDecodeError, OpenAIError) as e:
              last_error = e
              messages.append({"role": "assistant", "content": "（模型未输出合法 JSON）"})
              messages.append({"role": "user", "content": f"输出不是合法 JSON：{e}，请修正后重新输出"})
              continue
          resume, error = validate_resume(data)          # 校验失败：返回值路径
          if not error:
              return resume
          last_error = ValueError(error)
          messages.append({"role": "assistant", "content": json.dumps(data, ensure_ascii=False)})
          messages.append({"role": "user", "content": f"上述 JSON 校验失败：{error}，请修正后重新输出合法 JSON"})
      raise RuntimeError(f"抽取失败（{MAX_RETRIES} 次尝试后）：{last_error}")
  ```

---

## 五、第五周：tool_agent.py（Function Calling Agent）

**做对的部分**：Agent 循环结构标准（assistant 消息 → tool 消息带 tool_call_id → 循环）；`run_agent` 接收 messages 支持多轮历史；`/clear` 保留 system；`get_time` 参数改名 `timezone` 且窄捕获 `ZoneInfoNotFoundError`；tzdata 环境问题定位正确。

### Bug 1：调试 print 留在生产代码（safe_calculate）
- **现象**：`safe_calculate("(2+3)*4")` 打印 4 行调试信息（表达式、node.op、OPS keys、in 判断），结果 20 正确但输出被污染（实测）
- **根因**：调试时加的 `if isinstance(node, ast.BinOp): print(...)` 没删
- **正确写法**：删除调试块
- **学习点**：调试完必须删 print——尤其工具结果会进 Agent 对话/日志的路径，污染非常严重

### Bug 2：`registry[name]` 在判空前就抛 KeyError
- **现象**：`execute_tool(registry, "不存在的工具", "{}")` → `KeyError: '不存在的工具'` 崩溃（实测）
- **根因**：`f = registry[name]` 先取值（KeyError），`if not f` 判空永远执行不到——死代码
- **正确写法**：`f = registry.get(name); if not f: return f"未知工具: {name}"`
- **学习点**：先取后判要配套——`.get()` 才是"取不到返回默认值"的语义

### Bug 3：工具执行层没有容错（agent_turn）
- **现象**：工具抛异常（网络断、恶意表达式、坏 JSON）→ 冒泡到 main → 整个 REPL 退出
- **根因**：agent_turn 里 `execute_tool(...)` 没有 try/except——README 原则"工具出错作为结果回填"没实现
- **正确写法**：
  ```python
  try:
      result = execute_tool(REGISTRY, name, args)
  except Exception as e:
      result = f"工具执行失败: {e}"     # 错误也作为 tool 结果回填，模型自己处理
  ```
- **学习点**：Agent 的工具层 = 外部世界边界，任何失败都不能让它炸掉整个会话

### Bug 4：main 的 except 分支用 return 退出整个 REPL
- **现象**：一次"达到最大工具调用轮数"或临时错误 → 会话直接结束
- **正确写法**：`continue` 而不是 `return`（单轮失败不该终结整个会话）

### Bug 5：循环上限的报错信息误导
- **现象**：`raise RuntimeError(f"请求失败，已重试{turn}次")`——实际是"达到最大轮数"；`turn` 循环后是 MAX-1（5 轮显示"已重试4次"）
- **正确写法**：`raise RuntimeError(f"达到最大工具调用轮数（{MAX_TURNS}），未能生成最终回答")`

### Bug 6：API Key 缺失无友好提示（第三次出现）
- **现象**：`OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), ...)` 缺 key 时构造抛异常 → traceback
- **正确写法**：`load_api_key()` 判空 raise ValueError + main 捕获（第三、四周已写过两次，不该再犯）

### Bug 7：项目通过 sys.path hack 耦合练习代码
- **现象**：`sys.path.append(project_root)` + `from exercises import ...`——练习文件里的 bug（debug print、KeyError）直接传染给项目
- **建议**：工具实现放 tool_agent.py 内部（骨架本来的设计），或抽到独立 tools.py 正常导入
- **学习点**：项目代码不要依赖"练习文件恰好还在"；练习是一次性的，项目是可运行的交付物

### 小问题
- `WEATHER_CODES[fc.current.weather_code]` 可能 KeyError → 用 `.get(code, "未知")`
- `execute_tool` 里 print 副作用（分发函数应只 return，打印交给调用方）
- `get_time` 错误信息不带真实异常（调试时看不到是"缺数据库"还是"名字错"）

---

## 六、第六周：exercises.py（手写 ReAct）

### Bug 1：正则 re.DOTALL 让 thought 吞掉后续所有行（最隐蔽）
- **现象**：打印时 Action/Action Input 和 Final Answer 出现两遍（用 mock 客户端离线复现，与真实运行完全一致）
- **根因**：`re.search(r"Thought:\s*(.+)", text, re.DOTALL)` —— DOTALL 让 `.` 匹配换行，`(.+)` 贪婪抓到文本末尾，`thought` 字段里装进了后续的 Action/Action Input/Final Answer 行；打印 `Thought: {thought}` 时把内嵌行一起打出，随后单独打印各字段又打一遍 → 内容重复
- **正确写法**：Thought 正则去掉 `re.DOTALL`（只匹配第一行）；Final Answer 保留 DOTALL（答案可能多行）
- **学习点**：正则的 DOTALL/贪婪是隐藏雷区。调试"输出重复/错位"时，先 `print(repr(result))` 看字段里到底装了什么，别盯着打印结果猜

### Bug 2：模型输出被追加两次（assistant + user 各一次）
- **现象**：`messages.append({"role": "assistant", "content": text})` 后又 `messages.append({"role": "user", "content": text})`——同一段文本以两种角色进历史
- **正确写法**：只保留 assistant 那一次
- **学习点**：messages 历史里每条内容只能有一个正确的角色归属；重复会让模型看到"自己的话被用户说了一遍"

### 小问题
- 工具异常只捕 `(TypeError, SyntaxError)`，ValueError 等仍会崩（safe_calculate 拒绝恶意表达式时抛的就是 ValueError）→ 用 `except Exception`
- few-shot 示例与工具列表不一致（示例里出现 get_weather，工具列表没有它）——示例必须是"真实存在的流程"

### ⚠️ 教训复发案例：`.get()` 第二次栽跟头（mini_agent 项目）
- **现象**：循环 5 次输出 `Observation:工具执行出错：'thought'`（KeyError），模型永远无法恢复
- **根因**：① 打印时又用了 `result["thought"]` 直接索引——模型输出漏掉 Thought 行时抛 KeyError（通用心法 #12 复发）；② `try` 块包住了**打印语句**，KeyError 被 `except Exception` 当成"工具执行出错"回填给模型——模型收到无意义的 Observation，只能继续乱输出
- **正确写法**：字段一律 `.get()`；**try 只包 `execute_tool`**，打印放外面；解析层先 `text.replace("：", ":")` 兼容全角冒号
- **学习点**：模型输出不稳定是常态（缺字段、全角标点），解析/执行层必须防御式编程；**喂给模型的 Observation 必须是真实有用的信息**——垃圾进垃圾出，模型无法从无意义错误里恢复

### ⚠️ 二次复发：同一个 bug 模式出现多处，修漏了一处
- **现象**：修好 Action 分支的 `result["thought"]` 后，`Final Answer` 分支的同款直接索引又触发 KeyError（同一文件 3 处同类代码）
- **正确做法**：修 bug 前先 **grep 找出所有同类模式**（`grep -n 'result\["' 文件`），一次改完，别只修"报错的那一处"
- **学习点**：同一个错误模式往往复制粘贴了多处——改一处、验一处，不如"搜全部、改全部、再统一验证"

---

## 七、第七周：memory_chat.py（长期记忆）

### Bug 1：去重逻辑"碰巧正确"（空库分支没有 else）
- **现象**：`if not store.items: add` 之后没有 `else`/`continue`，空库时 add 完继续掉进查重逻辑
- **根因**：正确性依赖巧合——"search 命中刚存的自己 → 相似度 1.0 > 阈值 → continue 防重复"
- **学习点**：碰巧正确比直接报错更危险（通用心法 #15）——代码意图和实际流程不一致，条件一变就炸

### Bug 2：修复时 `return` 跑进 for 循环（静默丢数据）
- **现象**：重构空库分支时把 `store.save()` 和 `return count` 挪进 for 循环内 → **只处理第一条事实就返回**，其余静默丢失
- **学习点**：改结构时检查语句归属（通用心法 #16）；用"多条事实"用例验证（单条测不出）

### Bug 3：main 未捕获 extract_facts 的 RuntimeError
- **现象**：模型连续两次输出坏 JSON → 重试耗尽抛 RuntimeError → REPL 直接崩
- **正确写法**：REPL 里每个可能失败的环节都 try/except，失败只跳过本轮

### 认知：手写 n-gram 向量相似度只有 0.19
- "小明多大" vs "用户叫小明，25 岁" 相似度 0.19——但**排序仍然正确**（相关的那条排第一）
- 教学意义：粗糙但原理正确；生产必须换 embedding API

---

## 八、第八周：doc_qa.py（RAG）

### Bug 1：输出职责不分离（同一内容打印两遍）
- **现象**：`retrieve_and_answer` 里一段大 print 把"全部片段原文 + 问题的答案是 + 答案"挤在一行，`main()` 又把答案 print 一遍；`evaluate` 内部打印 rate，`/eval` 分支又打印一次
- **修复**：依据片段用"分行 + 编号 + 来源 + 50 字截断"展示；答案只由 main 打印；rate 只由 main 打印
- **学习点**：每个内容只从一个地方输出（通用心法 #17）；函数要么返回、要么打印，职责选一个

### 小问题
- 文档问答 temperature 用 0.7 太高（不稳定）→ 0.3
- `make_synthesis_prompt` 的示例格式与实际片段格式不一致（示例是"【片段5：...】 | 来源：..."，实际是"【片段N | 来源:xxx】\n文本"）——示例必须和真实格式一致

### 认知：hit rate 1.00 的假象
- 手写向量对"关键词直接重合"的问题全命中——但处理不了同义改写（"怎么给函数加日志"检索不到"装饰器"）
- 评估数字好看 ≠ 系统真的好；要知道自己的方法在什么场景会失效

---

## 九、第九周：langgraph_agent.py（LangGraph + 裸 openai SDK）

### Bug 1：add_messages 与裸 openai SDK 的类型冲突（最典型）
- **现象**：`400: messages[0]: missing field role`
- **根因**：装 langgraph 会**自动带上 langchain-core**；`Annotated[list, add_messages]` 收到 dict 消息时会把它**转换包装成 langchain Message 对象**（HumanMessage/AIMessage...），于是 `state["messages"]` 里存的不是纯 dict；把这些 langchain 对象直接喂给**裸 openai SDK** → 序列化时找不到 `role` 字段
- **修复（路线 A：全 dict）**：`messages: list` 用普通字段（无 reducer），node 手动返回 `state["messages"] + [新消息]`；assistant 消息手工构造 wire 格式 dict
- **学习点**：框架的类型系统约束——LangGraph 里处理消息**要么全 dict（路线 A），要么全 langchain（路线 B：ChatOpenAI + ToolNode）**，混用必踩坑；先想清楚"消息现在是什么类型的对象"

### Bug 2：content 字段类型要求（第二轮才炸）
- **现象**：修复 Bug 1 后报 `400: messages[3]: content should be a string or a list`
- **根因**：① 模型调工具时 `content` 是 None，却发送了 `"content": None`（DeepSeek 严格要求 content 是 string/list，不接受 None）→ 修复：**content 为空时省略整个字段**；② 工具结果没转字符串（safe_calculate 返回 float 20）→ 修复：`str(result)`
- **学习点**：① 不同服务商严格程度不同（OpenAI 容忍 `content: null`，DeepSeek 不接受）——换 API 报"反序列化失败"先想"它比原来的更严格在哪"；② docstring 写了 `str(结果)` 实现却漏了——**提示与实现脱节**是自查第一排查点

### 通用观察
- LangGraph 的价值在于"把循环变成图"（条件边回指自己）；这周的坑全是**类型边界**问题，不是图概念问题——说明你的 dict 心智模型本身是好的，问题出在框架插进来一层转换

---

## 十、第十周：report_workshop.py（多 Agent + LangGraph）

### Bug 1：图里漏了一条边——节点"没连上"导致根本不执行（最隐蔽）
- **现象**：整图跑完报 `KeyError: 'verdict'`（读不到评审结果）；用户误以为是 review_node 的代码问题
- **根因**：`build_graph()` 里加了 `review` 的条件边，但**漏了 `write → review` 的普通边**——review 节点从未被连进图，图跑到 write 就结束了（write 没有出口边）；`compile()` 对不可达节点**静默不报错**
- **修复**：`wss.add_edge("write", "review")` 一行
- **学习点**：① LangGraph 的 `compile()` 不校验节点连通性——**必须跑全图 mock 测试**（整图 invoke，不要只测单个节点）；② 报错位置 ≠ 问题位置——"读不到某字段"往往说明**产出该字段的节点压根没运行**，先顺着图查"这个节点到底有没有被执行到"（看它的 print 有没有出现）

### 小问题
- review 的 JSON 解析依赖模型输出纯 JSON；真实模型可能用 markdown 围栏包裹 → json.loads 失败靠重试兜底（能用，但建议 response_format=json_object 或先剥围栏）
- `review_node` 里轮次计数放在 review 而非 write（与 docstring 提示不符，但逻辑自洽能跑）——文档与实现不一致的老问题

---

## 十一、第十一周：arxiv_research_agent.py（大作业：真实 API + 多 Agent + 双状态模式）

### Bug 1（最重要的教训）：空数据喂给模型 → 模型"体面地编造"
- **现象**：输入中文主题"多agent系统"（arXiv 不收录中文）→ 搜索 0 篇 → **研究员自行"选了该领域经典论文"来提炼**（幻觉！日志原话："我将基于该领域的经典和前沿研究"）
- **根因**：search 返回空列表后**流程没有短路**，research_node 照常被调用——模型收到空输入，在缺失处体面地编造
- **修复（三层防线）**：① 图层面：search 后加条件边（有论文 → research；无 → `empty` 节点 → END），**空数据永远不进模型**；② prompt 层面：研究员提示词加铁律"列表为空必须回复未搜到，禁止编造"；③ UX 层面：main 检测无 draft → 提示换英文关键词，不进问答阶段
- **学习点**：防幻觉第一道防线是**数据边界**（通用心法 #18）。"arXiv 查不到"是数据问题，不是让模型"尽力而为"的理由
- **面试话术**："防幻觉的第一道防线是数据边界，不是提示词"

### Bug 2：惰性创建的 getter 没被调用（chat_llm 永远 None）
- **现象**：定义了 `get_chat_llm()` 但 `chat_node` 直接用全局 `chat_llm`（初始化 None 后从没被赋值）→ `None.invoke()` AttributeError，问答阶段必崩
- **学习点**：惰性创建模式（`get_x()` 缓存全局）要求**所有使用点都走 getter**——grep 一下"有没有人绕过 getter 直接用全局变量"（第九周 client 模块级的同类问题，换个形态又出现）

### Bug 3：问答阶段没上下文 + 跨 invoke 不传 state（add_messages 白用）
- **现象**：问答图每次 `invoke` 只带一条新 user 消息——① 没有 papers/报告上下文注入，模型无法讨论论文；② 上一轮的 state 没传回，历史不累积
- **修复**：main 维护 `chat_state`（首轮注入 system 上下文含论文列表），每轮追加 user 消息后把**上一轮 result 传回**给 invoke
- **学习点**：reducer 只在"状态被传递"时才累积——**没有 checkpointer 时，跨 invoke 的历史由调用方持有**；设计阶段先问"这个模型需要什么上下文"

### 小问题
- 链接链条：研究员 prompt 输出格式最初没要求保留 URL → 写手没链接可用（职责链上每个 Agent 的输出都要满足下游的输入需求）

### Bug 4：LLM 查询改写的单引号陷阱（arXiv 语法）——实测数字：2 篇 vs 64,814 篇
- **现象**：方案 B（LLM 改写 arXiv 查询）的 system prompt 示例里用了**单引号** `(abs:'operating system')`，模型照抄 → 搜索返回 64,814 篇松散匹配（等于没改写）
- **根因**：arXiv 的短语搜索**只认双引号**——单引号会被拆成语义词各自匹配，回到最原始的噪音问题
- **实测对比**：`all:"AI OS"` → 2 篇（真相关）；`all:'AI OS'` → 64,814 篇；带字段前缀的双引号组合查询 → 325 篇聚焦
- **修复（三层防线）**：① prompt 明确"短语必须双引号（单引号无效）"并给正确示例；② 代码层 `clean_query()`：去代码围栏 + **单引号批量转双引号**（防御模型手滑）；③ 回退策略：改写查询 0 结果 → 回退 `all:"{原始主题}"` 短语搜索 → 仍空才走 empty 节点
- **学习点**：① **LLM 会照着示例抄**——示例写错 = 全线输出错（prompt 的示例是事实标准）；② 外部 API 的语法坑（引号、转义、字段前缀）要实测验证，别靠猜——一个查询从"能跑"到"跑得对"差着 3 万倍结果；③ 数据层缺陷用 LLM 补（查询改写是语言任务），但 LLM 不可靠 → 代码层清洗+回退兜底，**prompt 给方向，代码守底线**

---

## 十二、面试考点映射（这些 bug 背后的知识点）

| 你踩过的坑 | 对应面试题 |
|---|---|
| argparse 缺 `--` | "位置参数和可选参数的区别？" |
| gather 缺 await、Future 当结果 | "async/await 的原理？怎么排查没 await？" |
| 类 vs 实例（AsyncClient） | "Python 里 class 和 instance 的区别？" |
| set/list/dict 方法混淆 | "list、set、dict 各自的特点和适用场景？" |
| 裸 raise / last_error 模式 | "Python 异常处理的正确姿势？" |
| 什么错误该重试 | "设计一个带重试的 API 调用，怎么决定重试策略？" |
| JSON mode + pydantic + 重试 | "如何保证 LLM 输出可靠的结构化数据？" |
| 提示注入实验 | "LLM 应用的安全风险有哪些？如何防护？" |
| API Key 泄漏风险 | "部署 LLM 应用时密钥如何管理？" |
| 哨兵值 vs 异常 | "函数失败时应该返回特殊值还是抛异常？" |

---

## 十三、Debug 自查清单（每次报错按顺序查）

1. 语法：`python -m py_compile 文件`（一行多字符、缺括号、行尾点）
2. 拼写：API 参数名、变量名、函数名
3. 类型：`type(x)` 打印——是类还是实例？是 Future 还是结果？是 dict 还是 list？
4. 异常：这个异常是谁抛的？我的 except 能接住它吗？except 里会不会又抛新的？
5. 返回值：函数说好的返回约定（raise 还是 return None）实现一致吗？调用方处理了吗？
6. 改了哪里：这次修改动了哪些路径？把相关的失败路径重新跑一遍
