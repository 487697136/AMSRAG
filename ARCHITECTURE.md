# AMSRAG（知源智答）架构设计与技术栈

基于项目代码与系统架构图的综合分析。

---

## 整体分层架构

项目采用**四层垂直分层 + 右侧运维支撑**的设计，两大核心流水线贯穿其中。

![系统分层架构](docs/images/system-architecture.png)

---

## 一、用户接入层（前端）

技术栈：Vue 3 + Vite + Pinia + Naive UI + ECharts + Axios

- Vue 3 构建多页面 SPA，Pinia 管理全局状态（会话、知识库等）
- Naive UI 作为组件库，ECharts（via vue-echarts）实现知识图谱可视化
- Marked + DOMPurify 做 Markdown 渲染与 XSS 防护
- 通信协议：HTTP 请求 + Server-Sent Events（SSE）实现流式回答输出

---

## 二、服务接入层（API 网关）

技术栈：FastAPI + Uvicorn + python-jose/JWT + Pydantic

- FastAPI 提供版本化 RESTful 接口（/api/v1/...），Uvicorn 作为 ASGI 服务器
- python-jose + passlib/bcrypt 实现 OAuth2 Bearer Token / JWT 认证授权
- Pydantic v2 做请求体契约校验与数据建模
- CORS 安全中间件由 FastAPI 内置中间件处理

---

## 三、业务逻辑层（核心服务）

技术栈：FastAPI Services + SQLAlchemy + SQLite + asyncio

模块                  实现
--------------------  --------------------------------------------------------
账户与权限            SQLAlchemy ORM + SQLite（amsrag_web.db），用户/API Key 管理
知识库管理            知识库元数据持久化，工作区文件系统隔离（rag_workspaces/user_N/）
会话与记忆            conversation_service + memory_service，历史轮次持久化与重构
文档解析              pdfplumber（PDF）、python-docx（Word）、openpyxl（Excel）
知识问答编排          rag_service 调度 AMSRAG 核心引擎，管理检索→生成全流程
运行时管理            runtime_service 负责异步任务调度与错误监控

---

## 四、知识处理与推理引擎层（核心创新）

这是项目的核心，分两条流水线：

### 索引构建流水线（Indexing Pipeline）

技术栈：Transformers + NetworkX + FlagEmbedding + FAISS/HNSWLib + BM25

文档
  → 知识切分（token/separator chunker）
  → 实体与关系抽取（LLM 驱动，OpenAI/Azure/Qwen）
  → 知识图谱构建（NetworkX）+ 社区分析（Louvain 社区检测）
  → 语义向量索引（FAISS / HNSWLib）+ 关键词倒排索引（BM25）

### 查询推理流水线（Query Reasoning Pipeline）—— 核心亮点

技术栈：ModernBERT + asyncio + scipy/scikit-learn

用户问题
  → 问题复杂度分类与路由（ModernBERT 分类器，本地推理）
  → 多源并行检索执行（向量检索 + BM25 + 图检索，异步并发）
  → 检索结果融合与重排（ConfidenceAwareFusion，RRF 算法）
  → 答案生成与后处理（LLM API 调用，SSE 流式输出）

复杂度路由是本项目最核心的创新点：基于本地部署的 ModernBERT-large fine-tune 分类器，
将查询自动路由至 local（实体局部）、global（社区全局）、hybrid（混合）、naive（直接检索）四种策略。

下图概括查询侧的复杂度分类、路由、多源检索、融合与答案生成关系（与实现模块对应，细节以代码为准）。

![查询推理与核心算法流程](docs/images/query-pipeline-framework.png)

---

## 五、存储与外部服务层

类型                  技术
--------------------  --------------------------------------------------------
关系型元数据库        SQLite（开发）/ 可扩展至 PostgreSQL
向量检索数据库        FAISS（大规模）/ HNSWLib（高速近似）/ NanoVectorDB（轻量）
关键词索引存储        BM25（bm25.py 自实现）
知识图谱数据库        NetworkX（本地）/ Neo4j（生产级图数据库）
文档与中间结果        JSON KV Storage（kv_json.py）
文本嵌入服务          OpenAI Embedding / FlagEmbedding（BGE 本地）/ SiliconFlow / Amazon Bedrock
大语言模型服务        OpenAI GPT-4o / Azure OpenAI / Qwen（通义千问）/ Amazon Bedrock

---

## 技术栈总结

层次                  核心技术
--------------------  --------------------------------------------------------
前端                  Vue 3 · Vite · Pinia · Naive UI · ECharts · SSE
后端网关              FastAPI · Uvicorn · JWT · Pydantic v2
业务层                SQLAlchemy · SQLite · aiofiles · loguru
核心引擎              PyTorch · Transformers · ModernBERT · FlagEmbedding · NetworkX
存储                  FAISS · HNSWLib · BM25 · Neo4j · JSON KV
外部 LLM              OpenAI / Azure / Qwen / Bedrock / SiliconFlow
评估                  ROUGE · BLEU · BERTScore · sacrebleu

整体设计以"复杂度感知的自适应多策略 GraphRAG"为核心，
通过本地轻量分类器替代 LLM 路由判断，在保持高性能的同时降低延迟与成本。
