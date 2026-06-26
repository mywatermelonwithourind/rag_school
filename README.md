# 计算机学院智能问答系统

五人协作课程项目 — RAG 问答骨架（FastAPI + LangGraph + Milvus + MySQL + Next.js）。

> 当前阶段：**结构与接口已立好**，各模块为 mock/桩实现，可并行补全。

---

## 目录结构

```
rag_school/
├── docker-compose.yml          # Milvus standalone + MySQL
├── docker/mysql/init.sql       # 父块 / FAQ 表 + 示例数据
├── .env.example
├── README.md
├── backend/
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── .env.example
│   ├── data/raw/               # 原始文档目录（入库用）
│   └── app/
│       ├── main.py             # FastAPI 入口
│       ├── core/               # 成员 E：配置、DB、工具
│       │   ├── config.py
│       │   ├── database.py
│       │   └── utils.py
│       ├── data/               # 成员 A：文档加载、切片、入库
│       │   ├── loader.py
│       │   ├── chunking.py
│       │   └── ingest.py
│       ├── retrieval/          # 成员 B：Milvus + 混合粗排 + rerank
│       │   ├── milvus_client.py
│       │   ├── embedding.py
│       │   ├── hybrid_ranker.py
│       │   ├── reranker.py
│       │   └── pipeline.py
│       ├── query_understanding/ # 成员 C：路由、改写、FAQ
│       │   ├── router.py
│       │   ├── rewrite.py
│       │   └── faq_matcher.py
│       ├── workflow/           # 成员 D：LangGraph 编排 + LLM
│       │   ├── state.py        # ★ AgentState 契约
│       │   ├── graph.py        # ★ 主图装配
│       │   ├── llm_client.py
│       │   └── nodes/          # ★ 各节点骨架
│       │       ├── preprocess.py
│       │       ├── rule_match.py
│       │       ├── query_route.py
│       │       ├── executor.py
│       │       ├── retrieval.py
│       │       └── answer.py
│       └── api/                # 成员 E：FastAPI 路由 + SSE
│           ├── schemas.py
│           └── routes/
│               ├── chat.py
│               └── health.py
└── frontend/                   # 成员 E：Next.js 聊天 UI
    └── src/
        ├── app/
        └── components/
            ├── ChatInterface.tsx
            └── MessageList.tsx
```

---

## 五人分工建议

| 成员 | 目录 | 职责 | 当前桩 / TODO |
|------|------|------|---------------|
| **A** | `app/data/` | 文档加载、父子切片、入库脚本 | 支持 `.pdf/.docx/.txt/.md` 上传解析；父块约 2000 token，子块约 150–250 token 语义切分；父块 upsert MySQL，子块向量写 Milvus |
| **B** | `app/retrieval/` | Milvus 召回、父块聚合、混合粗排、qwen3-rerank | 全 mock；`pipeline.py` 有 mock 父块 |
| **C** | `app/query_understanding/` | 路由分类、多轮改写、FAQ 匹配 | 规则占位；FAQ 读内存 mock，未连 MySQL |
| **D** | `app/workflow/` | LangGraph 主图、AgentState、LLM 生成、兜底 | 节点已串好；`llm_client.py` mock |
| **E** | `app/core/` + `app/api/` + `frontend/` + Docker | 配置、DB、API、SSE、前端、部署 | 健康检查仅 ping MySQL |

---

## 核心契约

### AgentState（`app/workflow/state.py`）

LangGraph 全局状态，字段均带类型与 writer/reader 注释：

| 字段 | 类型 | 写入节点 | 主要读取节点 |
|------|------|----------|--------------|
| `question` | str | api | 全部 |
| `history` | list[HistoryMessage] | api | preprocess, executor, answer |
| `session_id` | str | api | 全部 |
| `normalized_question` | str | preprocess | rule_match, query_route |
| `session_context` | dict | preprocess | query_route, executor, answer |
| `faq_match` | FAQMatchResult | rule_match | query_route, executor, answer |
| `faq_short_circuit` | bool | rule_match | query_route |
| `query_intent` | QueryIntent | query_route | executor, retrieval, answer |
| `retrieval_plan` | RetrievalPlan | query_route | retrieval, answer |
| `retrieval_queries` | list[str] | executor | retrieval |
| `sources` | list[SourceChunk] | retrieval | answer |
| `retrieval_sufficient` | bool | retrieval（B 定义） | answer（D 只读兜底） |
| `answer` | str | answer | api |
| `citations` | list[Citation] | answer | api |
| `debug_trace` | list[str] | 各节点 append | api |

`QueryIntent` 四值：`rewrite` | `decompose` | `direct_answer` | `direct_parent_chunk`

### LangGraph 主图（`app/workflow/graph.py`）

```
preprocess → rule_match → query_route
    ├─ direct_parent_chunk ──→ answer → END
    ├─ direct_answer ────────→ answer → END
    └─ rewrite / decompose → executor → retrieval → answer → END
```

