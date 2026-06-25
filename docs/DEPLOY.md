# 部署与远程数据库连接指南

数据库栈用 Docker 跑在**远程服务器**上，五人各自在**本地**跑 backend/frontend，通过 `.env` 连服务器上的 MySQL + Milvus。

相关文件：

| 文件 | 用途 |
|------|------|
| 根目录 `.env` | **仅** `docker compose`（MySQL/MinIO 密码、宿主机端口映射） |
| `backend/.env` | **仅** FastAPI 后端（`RAG_*` 连接串、LLM key、mock 开关） |

完整 API 说明见 [API.md](./API.md)。

---

## 一、服务器端：启动数据库

### 1. 准备配置

```bash
# SSH 登录服务器，进入仓库根目录
cp .env.example .env
# 编辑 .env：修改 MYSQL_* / MINIO_* 密码（生产务必强密码）
```

### 2. 启动

```bash
docker compose up -d
```

首次启动会拉镜像，**Milvus 较慢**（healthcheck `start_period: 90s`），属正常现象。

### 3. 确认四个容器健康

```bash
docker compose ps
```

期望（STATUS 列含 `healthy`）：

| 容器 | 说明 |
|------|------|
| `rag-mysql` | MySQL |
| `rag-milvus` | Milvus standalone |
| `rag-etcd` | Milvus 元数据（仅内网） |
| `rag-minio` | Milvus 对象存储（仅内网，控制台可选对外） |

若 `rag-milvus` 长时间 `starting`，等待 1–2 分钟后再查；仍 unhealthy 则：

```bash
docker compose logs milvus --tail 50
```

### 4. 防火墙放行清单

端口以**服务器根目录 `.env`** 中的映射变量为准（默认见 `.env.example`），**不要写死数字**，改映射后防火墙同步改。

| 类别 | 环境变量（宿主机端口） | 用途 | 是否必放 |
|------|------------------------|------|----------|
| **必放** | `MYSQL_HOST_PORT`（默认 3306） | 团队成员 backend 连 MySQL | ✅ 必放 |
| **必放** | `MILVUS_HOST_PORT`（默认 19530） | 团队成员 backend 连 Milvus | ✅ 必放 |
| **可选** | `MINIO_CONSOLE_HOST_PORT`（默认 9001） | MinIO Web 控制台，**仅排查 Milvus 对象存储** | ⭕ 可选 |

**不需对外放行**（容器内网 `rag_net` 互通）：etcd `2379`、MinIO `9000`、Milvus 内部健康端口 `9091`。

云厂商安全组 / `ufw` 示例（默认端口时）：

```bash
# 示例：ufw（按实际 MYSQL_HOST_PORT / MILVUS_HOST_PORT 替换）
sudo ufw allow ${MYSQL_HOST_PORT:-3306}/tcp
sudo ufw allow ${MILVUS_HOST_PORT:-19530}/tcp
# 可选
# sudo ufw allow ${MINIO_CONSOLE_HOST_PORT:-9001}/tcp
```

---

## 二、团队成员：本地 backend 配置

### 1. 复制并编辑 backend/.env

```bash
cd backend
cp .env.example .env
```

### 2. 必改项（连远程服务器时）

```env
# ⚠️ 改成服务器公网/局域网 IP，不是 127.0.0.1
RAG_MYSQL_HOST=203.0.113.10
RAG_MILVUS_HOST=203.0.113.10

# 端口与服务器根 .env 的 MYSQL_HOST_PORT / MILVUS_HOST_PORT 一致
RAG_MYSQL_PORT=3306
RAG_MILVUS_PORT=19530

# 与服务器根 .env 的 MYSQL_PASSWORD 一致
RAG_MYSQL_PASSWORD=你在服务器上设的用户密码
RAG_MYSQL_USER=rag_user
RAG_MYSQL_DATABASE=rag_school
```

### 3. API Key（可选，mock 默认可跑）

| 变量 | 说明 |
|------|------|
| `RAG_LLM_API_KEY` | 百炼 DashScope key；留空且 `RAG_LLM_MOCK=true` 可跑 mock |
| `RAG_EMBEDDING_API_KEY` | embedding 服务 key；mock 时可留空 |
| `RAG_RERANK_API_KEY` | 通常与 LLM 共用百炼 key |

填好真实 key 后，将对应 `RAG_*_MOCK` 改为 `false` 启用真实调用。

### 4. 根 .env 与 backend/.env 密码一致性

**一句话**：MySQL 的业务账号密码，服务器 `docker compose` 写入容器的值，必须与成员 `backend/.env` 里连接用的值**完全一致**。

