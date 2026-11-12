# mating1 — MCP 与 AnythingLLM 实践项目集

围绕 [MCP](https://modelcontextprotocol.io)（Model Context Protocol）与 [AnythingLLM](https://anythingllm.io) 的课程实践仓库，包含一个定制 Agent 内核、两套 MCP 服务、一个浏览器端工具，以及一套可直接运行的终端工作区。

本 README 只描述**仓库里真实存在的代码**；每个模块的细节、接口契约与验证方式见各自目录下的 README。

---

## 1. 仓库里有什么

| 目录 | 对应考核项 | 说明 | 技术栈 |
| --- | --- | --- | --- |
| `Agent/xAgent/` | D 定制 Agent | 与界面解耦的 Agent 内核 + Textual 终端界面。工具调用主循环、文件/时间/网页/搜索工具、技能创建与加载、MCP **客户端**、`AGENTS.md` 注入、会话存档、上下文压缩 | Python 3.11+ · requests · textual · mcp · trafilatura |
| `PetHospitalMCP/pet-hospital-mcp/` | A 宠物医院 MCP | 把既有 Go 宠物医院 REST API 无侵入包装成 MCP **服务端**（单工具 `list_pets`），不改动 Go 后端 | Python 3.11+ · `mcp==2.0.0` · pydantic · httpx |
| `AnythingLLMMCP/` | B AnythingLLM MCP | 把 AnythingLLM 的工作区、文档列表、本地文档上传、向量化挂载、检索问答封装成 MCP **服务端**（5 个工具）；另含 `mock_backend.py` 本地契约桩，供无实例时联调 | Python 3.9+ · 仅标准库（零第三方依赖） |
| `AnythingLLMWebPage/` | C AnythingLLM Webpage | 单文件网页：选工作区、流式对话（非流式回退）、响应式布局、Bearer 鉴权、Key 仅存内存 | 原生 HTML / JavaScript |
| `office/` | 运行环境样例 | xAgent 的完整工作区：`config.ini`、`.mcp.json`（7 个 MCP Server）、`AGENTS.md`、`.agents/skills/`（19 个技能目录）、一键启动脚本、交付说明 | — |
| `Agent/Practice02/` | 早期练习 | 单文件版工具调用与工具定义示例（`chat-tool-*.py`）与架构图，非主线实现 | Python |
| `PetHospitalMCP/windows/` | A 的上游后端 | Go 宠物医院 REST API 的 Windows 发行包（`pethospital.exe` + `data/pet.db` + 说明），是本项目 A 模块的前置服务 | Go 标准库 |
| `guizang-ppt-skill/` | 第三方引用 | 归藏 PPT 技能包（MIT），仅作 Skill 目录格式样例，**未做任何改造**，非本项目成果 | — |

---

## 2. 模块关系

```text
                    ┌──────────────────────────────┐
                    │        AnythingLLM 实例       │
                    │  workspace / 文档 / 向量库     │
                    └───────▲───────────────▲──────┘
              HTTP /api/v1/ │               │ HTTP /api/v1/
                            │               │
              ┌─────────────┴─────┐   ┌─────┴──────────────────┐
              │ AnythingLLMWebPage│   │ AnythingLLMMCP         │
              │ 浏览器直连对话     │   │ 5 个 MCP 工具（:8765）  │
              └───────────────────┘   └─────▲──────────────────┘
                                            │ MCP Streamable HTTP
                                            │
   ┌──────────────────────────┐   MCP   ┌───┴──────────────────┐
   │ PetHospitalMCP（:8000）   │◀───────▶│ Agent/xAgent（TUI）   │
   └─────▲────────────────────┘  client └──────────────────────┘
         │ HTTP /api/v1/pets
   ┌─────┴────────────────────┐
   │ Go 宠物医院 REST API(:8080)│
   └──────────────────────────┘
```

- A 与 B/C 互相独立：A 是把 REST 后端包成 MCP 服务端；C 是浏览器直连 AnythingLLM；B 是把 AnythingLLM 包成 MCP 服务端。
- xAgent 在 `office/.mcp.json` 里同时接入上述两个 HTTP MCP 与若干 stdio MCP（八字/命理/起名/择日），是这些服务的**统一客户端**。

---

## 3. 环境依赖一览

| 模块 | 运行时 | 关键依赖 | 外部服务 |
| --- | --- | --- | --- |
| `Agent/xAgent` | Python 3.11+ | `requirements.txt`：requests / textual / trafilatura / mcp / anyio（语音可选 faster-whisper、pyaudio、numpy） | 任一 OpenAI 兼容模型接口（默认 DeepSeek）；可选 AnythingLLM、各 stdio MCP |
| `PetHospitalMCP/pet-hospital-mcp` | Python 3.11+ | `pyproject.toml`：`mcp==2.0.0`、httpx、pydantic；开发态 pytest、pytest-asyncio | Go 宠物医院 API（默认 `http://127.0.0.1:8080`） |
| `AnythingLLMMCP` | Python 3.9+ | 无第三方依赖 | AnythingLLM（默认 `http://localhost:3001`） |
| `AnythingLLMWebPage` | 任意现代浏览器 | 无构建步骤 | 同上 |
| `PetHospitalMCP/windows` | Windows x64 | 无（单文件可执行） | 自带 `data/pet.db` |

---

## 4. 分步启动

四个模块互相独立，按需启动。以下命令均在各自目录下执行。

### 4.1 A · 宠物医院（先起 Go 后端，再起 MCP 服务）

```powershell
# 1) Go 后端（发行包，默认 127.0.0.1:8080）
cd PetHospitalMCP\windows
.\pethospital.exe

# 2) MCP 服务
cd PetHospitalMCP\pet-hospital-mcp
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m pet_hospital_mcp        # 默认 127.0.0.1:8000
```

`PetHospitalMCP\windows\` 内的 `pethospital.exe` 与 `data\pet.db` 是上游 Go 项目的发行包与示例数据，按 `.gitignore` 不入库，随课程资料/本机放置；缺这个后端时 MCP 服务仍可启动，`list_pets` 会返回 `backend_unavailable` 的结构化错误。

端点：`http://127.0.0.1:8000/mcp`（无状态 Streamable HTTP）与 `http://127.0.0.1:8000/health`。

验证：

```powershell
pytest -q                        # 当前 13 项，全部通过；使用 httpx.MockTransport，不访问真实 Go 服务
npx @modelcontextprotocol/inspector   # Transport 选 Streamable HTTP，URL 填 http://127.0.0.1:8000/mcp
```

### 4.2 B · AnythingLLM MCP

```powershell
# 前置：本机 AnythingLLM 已运行，并在 Settings → API Keys 生成密钥
cd AnythingLLMMCP
$env:ANYTHINGLLM_API_KEY = "<你的 API Key>"     # 必填，缺失则启动即退出
python server.py                                 # 默认 127.0.0.1:8765
```

端点：`http://127.0.0.1:8765/mcp`。客户端需先 `initialize`，再 `tools/list` / `tools/call`。

无真实实例时可先起本地契约桩联调：另开一个终端 `cd AnythingLLMMCP`，`set ANYTHINGLLM_API_KEY=sk-mock-anythingllm-local` 后 `python mock_backend.py`（监听 3001）；`server.py` 未显式配置时默认回退到该桩与 `demo-workspace`。桩只返回固定演示数据，不做真实入库与检索。

验证：`python -m pytest tests -q`（当前 13 项，覆盖工具分发、上传校验与错误透传，不连真实后端）；或按 `AnythingLLMMCP/README.md` 里的两条 `curl.exe` 示例手工调用。

### 4.3 C · 上传网页

无需安装，直接双击 `AnythingLLMWebPage\index.html`：

1. 顶部填 Base URL（默认 `http://localhost:3001`）与 API Key；
2. 点「加载工作区」拉取列表，或直接手填工作区 slug；
3. 输入消息发送，完成多轮对话。

若 AnythingLLM 端口不是默认值，可用参数覆盖：

```text
index.html?api=http://localhost:50368
index.html?api=http://localhost:50368/api     # 两种写法等价，结尾的 /api 会被自动去掉
```

API Key 与 Base URL 只保存在页面内存，不写入 localStorage 或任何持久存储；刷新页面即清空。

### 4.4 D · xAgent（定制 Agent）

```powershell
cd Agent\xAgent
pip install -r requirements.txt
python main.py                     # 等价于 python -m tui
python main.py --config D:\path\to\your.ini
```

首次启动若当前目录没有 `config.ini`，会自动生成一份带 `sk-mock-` 占位值的模板，改完 `[llm]` 段后重启。默认工作目录即启动目录（`[agent] workspace = .`），`AGENTS.md`、`.agents/skills/`、`.agents/sessions/` 都相对它解析。

验证：`python -m pytest tests -q`（60 个测试函数，含 `test_architecture.py` 的分层约束检查）。运行期每次工具调用会在 `.agents/logs/xagent.log` 追加一行 JSON（工具名、状态、耗时、脱敏参数）。

### 4.5 一键启动完整工作区（office）

```powershell
cd office
.\start.bat        # 依次拉起 8080/8090/8000/8765 四个本地服务，再启动 TUI
```

注意：`office/start.bat` 基于脚本所在目录用相对路径定位上级各组件，Python 优先 `py -3`、回退 PATH 中的 `python`，不写死绝对安装目录。服务清单与实机验收记录见 `office/交付说明.md`。

---

## 5. 配置与密钥

### 5.1 配置来源

- `Agent/xAgent`、`office`：`config.ini`（`[llm] base_url / api_key / model / timeout`，`[agent] max_iterations / workspace / context_window`，`[context]`、`[session]`、`[mcp]`、`[voice]`、`[ui]` 各段见 `Agent/xAgent/README.md` 第 6 节）。
- `office/.mcp.json`：MCP Server 清单（`type` + `url` 走 HTTP，或 `command` + `args` 走 stdio）。
- `PetHospitalMCP`：只认环境变量，不读配置文件。

### 5.2 环境变量

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `XAGENT_API_KEY` / `XAGENT_BASE_URL` / `XAGENT_MODEL` | 覆盖 `config.ini` 的模型配置（优先级更高） | — |
| `XAGENT_CONFIG` | 指定配置文件路径 | 当前目录 `config.ini` |
| `XAGENT_SEARCH_ENDPOINT` / `XAGENT_SEARCH_API_KEY` | `searchWeb` 的搜索后端与密钥（缺配置时工具返回明确提示） | 空 |
| `PET_HOSPITAL_BASE_URL` | 宠物医院 Go 后端地址 | `http://127.0.0.1:8080` |
| `MCP_HOST` / `MCP_PORT` | 宠物医院 MCP 服务监听地址 | `127.0.0.1` / `8000` |
| `ANYTHINGLLM_BASE_URL` | AnythingLLM 地址 | `http://localhost:3001` |
| `ANYTHINGLLM_API_KEY` | AnythingLLM 密钥（必填，缺失即退出） | — |
| `ANYTHINGLLM_SLUG` | 默认工作区 slug（为空时自动取第一个） | 空 |
| `HOST` / `PORT` | AnythingLLM MCP 监听地址 | `127.0.0.1` / `8765` |

### 5.3 密钥约定

- 仓库内所有 `config.ini` 与示例命令一律使用 `sk-mock-000000000000000000000000` 这类**占位值**，不含任何真实密钥。
- 真实密钥只通过环境变量或网页输入框提供，不写进文件、不写进前端代码。
- 若曾在历史提交中放过密钥，请在对应服务后台**轮换该密钥**——从 Git 历史删除并不会让它失效。

---

## 6. 目录结构（节选）

```text
LLM/
├── README.md                       ← 本文件
├── .gitignore
├── config.ini                      ← 占位配置（占位 api_key）
├── Agent/
│   ├── xAgent/                     ← D：Agent 内核 + TUI
│   │   ├── main.py  requirements.txt  pyproject.toml  config.ini  build_exe.bat
│   │   ├── core/                   ← 与界面无关的内核（config/agent/context/skills/tracing/session_store/llm/tools）
│   │   ├── tui/                    ← Textual 界面
│   │   ├── docs/architecture.md
│   │   └── tests/                  ← 60 个测试函数
│   └── Practice02/                 ← 早期单文件练习 + 架构图（.mmd / .png）
├── PetHospitalMCP/
│   ├── pet-hospital-mcp/           ← A：MCP 服务端
│   │   ├── src/pet_hospital_mcp/   ← server / rest_client / errors / logging_config / tools
│   │   ├── tests/                  ← 13 项
│   │   └── README.md
│   ├── windows/                    ← A 的上游 Go 后端发行包
│   └── prompt-step1.md             ← 阶段任务书（开发提示词，非运行文档）
├── AnythingLLMMCP/                 ← B：anythingllm MCP 服务端
│   ├── server.py  mock_backend.py  README.md  tests/
├── AnythingLLMWebPage/             ← C：单文件网页
│   ├── index.html  README.md
├── office/                         ← xAgent 工作区样例（.mcp.json / config.ini / AGENTS.md / .agents/skills / 交付说明）
└── guizang-ppt-skill/              ← 第三方技能包（MIT），未改造
```

---

## 7. 附属文件与历史产物说明

为免误读，以下目录/文件不是主线实现，作用如下：

| 路径 | 性质 | 说明 |
| --- | --- | --- |
| `Agent/Practice02/` | 早期练习 | 三个单文件脚本演示工具定义与调用；`code_*.mmd/png` 为架构与流程图，非生产代码 |
| `PetHospitalMCP/prompt-step1.md` | 开发任务书 | 写给自己/助手的阶段需求文档，描述目标而非现状；**当前实现以 `pet-hospital-mcp/README.md` 为准** |
| `PetHospitalMCP/windows/` | 第三方上游 | Go 后端发行包，含 `README.md`（其 Github Releases 链接指向原项目，不是本仓库）；`pethospital.exe`、`data/pet.db` 按 `.gitignore` 不入库 |
| `office/_demo_mcp_server.py` | 联调辅助 | 临时演示 MCP Server（`add` / `greet` 两个工具），用于验证 xAgent 的 MCP 客户端接入 |
| `office/_start_*.bat` | 启动辅助 | 分别拉起 demo / 宠物医院 / AnythingLLM MCP，以及本地 AnythingLLM 契约桩（`_start_mock_anythingllm.bat`） |
| `office/.agents/mouse_probe.log` | 调试日志 | TUI 鼠标事件排查残留，可删除，不影响运行 |
| `AnythingLLMMCP/err.log`、`out.log` | 运行日志 | 本地联调输出，已被 `.gitignore` 排除，不入库 |
| `guizang-ppt-skill/` | 第三方 | 归藏 PPT 技能包整目录引用，保留原 LICENSE 与 CONTRIBUTING，未修改 |

---

## 8. 安全说明

- 所有服务默认只监听 `127.0.0.1`，属本机教学/实验用途。`pet-hospital-mcp` 按课程要求**不实现认证、权限与 CORS / Origin 校验**，请勿直接暴露到公网。
- `pet-hospital-mcp` 的调用日志为单行 JSON（`timestamp / tool_name / params / status / duration_ms`），其中 `ownerPhone`、`ownerAddr`、`chipNo` 及其 snake_case 写法（`owner_phone`、`owner_addr`、`chip_no`）在任意嵌套层级递归替换为 `[REDACTED]`。
- xAgent 的文件工具带工作目录边界校验：相对路径解析到工作区后越界即拒绝；生产装配强制 `strict_root`，root 缺失时拒绝宽松路径访问；非空目录默认拒绝删除，需显式 `recursive=true`。`RunCli` 拦截破坏性命令、shell 解释器、下载执行类命令及含管道/重定向拼接的参数，可选命令白名单。
- `AnythingLLMWebPage` 用 `textContent` 渲染消息（不做 HTML 拼接），带 CSP `meta`，Key 仅存内存不落盘，输入限长并校验 Base URL 协议。

---

## 9. 验证清单

| 检查项 | 命令 / 动作 | 预期 |
| --- | --- | --- |
| A 单元测试 | `cd PetHospitalMCP\pet-hospital-mcp && pytest -q` | 13 passed |
| A 健康检查 | `curl http://127.0.0.1:8000/health` | `{"status":"ok"}` |
| A 工具可发现 | MCP Inspector 连 `http://127.0.0.1:8000/mcp` | 列出 `list_pets` |
| B 单元测试 | `cd AnythingLLMMCP && python -m pytest tests -q` | 13 passed |
| B 工具可发现 | 按 README 的 `tools/list` curl | 返回 5 个工具 |
| C 主流程 | 打开 `index.html` → 填 Key → 加载工作区 → 发消息 | 出现工作区下拉并返回回答 |
| D 单元测试 | `cd Agent\xAgent && python -m pytest tests -q` | 全部通过（60 个测试函数） |
| D 分层约束 | 同上，`tests/test_architecture.py` | core 不依赖前端框架 |
| 整体 | `cd office && start.bat` | 四个端口就绪后进入 TUI |

---

## 10. 第三方与许可

- `guizang-ppt-skill/`、`office/.agents/skills/guizang-ppt-skill/`：第三方技能包，按其自带 `LICENSE`（MIT）授权，未做改造，不作为本项目成果。
- `office/.agents/skills/horoscope-daily/`：外部技能市场下载，来源见其 `_meta.json`，未做改造；其余自撰技能与 `AgentBrowser` / `OfficeCLI` 的归属见 `office/.agents/skills/NOTICE.md`。
- `PetHospitalMCP/windows/`：Go 宠物医院后端发行包，自带 `LICENSE`；其可执行文件与示例数据库不入库，本机/课程资料放置。
- `office/agent-browser-win32-x64.exe`、`office/officecli-win-x64.exe`：第三方 CLI 发行物，本机放置、不入库。
- 其余模块为本仓库作者编写：`pet-hospital-mcp` 在 `pyproject.toml` 中声明 MIT；`Agent/xAgent`、`AnythingLLMMCP`、`AnythingLLMWebPage` 供学习与实验使用。
