# API 文档

计算机学院智能问答系统 — HTTP API 说明。

> 本文档依据当前代码生成（`app/api/`、`app/workflow/state.py`）。桩实现或未对外暴露的字段标注 **TODO/待定**，不编造代码中不存在的字段。

---

## 概览

| 项 | 说明 |
|----|------|
| **Base URL（本地默认）** | `http://127.0.0.1:8000` |
| **API 前缀** | `/api`（环境变量 `RAG_API_PREFIX`，默认 `/api`） |
| **完整路径示例** | `http://127.0.0.1:8000/api/chat/stream` |
| **Content-Type（POST）** | `application/json` |
| **字符编码** | UTF-8 |
| **CORS** | 默认允许 `http://localhost:3000`（`RAG_CORS_ORIGINS`） |
| **OpenAPI 交互文档** | `http://127.0.0.1:8000/docs` |

### 通用响应约定

- **成功**：HTTP `200`，响应体为 JSON（SSE 接口除外，见下文）。
- **请求体验证失败**：HTTP `422`，FastAPI 标准 `detail` 数组（字段名、错误类型、提示信息）。当前路由**未定义**自定义错误码或统一 `{ "code": ..., "message": ... }` 包装。
- **服务端异常**：HTTP `500`，FastAPI 默认错误体。**TODO(api/E)**：是否需要统一错误格式待定。
- **AgentState 内部字段**（如 `history`、`query_intent`、`sources`、`retrieval_sufficient`、`faq_match`、`error`）**不**通过 HTTP 响应暴露；API 层仅映射 `answer`、`citations`、`session_id`、`debug_trace`（见各接口说明）。

### 错误码约定（当前实现）

| HTTP 状态 | 场景 | 响应体（当前） |
|-----------|------|----------------|
| `200` | 成功 | 见各接口 |
| `422` | `ChatRequest` 校验失败（如 `question` 为空、超长） | FastAPI `{"detail":[...]}` |
| `500` | LangGraph / 未捕获异常 | FastAPI 默认 `Internal Server Error` |