| 服务器根 `.env` | 成员 `backend/.env` | 说明 |
|-----------------|---------------------|------|
| `MYSQL_USER` | `RAG_MYSQL_USER` | 必须相同 |
| `MYSQL_PASSWORD` | `RAG_MYSQL_PASSWORD` | 必须相同 |
| `MYSQL_DATABASE` | `RAG_MYSQL_DATABASE` | 必须相同 |
| `MYSQL_HOST_PORT` | `RAG_MYSQL_PORT` | 端口一致（HOST 填服务器 IP） |
| `MILVUS_HOST_PORT` | `RAG_MILVUS_PORT` | 端口一致（HOST 填服务器 IP） |
| `MYSQL_ROOT_PASSWORD` | — | 仅服务器管理用，backend **不需要** |
| `MINIO_*` | — | backend 不直连 MinIO |

---

## 三、连通性自检（配完 .env 后、启动后端前）

⚠️ **多人协作请先跑自检**，确认能连上服务器 MySQL/Milvus，再 `uvicorn`。

```bash
cd backend
# 已创建 venv 并 pip install -r requirements.txt 后：
python scripts/check_connectivity.py
```

Windows（PowerShell）：

```powershell
cd backend
.\.venv\Scripts\python scripts/check_connectivity.py
```

**期望输出**：

```
=== RAG 数据库连通性自检 ===
MySQL  203.0.113.10:3306/rag_school ... OK
Milvus 203.0.113.10:19530 ... OK
✅ 全部通过，可以启动后端: uvicorn app.main:app --reload --port 8000
```

若仍显示 `127.0.0.1` 且你实际要用远程库，脚本会打印 HOST 警告。

### 通过后再启动后端

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
curl http://127.0.0.1:8000/api/health
# mysql: true 表示 MySQL 连通（milvus 健康检查 TODO，当前可能仍为 false）
```

### 无 Python 环境时的最小探测（备选）

```bash
# MySQL（需本机有 mysql 客户端，替换 HOST/PORT/USER/PASSWORD）
mysql -h <服务器IP> -P <MYSQL_HOST_PORT> -u rag_user -p rag_school -e "SELECT 1"

# Milvus 端口是否可达（仅 TCP，不验证协议）
# Linux/macOS:
nc -zv <服务器IP> <MILVUS_HOST_PORT>
# Windows PowerShell:
Test-NetConnection <服务器IP> -Port <MILVUS_HOST_PORT>
```

---

## 四、常见坑

### ⚠️ ① init.sql 只在首次创建 volume 时执行（高频）

`docker/mysql/init.sql` 仅在 **MySQL 数据卷首次创建** 时自动导入。

- **改了表结构 / 初始化 SQL** 后，旧 volume 里的库**不会**自动更新。
- **正确做法**（会清空 MySQL 数据，生产慎用）：

```bash
docker compose down -v    # -v 删除 volume，下次 up 重新执行 init.sql
docker compose up -d
```

- 已有数据的升级应走迁移脚本，不要指望改 init.sql 自动生效。

### ② 宿主机端口被占用

修改**服务器根目录 `.env`** 中的映射，例如：

```env
MYSQL_HOST_PORT=13306
MILVUS_HOST_PORT=19531
```

然后 `docker compose up -d`，防火墙与成员 `backend/.env` 的 `RAG_MYSQL_PORT` / `RAG_MILVUS_PORT` **同步修改**。

### ③ 忘改 HOST（最高频）

| 症状 | 原因 |
|------|------|
| `Connection refused` 连 `127.0.0.1:3306` | `RAG_MYSQL_HOST` 仍为 127.0.0.1，在本机找 MySQL |
| `/api/health` → `mysql: false` | 同上，或密码/防火墙不对 |
| 自检脚本 FAIL + HOST 警告 | 未改 `RAG_MYSQL_HOST` / `RAG_MILVUS_HOST` |

**排查**：打开 `backend/.env`，确认两个 HOST 均为**服务器 IP** → 跑 `python scripts/check_connectivity.py`。

### ④ Milvus 启动慢，backend 先连失败

- Milvus 依赖 etcd + minio healthy 后才启动，healthcheck 有 **90s start_period**。
- **顺序**：服务器 `docker compose ps` 四个都 healthy → 成员跑自检 → 再起 backend。
- 若 Milvus FAIL 但容器仍 starting，等待后重跑自检。

---

## 五、快速命令索引

| 场景 | 命令 |
|------|------|
| 服务器起库 | `docker compose up -d` |
| 看健康状态 | `docker compose ps` |
| 看 Milvus 日志 | `docker compose logs milvus --tail 50` |
| 成员连通自检 | `cd backend && python scripts/check_connectivity.py` |
| 本地起后端 | `uvicorn app.main:app --reload --port 8000` |
| 重建 DB（删 volume） | `docker compose down -v && docker compose up -d` |

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-25 | 初版：远程 Docker 部署 + 团队本地连库 |
