# xAgent

核心与界面分离的**玄学命理顾问 Agent**。内核（`core/`）与界面无关：模型流式调用、工具执行、会话编排、上下文压缩、技能与 MCP 装配都在内核完成；终端界面（`tui/`）只是消费同一套事件流的前端。

* `core/` —— 与界面无关的业务内核（模型调用、工具执行、会话编排、上下文管理）
* `tui/` —— 基于 [Textual](https://textual.textualize.io/) 的终端界面
* `web/`、`desktop/` —— 预留前端，`core` 层无需改动即可接入

> 默认人设为「玄机真人」：精通八字、紫微斗数、塔罗、占星、六爻、梅花易数、奇门遁甲、风水与数字命理；文件读写、网页抓取、命令行、文档生成仅作为后台辅助能力。

---

## 1. 快速开始

```bash
cd <xAgent 源码目录>
pip install -r requirements.txt

python main.py            # 启动 TUI
python -m tui             # 等价写法
python main.py --config D:\path\to\your.ini
```

首次启动若缺少 `config.ini`，会在当前工作目录生成一份带 mock 值的模板，填入有效的 `base_url / api_key / model` 后重启。

TUI 操作：

| 操作 | 说明 |
| --- | --- |
| `Enter` | 发送输入 |
| `Ctrl+L` | 清空界面与对话上下文 |
| `Ctrl+N` | 新建会话 |
| `Ctrl+Q` | 退出 |

---

## 2. 目录结构

```
xAgent/
├── main.py                     # 统一入口（参数解析 + 启动 TUI）
├── config.ini                  # 配置（base_url / api_key / model / agent 参数）
├── requirements.txt
├── pyproject.toml
│
├── core/                       # ===== 核心层：零界面依赖 =====
│   ├── config.py               # 配置加载（config.ini + 环境变量覆盖）
│   ├── errors.py               # 统一异常：ConfigError / LLMError / ToolError
│   ├── models.py               # 领域模型：Message / ToolCall
│   ├── events.py               # 事件模型：前端唯一的数据契约
│   ├── session.py              # 对话历史管理
│   ├── session_store.py         # 会话存档与恢复
│   ├── context.py              # 上下文压缩与归档检索
│   ├── skills.py               # Skill 发现与 frontmatter 解析
│   ├── agent.py                # Agent 编排（唯一的业务主流程）
│   ├── factory.py              # 依赖装配（各前端共用）
│   ├── llm/                    # OpenAI 兼容流式客户端 + 协议 + tool_call 聚合
│   ├── tools/
│   │   ├── base.py             # Tool 抽象 + FunctionTool
│   │   ├── registry.py         # 工具注册表与统一执行/错误包装
│   │   ├── fileops/            # 文件与目录操作（含工作目录边界校验）
│   │   ├── systime/            # 本地日期时间、星期、闰年（标准库，跨平台）
│   │   ├── fetchweb/           # 网页抓取，正文抽为 Markdown
│   │   ├── search/             # 外部搜索服务 API（地址/密钥走环境变量）
│   │   ├── runcli/             # 本地命令行执行（危险命令/解释器/拼接拦截，shell=False）
│   │   ├── skills/             # 技能加载与创建落盘
│   │   ├── context/            # 归档上下文召回
│   │   └── mcp/                # MCP 桥接（异步连接、动态补注册工具）
│   └── utils/
│       └── asyncbridge.py      # 同步迭代器 → 异步迭代器
│
├── tui/                        # ===== 终端前端 =====
│   ├── app.py                  # Textual App：输入、渲染、快捷键
│   ├── widgets.py              # TUI 专用控件
│   ├── style.tcss              # 样式
│   └── __main__.py             # python -m tui
│
├── tests/                      # 单元测试 + 架构约束测试
└── docs/
    └── architecture.md         # 分层规范与架构图
```

---

## 3. 内置工具

| 工具名 | 模块 | 职责 |
| --- | --- | --- |
| `getcwd` `listDir` `getFileType` | fileops | 查看当前目录、列目录、判断文件/目录/链接类型 |
| `readFile` `createFile` `editFile` | fileops | 读取、新建、修改文件（限制在工作目录内） |
| `createDir` `deleteDir` `deleteFile` `renameMove` | fileops | 建目录、删目录（非空默认拒绝）、删文件、改名/移动（拒覆盖） |
| `getDate` `isLeapYear` | systime | 本地日期时间与星期、闰年判断 |
| `fetchWeb` | fetchweb | 抓取网页正文并转为 Markdown |
| `searchWeb` | search | 调用外部搜索 API，返回标题/链接/摘要；未配置时返回明确提示 |
| `RunCli` | runcli | 执行本地命令行并回传 stdout/stderr；破坏性命令、shell 解释器、下载执行类命令及含管道/重定向拼接的参数被拦截，可配命令白名单 |
| `loadSkill` `createSkill` | skills | 按需加载技能说明；新建技能并落盘到 `.agents/skills/` |
| `recallContext` | context | 从归档上下文中召回相关历史片段 |
| MCP 工具 | mcp | 由 `.mcp.json` 配置的外部 Server 异步接入，动态补注册 |

---

## 4. 分层规范

### 4.1 依赖方向（只能从上往下）

```
   tui/  web/  desktop/  mobile/     ← 前端层：只负责展示与输入
        │        │          │
        ▼        ▼          ▼
              core/                ← 核心层：业务、模型、工具
```

强制约束（已由 `tests/test_architecture.py` 自动校验）：

| 约束 | 说明 |
| --- | --- |
| core 不 import 前端框架 | `textual` / `rich` / `fastapi` / `tkinter` … 一律禁止 |
| 前端不直接访问网络 | TUI 里不允许出现 `requests` / `urllib3` |
| core 不直接 `print` | 对外输出一律是 `core.events` 里的事件对象 |

### 4.2 核心层内部再分层

| 层次 | 模块 | 职责 |
| --- | --- | --- |
| 数据结构层 | `models.py` `events.py` `errors.py` | 纯数据与异常，无逻辑 |
| 能力适配层 | `llm/` `tools/` | 对接外部系统（模型、文件系统、网络、MCP） |
| 业务编排层 | `session.py` `agent.py` `context.py` | 对话上下文、Agent 主循环、上下文压缩 |
| 配置装配层 | `config.py` `factory.py` | 配置读取、依赖装配 |

### 4.3 事件驱动的前端对接方式

core 只产出事件，前端各自渲染，因此新增前端不需要动 core：

```python
from core import build_agent, load_config

config = load_config()
agent = build_agent(config)

async for event in agent.arun("列出当前目录"):
    match event.kind:
        case "user_message":      ...
        case "assistant_delta":   ...   # 流式增量
        case "assistant_message": ...
        case "tool_call_started": ...
        case "tool_call_finished":...
        case "error":             ...
        case "turn_completed":    ...
```

---

## 5. 新增一个工具

工具 = 一段业务逻辑 + 一份参数 schema，放在 `core/tools/<模块>/` 下：

```python
# core/tools/<模块>/service.py
class XxxService:
    def do(self, keyword: str) -> str:
        ...

# core/tools/<模块>/toolset.py
def build_xxx_tools(service=None) -> list[Tool]:
    service = service or XxxService()
    return [
        FunctionTool(
            name="xxxTool",
            description="按关键字执行某能力",
            parameters={
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
            func=lambda keyword: service.do(keyword),
        )
    ]
```

再在 `core/factory.py` 的 `build_registry()` 里注册即可，模型立刻就能调用。

---

## 6. 配置说明

`config.ini`：

```ini
[llm]
base_url = https://api.deepseek.com/v1
api_key = sk-mock-000000000000000000000000
model = deepseek-chat
timeout = 60

[agent]
max_iterations = 8        # 单轮内最多几次"模型 → 工具"循环
workspace = .             # 工作目录
system_prompt = ...       # 系统提示词
```

各段字段与代码默认值一一对应（`core/config.py`）：

`[llm]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `base_url` | — | OpenAI 兼容接口地址 |
| `api_key` | — | 密钥，建议用 `XAGENT_API_KEY` 覆盖 |
| `model` | — | 模型名 |
| `timeout` | `60` | 单次模型请求超时（秒） |

`[agent]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `max_iterations` | `8` | 单轮内最多几次"模型 → 工具"循环 |
| `workspace` | 未设置时为当前工作目录 | 工作目录、文件工具根、技能与归档根 |
| `system_prompt` | 空 | 自定义系统提示词，留空则只用人设默认 |
| `context_window` | `128000` | 上下文窗口（token），用于压缩阈值计算；显式填写才会覆盖默认值 |

`[context]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `threshold` | `0.7` | 占用上下文窗口比例达到该值时压缩 |
| `archive_dir` | `.agents/context` | 归档目录（相对工作区） |
| `recall_limit` | `8` | `recallContext` 单次最多返回条数 |
| `recall_snippet` | `240` | `recallContext` 单条截断字符数 |

`[voice]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `model` | `small` | faster-whisper 模型规模 |
| `device` | `cpu` | 推理设备 |
| `compute_type` | `int8` | 量化精度 |
| `language` | `zh` | 识别语言 |

`[session]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `dir` | `.agents/sessions` | 会话存档目录（相对工作区） |
| `auto_save` | `true` | 退出/新建会话时自动保存 |

`[mcp]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `connect_timeout` | `30` | 连接 MCP Server 的超时（秒） |
| `call_timeout` | `120` | 单次 MCP 工具调用超时（秒） |

`[ui]`

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `stream_flush_interval` | `0.06` | 流式刷新的节流间隔（秒） |
| `agents_file` | `AGENTS.md` | 项目约定文件名，存在则首次注入 |

环境变量优先级更高，便于多环境部署与避免把密钥写进仓库：

| 变量 | 作用 |
| --- | --- |
| `XAGENT_CONFIG` | 指定配置文件路径 |
| `XAGENT_API_KEY` | 覆盖 api_key |
| `XAGENT_BASE_URL` | 覆盖 base_url |
| `XAGENT_MODEL` | 覆盖 model |
| `XAGENT_SEARCH_ENDPOINT` | 搜索服务 API 地址（`searchWeb`） |
| `XAGENT_SEARCH_API_KEY` | 搜索服务 API 密钥 |

项目约定文件（默认 `AGENTS.md`）在会话首次启动时注入系统提示，超长自动截断；文件名可在 `[ui] agents_file` 调整。

每次工具调用都会追加一行 JSON 到 `<workspace>/.agents/logs/xagent.log`：
`{"timestamp": "...", "level": "INFO", "logger": "xagent", "event": "tool_call", "tool_name": "readFile", "status": "ok", "duration_ms": 1.23, "detail": {...}}`。
`status` 取 `ok` / `tool_error` / `bad_arguments` / `type_error` / `os_error` / `exception` / `unknown_tool`，
`detail` 里的 `api_key`、`token`、`password` 等字段写盘前递归替换为 `[REDACTED]`（`core/tracing.py`）。

---

## 7. 测试

```bash
python -m pytest tests -q
```

| 文件 | 覆盖内容 |
| --- | --- |
| `tests/test_core.py` | 工具注册表、Agent 主循环 |
| `tests/test_config.py` | 配置加载与环境变量覆盖 |
| `tests/test_fileops.py` | 文件/目录操作语义、路径边界、越界阻断与 strict_root 拒绝访问 |
| `tests/test_runcli.py` | 危险命令/解释器/下载执行拦截、拼接符号拦截与白名单 |
| `tests/test_systime.py` | 本地时间与闰年判断 |
| `tests/test_search.py` | 搜索缺配置报错、响应解析与结果格式化 |
| `tests/test_skills.py` `test_skill_service.py` | 技能发现、frontmatter 解析、创建落盘与截断 |
| `tests/test_agents_md.py` | AGENTS.md 注入、一次注入与超长截断 |
| `tests/test_mcp.py` | MCP 桥接配置解析与状态 |
| `tests/test_tracing.py` | 调用追踪日志的 JSON 行结构、脱敏与失败状态 |
| `tests/test_tui.py` | Textual headless 模式下的界面渲染 |
| `tests/test_architecture.py` | 分层隔离约束（core 不依赖前端等） |

---

## 8. 配套外部组件

| 组件 | 目录 | 说明 |
| --- | --- | --- |
| AnythingLLM MCP Server | `D:\LLM\AnythingLLMMCP` | 工作区列表、文档上传入库、向量化挂载、检索问答的 MCP 桥 |
| AnythingLLM Web 页面 | `D:\LLM\AnythingLLMWebPage` | 单文件前端：工作区下拉、流式对话（非流式回退）、响应式布局、Key 仅存内存、Bearer 鉴权 |
| 技能目录 | 工作区 `.agents/skills/` | 各玄学分支 Skill，启动时按 frontmatter 自动发现 |
