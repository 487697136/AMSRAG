# AMSRAG Web

AMSRAG Web 是 AMSRAG 检索与知识图谱能力的 Web 应用层，包含：

- `backend/`：FastAPI 后端
- `frontend/`：Vue 3 + Vite 前端
- `data/`：本地数据库、上传文件与 RAG 运行时目录
- `logs/`：运行日志

当前版本在原项目基础上完成了以下增强：

- 新知识库的上传、处理、图谱读取、问答、删除、重建形成完整闭环
- Neo4j 写入改为按 `namespace + id` 合并，降低实体类型漂移导致的重复节点风险
- 图谱接口支持 `Neo4j -> GraphML` 回退，并显式返回来源状态
- 文档和知识库新增重试、重建、清理运行时能力
- 删除文档 / 删除知识库时同步清理运行时数据，而不是只删业务记录
- 前端图谱、知识库、文档、设置、会话、聊天页面统一为现代化控制台风格

## 目录结构

```text
amsrag-web/
  backend/                FastAPI service
  frontend/               Vue 3 + Vite client
  data/                   SQLite、上传文件、RAG 工作目录
  logs/                   运行日志
  install.bat             安装依赖
  quick-start.bat         一键启动前后端
  start-all.bat           quick-start.bat 别名
  README_FIXES.md         本次修复摘要
  ACCEPTANCE_CHECKLIST.md 手工验收清单
```

## 运行前提

- Windows 10/11
- Node.js 16+
- npm
- Python 3.10+ 或 Conda
- 推荐 Conda 环境：`pytorch_new`
- 若启用 Neo4j，请准备 Aura 或自建 Neo4j 连接信息

## 关键环境变量

后端从 `backend/.env` 读取配置。常用项如下：

```env
DEBUG=false
BACKEND_CORS_ORIGINS=http://localhost:3000,http://localhost:5173

RAG_BEST_MODEL=qwen-plus
RAG_CHEAP_MODEL=qwen-flash
RAG_ENTITY_EXTRACTION_MODEL=qwen-flash
RAG_GRAPH_BACKEND=networkx

NEO4J_URL=
NEO4J_USERNAME=
NEO4J_PASSWORD=

MAX_UPLOAD_SIZE=52428800
ALLOWED_EXTENSIONS=.txt,.md,.json,.csv
```

说明：

- 默认 `RAG_GRAPH_BACKEND=networkx`：本地 NetworkX 图存储（功能完整，不依赖 Neo4j 插件）。
- 需要 Neo4j 时设置 `RAG_GRAPH_BACKEND=neo4j`：后端会尝试使用 Neo4j 图存储；若连接不可用会自动回退到 NetworkX。
- 若 Neo4j 读取失败且本地存在 GraphML 缓存，图谱接口会自动回退。
- DashScope 和 SiliconFlow API Key 由前端“系统设置”页面保存到数据库，不建议写入 `.env`。

## 安装依赖

在 `amsrag-web/` 目录执行：

```bat
install.bat
```

## 启动方式

### 方式一：一键启动

在 `amsrag-web/` 目录执行：

```bat
quick-start.bat
```

或：

```bat
start-all.bat
```

启动后默认地址：

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`
- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/health`

### 方式二：分别启动

后端：

```bat
cd backend
start.bat
```

前端：

```bat
cd frontend
start.bat
```

## 当前已完成的核心闭环

### 1. 文档生命周期

- 上传文档后进入后台处理
- 处理失败时保留可读错误信息
- 支持失败文档重新处理
- 删除文档时同步处理 RAG 运行时数据

### 2. 知识库生命周期

- 支持新建、更新、删除知识库
- 支持“重建知识库运行时数据”
- 支持“清理知识库运行时数据”
- 删除知识库时同步清理 Neo4j / GraphML / FAISS / 缓存服务实例

### 3. 图谱状态语义

图谱接口和统计接口会显式返回：

- `graph_source`：`neo4j` / `graphml` / `memory` / `none`
- `graph_backend_status`：`ready` / `fallback` / `error`
- `fallback_reason`
- `last_error`

### 4. Neo4j 集成

- 启动和运行时都支持 Neo4j 连接验证
- 新知识库写入链路已按 Neo4j 方式构建
- 若 Aura 抖动或图数据缺失，前端会收到明确状态而不是只看到泛化失败提示

## 推荐验收顺序

请优先按以下顺序验证：

1. 启动前后端，确认 `/health` 返回 200。
2. 登录系统后，在“系统设置”中保存 DashScope 和 SiliconFlow API Key。
3. 在 `backend/.env` 中启用 `RAG_GRAPH_BACKEND=neo4j` 并配置 Neo4j 连接。
4. 新建一个空知识库。
5. 上传一个 UTF-8 编码的 `.txt` 或 `.md` 文件。
6. 等待文档状态变为“已完成”。
7. 打开知识图谱页面，确认显示 `Neo4j 实时图谱` 或明确的回退来源。
8. 在智能问答页面基于该知识库发起问答。
9. 删除文档，确认图谱和统计同步变化。
10. 使用“重建知识库”再次恢复运行时数据。
11. 删除知识库，确认业务记录和运行时数据同步删除。

更细的步骤见 [ACCEPTANCE_CHECKLIST.md](./ACCEPTANCE_CHECKLIST.md)。

## 常见故障排查

### 1. 图谱页显示回退到本地历史缓存

说明：
当前知识库在 Neo4j 中没有可读取的图数据，或 Aura 读取失败，但本地仍有 GraphML 缓存可展示。

检查项：

- 是否为旧知识库
- Neo4j URL / 用户名 / 密码是否正确
- 新上传文档是否真的处理完成
- 后端日志中是否有 `UnknownLabelWarning` 或连接重置

### 2. 上传后文档一直处于处理中

检查项：

- “系统设置”中的 DashScope / SiliconFlow Key 是否已保存
- 后端日志是否有实体抽取或 Neo4j 写入错误
- 上传文件是否为 UTF-8 编码

### 3. 图谱页提示 Neo4j 连接异常

检查项：

- `backend/.env` 中 `RAG_GRAPH_BACKEND` 是否为 `neo4j`
- `NEO4J_URL / NEO4J_USERNAME / NEO4J_PASSWORD` 是否完整
- Aura 是否存在瞬时网络抖动

### 4. 后端启动时报缺包

`backend/start.bat` 会自动检查并安装常见依赖。若仍失败，请手动执行：

```bat
cd backend
python -m pip install -r requirements.txt
```

## 已知边界

- 旧知识库不会自动迁移到 Neo4j；当前策略是兼容显示旧 GraphML 缓存。
- Neo4j Aura 在短时间高并发下仍可能出现瞬时连接抖动，但当前版本已增加更稳妥的回退与重建路径。
- 当前交付目标是“本地稳定运行 + 可手工验收”，不是线上生产部署方案。

## 相关文档

- [README_FIXES.md](./README_FIXES.md)
- [ACCEPTANCE_CHECKLIST.md](./ACCEPTANCE_CHECKLIST.md)
- [backend/start.bat](./backend/start.bat)
- [frontend/start.bat](./frontend/start.bat)