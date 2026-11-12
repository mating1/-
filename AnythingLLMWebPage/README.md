# AnythingLLM 对话网页（单文件前端）

一个不依赖构建工具的单文件网页，用浏览器直连 AnythingLLM 的 `/api/v1`，完成「选工作区 → 多轮对话」的最小闭环。

## 功能

| 功能 | 实现位置 | 说明 |
| --- | --- | --- |
| 加载工作区列表 | `loadWorkspaces()` | `GET /api/v1/workspaces`，结果填入下拉框 |
| 手填工作区 slug | 顶部「或手填 slug」输入框 | 不依赖列表接口，可直接指定 |
| 流式对话（优先） | `postStream()` | `POST /api/v1/workspace/{slug}/stream-chat`，按 SSE `data:` 行逐段追加渲染 |
| 非流式回退 | `postJson()` | 流式不可用、无增量或请求失败时，回退 `POST /api/v1/workspace/{slug}/chat` |
| 多轮会话 | 发送表单逻辑 | `mode=chat`，`sessionId` 随会话保持；「新会话」重新生成 |
| 三态反馈 | 请求前后与 catch 分支 | 请求期间禁用发送按钮；成功渲染回答；失败输出 `HTTP <code>` 或异常信息 |
| 响应式布局 | `@media (max-width:640px)` | 窄屏下消息气泡、配置区与表单自动堆叠 |
| 输入面约束 | 各输入框 `maxlength` + URL 校验 | 消息/Key/Base/slug 限长；Base URL 必须为 `http://` 或 `https://` |

## 安全说明

- API Key 只保存在页面内存，**不写入 localStorage 或任何持久存储**；刷新页面即清空。
- 页面带 CSP `meta`，脚本/样式/连接源受限；回答与界面文本一律用 `textContent` 渲染，不插入 HTML。
- 本页只做对话，不含浏览器端文件上传；文档入库走 `AnythingLLMMCP` 的 `uploadLocalDocument` / `addDocumentsToWorkspace`。

## 使用

1. 双击 `index.html`（或拖进浏览器），无需本地服务器。
2. Base URL 默认 `http://localhost:3001`；若 AnythingLLM 端口不同，改写输入框。
3. 填入 AnythingLLM 后台 **Settings → API Keys** 生成的密钥，点「加载工作区」。
4. 选择工作区（或手填 slug）后即可对话。

### 参数覆盖基线地址

```text
index.html?api=http://localhost:50368
index.html?api=http://localhost:50368/api
```

两种写法等价：结尾的 `/api` 会被自动去掉，页面内部统一拼成 `${base}/api/v1/...`。

## 接口依赖

| 端点 | 方法 | 用途 |
| --- | --- | --- |
| `/api/v1/workspaces` | GET | 拉取工作区列表（`slug` / `name` / `documents`） |
| `/api/v1/workspace/{slug}/stream-chat` | POST | 流式提问，SSE 逐段返回 `textResponse` |
| `/api/v1/workspace/{slug}/chat` | POST | 非流式回退，读取 `textResponse` |

请求头统一带 `Authorization: Bearer <key>`。

## 本地联调桩

无真实 AnythingLLM 时，可先用 `AnythingLLMMCP/mock_backend.py` 起契约桩（`127.0.0.1:3001`）：Base URL 填 `http://localhost:3001`，Key 填 `sk-mock-anythingllm-local`，工作区 slug 为 `demo-workspace`。桩返回固定演示数据与 SSE 分片，仅用于验证前端下拉、流式/非流式问答与三态，不代表真实入库与检索。

## 已知限制

- 接入真实 AnythingLLM 前，工作区列表与对话只在桩后端上验证过 HTTP 契约；真实实例的字段与事件格式需在接入后复核。
- 流式解析按 AnythingLLM 开源版 SSE 格式（`data:` JSON、`textResponse`、`closed`）实现；后端事件格式不同会自动回退非流式。
- 页面只在内存中保存当前会话 ID，刷新页面即开始新会话。