**TODO(api/E)**：业务错误码（如检索超时、LLM 不可用）尚未定义；`AgentState.error` 字段存在，计划经 SSE `error` 事件暴露（当前不发送，见 [事件：`error`](#事件error预留)）。

---

## GET `/api/health`

### 用途

服务与依赖连通性探测。当前仅 ping MySQL；Milvus 固定返回 `false`（桩）。

### 请求

无 query 参数、无请求体。

### 响应体

对应 `HealthResponse`（`app/api/schemas.py`）。

| 字段 | 类型 | 含义 |
|------|------|------|
| `status` | `string` | `"ok"`（MySQL 可达）或 `"degraded"`（MySQL 不可达） |
| `mysql` | `boolean` | MySQL 连接是否正常 |
| `milvus` | `boolean` | 当前**固定为 `false`**；**TODO(api/retrieval)**：实现 Milvus ping |

### 示例

```json
{
  "status": "degraded",
  "mysql": false,
  "milvus": false
}
```

### 错误情况

- 一般返回 `200`（即使依赖不可用，`status` 为 `degraded`）。
- 应用未启动：连接失败（非 JSON）。

---

## POST `/api/chat`

### 用途

同步问答，**调试用**。跑完整个 LangGraph 流水线后一次性返回结果。生产前端默认走 `/api/chat/stream`。

### 请求体

对应 `ChatRequest`（`app/api/schemas.py`）。

| 字段 | 类型 | 必填 | 约束 | 含义 |
|------|------|------|------|------|
| `question` | `string` | 是 | 长度 1–2000 | 用户**当前轮**问题 |
| `session_id` | `string \| null` | 否 | 默认 `null` | 会话 ID；上下文加载钥匙。为 `null` 时后端生成 UUID |

#### `session_id` 与历史加载（与代码一致）

- 前端**不再传 `history`**。请求体只包含当前 `question` 和可选 `session_id`。
- `session_id` 是后端加载上下文的钥匙：首轮传 `null` 或省略，后端生成 UUID 并在响应中返回；后续每轮前端回传同一个 `session_id`。
- 后端 `_build_initial_state()` 会按 `session_id` 从 `chat_conversation` 表加载最近 N 轮已完成问答，展开为 `AgentState.history`：
  - 每条记录展开为 `user: question` 和 `assistant: answer` 两条消息。
  - `query_intent`、`citations`、`debug_trace` 仅用于存档分析，不进入 LLM 上下文。
- N 由 `RAG_CHAT_HISTORY_WINDOW` 配置，默认 `4` 轮（最多 8 条 history message）。
- 时序固定为：**先读旧历史 → 再跑 LangGraph → 最后写入本轮 Q&A**。当前这句问题不会混进本轮读取到的历史里。
- 写入本轮存档失败只记录日志，不影响接口返回答案。

#### 请求示例

```json
{
  "question": "计算机学院办公时间是什么",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

首条消息可省略 `session_id`：

```json
{
  "question": "毕业学分要求是多少",
  "session_id": null
}
```

### 响应体

对应 `ChatResponse`；字段来自 LangGraph 执行后的 `AgentState`。

| 字段 | 类型 | AgentState 来源 | 含义 |
|------|------|-----------------|------|
| `answer` | `string` | `answer` | 最终回答文本 |
| `citations` | `array` | `citations` | 出处列表，见 [Citation](#citation) |
| `session_id` | `string` | `session_id` | 本会话 ID（请求传入或后端新生成） |
| `debug_trace` | `array` of `string` | `debug_trace` | 节点执行轨迹，联调用 |

**未返回的 AgentState 字段**（内部使用）：`sources`、`query_intent`、`retrieval_sufficient`、`faq_match`、`normalized_question` 等。

#### 响应示例

```json
{
  "answer": "计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。",
  "citations": [
    {
      "parent_chunk_id": "pc_office_hours",
      "doc_id": "doc_admin_guide",
      "snippet": "计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。",
      "relevance_score": 0.9
    }
  ],
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "debug_trace": [
    "preprocess",
    "rule_match",
    "query_route:direct_parent_chunk",
    "answer:faq_direct"
  ]
}
```

### 错误情况

| 场景 | HTTP | 说明 |
|------|------|------|
| `question` 缺失或为空 | `422` | Pydantic 校验 |
| `question` 超过 2000 字 | `422` | Pydantic 校验 |
| 流水线内部异常 | `500` | 无自定义错误体 |

---

## POST `/api/chat/stream`

### 用途

SSE（Server-Sent Events）流式问答。前端生产路径。

### 请求体

与 [POST `/api/chat`](#post-apichat) **完全相同**（`ChatRequest`）。  
`session_id` 语义一致：前端不传 history，后端按 `session_id` 加载最近 N 轮历史。

### 响应

| 项 | 值 |
|----|-----|
| HTTP 状态 | `200` |
| `Content-Type` | `text/event-stream` |
| 响应头 | `Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no` |

每条 SSE 消息格式：

```
data: <JSON 字符串>\n\n
```

**注意**：`data` 载荷**均为 JSON 对象**（含 `type` 字段），**不是**纯文本 token 行。

### 当前实现时序（桩阶段，与代码一致）

1. 服务端先按 `session_id` 从库加载最近 N 轮历史，构造 `AgentState.history`。
2. 服务端同步跑完 `run_rag_pipeline()`，得到完整 `answer`、`citations` 等。
3. 将 `state.answer` **逐字符**推送为 `token` 事件（展示层流式；**唯一答案来源是 answer 节点产出的 `state.answer`**）。
4. 若有 `citations`，推送一条 `citations` 事件。
5. 最后**必定**推送一条 `done` 事件。
6. `done` 发出后才异步写入本轮 Q&A 到 `chat_conversation`；如果客户端中途断开导致流未完整结束，本轮不存档，避免残缺答案进入历史。

（真流式上线后）若流中途出错，**计划**在 `done` 之前推送 `error` 事件，见 [事件：`error`](#事件error预留)）。

因此当前「流式」是**展示层流式**，非端到端 LLM token 流。

---

### 事件：`token`

| 项 | 说明 |
|----|------|
| **发出时机** | 流水线完成后，按 `state.answer` 顺序逐个发出（当前为逐字符） |
| **`data` 格式** | JSON 对象，**不是**纯文本 |

```json
{
  "type": "token",
  "content": "计"
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `type` | `"token"` | 固定 |
| `content` | `string` | 本段增量文本（当前常为单字符；真 LLM 流式后可能为多 token 字符串） |

---

### 事件：`citations`

| 项 | 说明 |
|----|------|
| **发出时机** | 全部 `token` 发完之后；**仅当** `state.citations` 非空时发出（无出处则跳过此事件） |
| **`data` 格式** | JSON 对象 |

```json
{
  "type": "citations",
  "content": [
    {
      "parent_chunk_id": "pc_office_hours",
      "doc_id": "doc_admin_guide",
      "snippet": "计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。",
      "relevance_score": 0.9
    }
  ]
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `type` | `"citations"` | 固定 |
| `content` | `Citation[]` | 与 `ChatResponse.citations` / `AgentState.citations` 同结构 |

**当前不含**：文档标题、URL、页码等。**TODO(workflow/D)**：是否在 `Citation` 增加 `doc_title` 等待定。

---

### 事件：`done`

| 项 | 说明 |
|----|------|
| **发出时机** | 流结束前的**最后一条**事件（在 `token` 与可选的 `citations` 之后） |
| **`data` 格式** | JSON 对象 |

```json
{
  "type": "done",
  "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "debug_trace": [
    "preprocess",
    "rule_match",
    "query_route:direct_parent_chunk",
    "answer:faq_direct"
  ],
  "answer": "计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。"
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `type` | `"done"` | 固定 |
| `session_id` | `string` | 会话 ID，前端应保存并在后续请求回传 |
| `debug_trace` | `string[]` | 节点轨迹 |
| `answer` | `string` | 完整答案（权威值；见 [边界与约定 — answer 与 token 的一致性](#answer-与-token-的一致性)） |

**TODO(api/E)**：`done` 是否额外携带其他调试字段待定；错误信息走 `error` 事件而非 `done`（见下）。

---

### 事件：`error`（预留）

| 项 | 说明 |
|----|------|
| **当前桩阶段** | **不发送**。流水线在推流前已同步跑完，流中途不会出错；HTTP 层错误仍为 `422`/`500`（无 SSE 体）。 |
| **启用时机** | **TODO(workflow/D + api/E)**：LLM 真流式后，错误可能发生在 HTTP `200` 已发出、已推送部分 `token` 之后，此时无法再返 `500`，须通过 SSE 通知前端。 |
| **发出时机（计划）** | 流中途发生可恢复/不可恢复错误时，在**最后一条 `done` 之前**发出；发出后是否仍发 `done` **TODO** 待定（建议：fatal 错误只发 `error` 不发 `done`）。 |
| **数据来源（计划）** | `AgentState.error`（`app/workflow/state.py`，当前各节点**几乎未写入**该字段） |

```json
{
  "type": "error",
  "content": "LLM 调用超时",
  "recoverable": false
}
```

| 字段 | 类型 | 含义 |
|------|------|------|
| `type` | `"error"` | 固定 |
| `content` | `string` | 人类可读错误说明（来自 `AgentState.error` 或等价信息） |
| `recoverable` | `boolean` | 是否可重试；**TODO(api/E)**：判定规则待定，默认 `false` |

**前端要求**：消费逻辑**应预先**处理 `type === "error"`（即使当前收不到），真流式上线后无需改解析框架。`ChatInterface.tsx` **当前未实现**该分支。

---

### 完整 SSE 响应流示例

FAQ 直出路径（有 citations）：

```
data: {"type":"token","content":"计"}

data: {"type":"token","content":"算"}

data: {"type":"token","content":"机"}

…（省略若干 token）…

data: {"type":"citations","content":[{"parent_chunk_id":"pc_office_hours","doc_id":"doc_admin_guide","snippet":"计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。","relevance_score":0.9}]}

data: {"type":"done","session_id":"f47ac10b-58cc-4372-a567-0e02b2c3d479","debug_trace":["preprocess","rule_match","query_route:direct_parent_chunk","answer:faq_direct"],"answer":"计算机学院办公室工作时间为周一至周五 8:30-17:00，中午 12:00-13:30 休息。"}

```

寒暄 `direct_answer` 且无 citations 时，**无** `citations` 事件，直接 `done`：

```
data: {"type":"token","content":"["}

…

data: {"type":"done","session_id":"...","debug_trace":[...],"answer":"[MOCK LLM 回答] ..."}

```

---

### 前端消费方式（与 `ChatInterface.tsx` 对齐）

| 项 | 当前实现 |
|----|----------|
| API | **`fetch` + `ReadableStream`**（`response.body.getReader()`） |
| 未使用 | 原生 `EventSource`（因需 **POST** 请求体，EventSource 仅支持 GET） |
| 解析 | 按行读取，`line.startsWith("data: ")` → `JSON.parse(line.slice(6))` |
| `token` | `fullAnswer += event.content`，更新 UI（`event.content` 为 **string**） |
| `citations` | 暂存 `event.content`（**Citation[]**），流结束后写入消息 |
| `done` | `setSessionId(event.session_id)`；若存在 `event.answer` **覆盖** `fullAnswer` |
| `error` | **TODO（前端应预留）**：展示 `event.content` 为错误文案、**停止**累积 token、`streaming: false`；是否允许重试看 `recoverable` |
| HTTP 非 2xx | `!res.ok` 抛错；显示「请求失败：HTTP xxx」 |
| 流中断 / 无 SSE 错误事件 | 前端 catch 或读流异常；**当前**无 SSE 内错误事件可解析 |

---

### 错误情况

| 场景 | 行为 |
|------|------|
| 请求体验证失败 | HTTP `422`，**无** SSE 流 |
| 流水线异常（桩阶段，推流前） | HTTP `500`，**无** SSE 流 |
| 流水线已成功、流中途异常（真流式，**TODO**） | HTTP 仍为 `200`；计划发 `error` 事件 |
| 流中断 / 网络错误 | 前端 catch，助手消息显示错误文案 |

---

## POST `/api/ingest/upload`

### 用途

上传一个本地文档，后端解析文本、清洗、父子切片，并写入知识库。

支持格式：`.pdf`、`.docx`、`.txt`、`.md`。

### 请求

`multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | `file` | 是 | 待入库文档 |
| `kb_id` | `string` | 否 | 默认 `kb_cs_college` |
| `write_vectors` | `boolean` | 否 | 默认 `true`，是否写入 Milvus 子块向量 |
| `fail_on_vector_error` | `boolean` | 否 | 默认 `false`，Milvus 写入失败时是否让整个请求失败 |

### 切片策略

- 父块：按语义单元打包，目标约 `2000 token`。
- 子块：基于段落/句子语义切分，目标约 `200 token`，尽量保持在 `150–250 token`。
- 当前 token 统计为轻量估算，后续可替换为 embedding 模型 tokenizer。

### 响应体

对应 `IngestResponse`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `docs` | `number` | 处理文档数，上传接口通常为 `1` |
| `skipped_docs` | `string[]` | 未提取到文本而跳过的文档 |
| `parents` | `number` | 生成父块数 |
| `children` | `number` | 生成子块数 |
| `parent_upserts` | `number` | MySQL 父块写入/更新数 |
| `vector_upserts` | `number` | Milvus 子块向量写入/更新数 |
| `source_dir` | `string` | 上传来源标识 |
| `warnings` | `string[]` | 解析或向量写入提醒 |

---

## GET `/api/documents`

### 用途

展示知识库中已经入库的文件列表。前端知识库视图使用该接口。

### 请求参数

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `kb_id` | `string` | `kb_cs_college` | 知识库 ID |
| `limit` | `number` | `100` | 返回数量，范围 1–500 |

### 响应体

```json
{
  "total": 1,
  "items": [
    {
      "doc_id": "sample_xxxxxxxx",
      "kb_id": "kb_cs_college",
      "title": "sample",
      "source_name": "sample.pdf",
      "file_ext": ".pdf",
      "source_type": "upload",
      "content_chars": 12000,
      "parent_count": 4,
      "child_count": 36,
      "vector_count": 36,
      "status": "ready",
      "warnings": [],
      "updated_at": "2026-06-29T12:00:00"
    }
  ]
}
```

---

## 共享数据结构

### HistoryMessage

仅内部使用：`AgentState.history`。前端不再通过请求体传 history；API 层按 `session_id` 从 `chat_conversation` 表加载最近 N 轮问答，并展开为该结构。

| 字段 | 类型 | 说明 |
|------|------|------|
| `role` | `"user" \| "assistant"` | 发言角色 |
| `content` | `string` | 消息正文 |

### Citation

响应 / SSE / `AgentState.citations[]` / `CitationSchema` 四者对齐。

| 字段 | 类型 | 说明 |
|------|------|------|
| `parent_chunk_id` | `string` | 父块 ID |
| `doc_id` | `string` | 来源文档 ID（**不是**人类可读文档名） |
| `snippet` | `string` | 摘录（answer 节点截取 `content` 前 120 字） |
| `relevance_score` | `number` | 相关度（优先 `score_rerank`，否则 `score_hybrid`） |

定义位置：

- API：`app/api/schemas.py` → `CitationSchema`
- 工作流：`app/workflow/state.py` → `Citation`

### SourceChunk

**不对外暴露**于 HTTP API；仅 `AgentState.sources` 内部使用（retrieval → answer）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `parent_chunk_id` | `string` | 父块 ID |
| `child_chunk_id` | `string \| null` | 子块 ID |
| `content` | `string` | 块全文 |
| `doc_id` | `string` | 文档 ID |
| `kb_id` | `string` | 知识库 ID（单域内部字段，API 未暴露） |
| `score_vector` | `number` | 向量分 |
| `score_lexical` | `number` |  lexical 分 |
| `score_hybrid` | `number` | 混合粗排分 |
| `score_rerank` | `number \| null` | 精排分 |
| `metadata` | `object` | 扩展元数据 |

**TODO**：若前端需展示检索详情，需新增 API 字段或扩展 `Citation`，当前无计划字段。

---

## 调用示例

### curl — 健康检查

```bash
curl -s http://127.0.0.1:8000/api/health
```

### curl — 同步问答

```bash
curl -s -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"计算机学院办公时间是什么\",\"session_id\":null}"
```

### curl — SSE 流式（原始输出）

```bash
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"你好\",\"session_id\":null}"
```

### 前端 fetch — SSE（摘自 `ChatInterface.tsx` 逻辑）

```typescript
const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const res = await fetch(`${API_BASE}/api/chat/stream`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    question: "毕业学分要求是多少",
    session_id: sessionId, // 首条可为 null，后续用 done 返回的 session_id
  }),
});