| 节点 | 模块 | 说明 |
|------|------|------|
| preprocess | workflow (D) | 清洗问题、初始化 session_context |
| rule_match | query_understanding (C) | FAQ 规则匹配 |
| query_route | query_understanding (C) | 意图分类 + retrieval_plan；**条件边分流** |
| executor | query_understanding (C) | 仅 rewrite/decompose：产出 retrieval_queries |
| retrieval | retrieval (B) | Milvus → 粗排 → rerank；写入 `retrieval_sufficient` |
| answer | workflow (D) | 生成答案 / FAQ 直出 / 材料不足兜底 |

**跨组接口对齐**

- **C → 图**：`direct_answer` 判定须保守，拿不准优先 `rewrite`（见 `router.ROUTING_PROMPT_CONSTRAINTS`），避免无材料 LLM 编造。
- **B → D**：`retrieval_sufficient` 判定标准由 B 在 `pipeline.is_retrieval_sufficient()` 定义；D 在 `answer` 节点只读该字段做兜底，不重复实现阈值。

### API 契约

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/chat` | 同步问答（调试） |
| POST | `/api/chat/stream` | SSE 流式 |
| POST | `/api/ingest/upload` | 上传本地文档并清洗入库 |

SSE 事件：`token` | `citations` | `done`

完整请求/响应字段、SSE 各事件 `data` JSON 结构、共享类型与 curl/fetch 示例见 **[docs/API.md](docs/API.md)**。

---

## 快速启动

### 1. 启动数据库（Docker）

部署细节、防火墙、远程连库见 **[docs/DEPLOY.md](docs/DEPLOY.md)**。

```bash
cp .env.example .env   # 服务器上：填 MySQL/MinIO 密码
docker compose up -d
docker compose ps      # 确认四个容器 healthy
```

对外端口由根 `.env` 的 `MYSQL_HOST_PORT` / `MILVUS_HOST_PORT` / `MINIO_CONSOLE_HOST_PORT` 控制（MinIO 控制台可选）。

### 2. 后端（本地）

```bash
cd backend
cp .env.example .env
# ⚠️ 连远程服务器：必须把 RAG_MYSQL_HOST / RAG_MILVUS_HOST 改成服务器 IP

python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/check_connectivity.py   # 先自检 MySQL/Milvus 连通
python scripts/create_child_chunks_collection.py  # 首次使用前创建 Milvus 子向量 collection
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. 前端（本地）

```bash
cd frontend
npm install
# 可选：设置 NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
npm run dev
```

浏览器打开 http://localhost:3000

### 4. 联调示例

- FAQ 命中：「计算机学院办公时间是什么」「几点上班」
- 普通检索：「毕业学分要求是多少」
- 寒暄：「你好」

---

## 环境变量

见 `backend/.env.example`，前缀 `RAG_`。关键项：

- `RAG_MYSQL_*` — MySQL 连接（可指向服务器 IP）
- `RAG_MILVUS_*` — Milvus 连接
- `RAG_LLM_*` — 百炼 deepseek（`RAG_LLM_MOCK=true` 时不调 API）
- `RAG_EMBEDDING_MOCK` / `RAG_RERANK_MOCK` — embedding/rerank 桩开关

---

## 数据库表

见 `docker/mysql/init.sql`：

- `parent_chunk` — 父块全文（FULLTEXT）
- `faq_rule` — FAQ 标准问 + target_parent_chunk_ids + answer_mode
- `faq_alias` — 别名 + match_type (exact/contains/regex)

---

## 协作约定

1. **只改自己目录**，跨模块调用走已有函数签名，改签名先在群里同步。
2. **AgentState 字段变更**必须更新 `state.py` 注释并通知 workflow 组。
3. 未完成逻辑用 `# TODO(组名):` 标注。
4. **开发期并行、集成期串联**：五人可**同时**开工，各模块靠 mock 开关在桩数据上独立开发、互不阻塞——`RAG_EMBEDDING_MOCK` / `RAG_RERANK_MOCK` / `RAG_LLM_MOCK`（见 `backend/.env.example`），FAQ 当前为内存 mock（`faq_matcher.py`），retrieval 有 mock 父块（`pipeline.py`），**不必等 A 入库才能写 B/C/D 的逻辑**。下面这条是**最后集成、各模块换成真实现时的串联顺序**，不是开发期的先后依赖：data 入库 → retrieval 真召回 → query_understanding FAQ → workflow LLM → api SSE。

## 未来扩展（本阶段不实现）

**多知识库 / 多租户**：当前 AgentState 与表结构均为**单域**（计算机学院），不含 `kb_id` / `user_id` 路由字段。若后续需支持多知识库，可在 API 层增加 `kb_id` 参数、检索与 FAQ 查询加过滤条件、Milvus collection 分区或分库——届时再扩展 `state.py` 与配置，本阶段代码不预留。