const reader = res.body!.getReader();
const decoder = new TextDecoder();
let buffer = "";

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  for (const line of buffer.split("\n")) {
    if (!line.startsWith("data: ")) continue;
    const event = JSON.parse(line.slice(6));
    if (event.type === "token") { /* append event.content (string) */ }
    if (event.type === "citations") { /* event.content: Citation[] */ }
    if (event.type === "error") { /* TODO: show event.content, stop streaming */ }
    if (event.type === "done") { /* event.session_id, event.answer — authoritative */ }
  }
}
```

---

## 边界与约定

联调高频踩坑点集中说明。有代码依据的注明文件位置；未处理的如实标 **TODO**。

### 空与缺失

#### `question` 空白

| 输入 | 实际行为 | 依据 |
|------|----------|------|
| 字段缺失 | `422` | `ChatRequest.question` 必填 |
| `""` 空字符串 | `422`（`min_length=1`） | `app/api/schemas.py` |
| 仅空白如 `"   "` | **不** 422（长度 ≥ 1），进入流水线；`preprocess` 中 `normalize_text()` strip 后可能变为空串仍继续 | `app/api/schemas.py` + `app/core/utils.py` + `app/workflow/nodes/preprocess.py` |

**TODO(api/E)**：是否在 API 层 `strip` 后再校验非空（拒绝纯空白）。

#### history 来源

| 项 | 实际行为 |
|----|----------|
| 请求体是否包含 `history` | **不包含**。`ChatRequest` 只有 `question` 与 `session_id` |
| 后端如何得到历史 | 按 `session_id` 查询 `chat_conversation` 最近 N 轮，并展开为 `AgentState.history` |
| 首轮没有历史 | `session_id: null` 时后端生成新 UUID，查询结果为空 |
| 当前问题是否进入本轮 history | **不会**。当前问题在链路跑完后才写入数据库，供后续请求使用 |

#### `sources` 为空时 `answer` 如何兜底

取决于 `query_intent`（`app/workflow/nodes/answer.py`）：

| 路径 | 条件 | 结果 |
|------|------|------|
| `direct_answer` | 路由判定为寒暄等 | **不走**「未检索到」文案；`generate_answer()` 无材料生成（可能 MOCK） |
| `direct_parent_chunk` | FAQ 命中但拉不到父块 | 落入下方「材料不足」分支 |
| `rewrite` / `decompose` | `retrieval_sufficient == false` 或 `sources` 为空 | 固定兜底文案：「抱歉，我在知识库中没有找到与您问题足够相关的材料…」（`answer:insufficient`） |

**不会**因 sources 为空 alone 而自动改走 `direct_answer`；意图由 `query_route` 在检索前已确定。

#### `citations` 为空与 SSE 事件

| 场景 | 同步 `/api/chat` | SSE `/api/chat/stream` |
|------|------------------|------------------------|
| `citations: []` | 响应含 `"citations": []` | **不发送** `citations` 事件（`if citations:` 为假） |
| 有 citations | 正常返回数组 | 发送一条 `citations` 事件 |

代码：`chat.py` 第 70–76 行。空数组 **不会** 发 SSE `citations` 事件。

---

### `session_id` 生命周期

```
首次请求 session_id: null
    → _build_initial_state: body.session_id or new_session_id()
    → 按 session_id 加载最近 N 轮历史（新 UUID 通常为空）
    → 流水线使用该 session_id
    → done / ChatResponse 返回 session_id
    → 前端 setSessionId，后续请求回传同一值
    → 完成本轮后写入 chat_conversation，供下一轮加载
```

| 问题 | 实际行为 |
|------|----------|
| 后端是否存储 session | 不单独建 session 表；上下文来自 `chat_conversation.session_id` 下的历史问答 |
| 传入后端「没见过」的 `session_id` | 照常处理，历史为空；本轮完成后会写入该 session_id |
| 传 `null` vs 省略字段 | 等价，均触发后端新生成 UUID |

---

### 字段边界值

| 字段 | 约束 | 超出/非法 |
|------|------|-----------|
| `question` | 1–2000 字符 | `422` |
| `session_id` | `string \| null`，**无格式校验** | 任意字符串均可 |

#### `null` vs 字段缺失

| 字段 | 缺失 | 显式 `null` |
|------|------|-------------|
| `session_id` | 后端生成 UUID | 等同缺失，后端生成 UUID |
| `question` | `422` | `null` → **422**（期望 string） |

---

### answer 与 token 的一致性

- **`done.answer` 为权威完整答案**；流式 `token` 累积仅用于过程展示。
- 桩阶段两者应一致（token 来自对同一 `state.answer` 的逐字拆分，`chat.py` + `llm_client.stream_text`）。
- 真流式或网络丢包时，**可能出现** token 拼接与 `done.answer` 不一致；**前端应以 `done.answer` 为准覆盖**（`ChatInterface.tsx` 第 99–101 行已实现）。**这不是 bug**，是刻意设计。
- 若只收到 token 从未收到 `done`（断流），前端当前保留已累积内容或显示网络错误；**TODO(前端/E)**：超时与 `error` 事件策略。

---

### `content` 字段的多态

同一 JSON 键名 `content`，**类型随 `type` 变化**，不可统一当 string：

| `type` | `content` 类型 | 前端处理 |
|--------|------------------|----------|
| `token` | `string` | 字符串拼接 |
| `citations` | `Citation[]` | 数组，渲染出处列表 |
| `error`（预留） | `string` | 错误文案 |
| `done` | **无 `content` 字段** | 读 `answer`、`session_id` 等 |

必须先 `if (event.type === ...)` 再访问 `content`。

---

### 编码与特殊字符

| 项 | 实现 |
|----|------|
| SSE 序列化 | `json.dumps(..., ensure_ascii=False)`（`chat.py`） |
| 换行/引号/中文 | 标准 JSON 字符串转义（换行为 `\n`），整段 JSON 在**单行** `data: ` 后，**不会**因 answer 内含换行而拆成多行 SSE 字段 |
| 前端反序列化 | `JSON.parse(line.slice(6))`（`ChatInterface.tsx`） |
| 字符集 | HTTP JSON 请求/响应 UTF-8 |

中文长答案、snippet 中的标点均依赖上述机制；勿用手动字符串拼接 SSE 行。

---

### 并发与重复请求

| 项 | 实际行为 |
|----|----------|
| 同一 `session_id` 并发两请求 | 后端**无锁**、无排队；两次请求都会先读当时库中已完成历史，可能读不到对方尚未写入的本轮结果 |
| 后端 session 状态 | 无单独 session 表；按 `chat_conversation` 中已完成 Q&A 恢复上下文 |
| 前端防重复 | `loading === true` 时禁用输入/发送（`ChatInterface.tsx`） |
| 新请求 vs 进行中的流 | 前端 loading 禁止发送下一条；若用户/网络中断导致 SSE 未完整走到 `done` 后的存档点，本轮不写入历史 |

为避免同一 `session_id` 并发请求读到不一致历史，前端应保持“上一条未结束时不可发送下一条”（当前已通过 `loading` 实现）。

---

### CORS 与跨域

| 项 | 值 |
|----|-----|
| 配置项 | `RAG_CORS_ORIGINS`（`app/core/config.py`） |
| 默认值 | `["http://localhost:3000"]` |
| 行为 | `CORSMiddleware` 允许列表内 origin 的浏览器跨域请求（`app/main.py`） |

前端部署到其他地址（如 `http://192.168.x.x:3000`、生产域名）时，须在后端 `.env` 增加对应 origin，否则浏览器 `fetch` 被 CORS 拦截。  
**非浏览器**调用（curl、服务端）不受 CORS 限制。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-25 | 初版，对齐骨架代码实现 |
| 2026-06-25 | 补充 SSE `error` 预留、history 截断约定、「边界与约定」一节 |
| 2026-06-25 | 对话历史改为后端按 `session_id` 从数据库加载，前端不再传 `history` |
