# 医疗智能问答系统 — 关键设计决策记录 (ADR)

> **版本：** v1.0
> **日期：** 2026-06-19
> **状态：** 持续更新

---

## 决策索引

| 编号 | 决策 | 状态 | 日期 |
|------|------|------|------|
| ADR-001 | LangGraph 作为 Agent 编排框架 | ✅ 已确认 | 2026-06-19 |
| ADR-002 | Master-Agent 集中路由模式 | ✅ 已确认 | 2026-06-19 |
| ADR-003 | 黑板模式 Agent 间通信 | ✅ 已确认 | 2026-06-19 |
| ADR-004 | 问诊与搜索异步并行 | ✅ 已确认 | 2026-06-19 |
| ADR-005 | Milvus Lite → Distributed 渐进路径 | ✅ 已确认 | 2026-06-19 |
| ADR-006 | JSONB 存储结构化病历与诊断 | ✅ 已确认 | 2026-06-19 |
| ADR-007 | PII 双轨存储策略 | ✅ 已确认 | 2026-06-19 |
| ADR-008 | 审计日志按月分区 | ✅ 已确认 | 2026-06-19 |
| ADR-009 | SSE 流式输出 + next_action 状态机 | ✅ 已确认 | 2026-06-19 |
| ADR-010 | pgvector 双轨并行策略 | ✅ 已确认 | 2026-06-19 |
| ADR-011 | LLM 适配层无代码切换 | ✅ 已确认 | 2026-06-19 |
| ADR-012 | 问诊核心字段终止条件 | 🔶 待确认 | 2026-06-19 |

---

## ADR-001: LangGraph 作为 Agent 编排框架

### 状态
✅ 已确认

### 背景
需要选择一个 Agent 编排框架来管理多智能体间的状态流转、条件路由和循环调用。

### 决策
采用 **LangGraph** 作为唯一 Agent 编排框架。

### 理由
1. 原生支持有状态循环工作流（StateGraph），天然契合问诊的多轮循环模式
2. 内置 Checkpoint 机制支持断线恢复
3. LangChain 生态活跃，社区支持好
4. 条件边（conditional edges）原生支持 MasterAgent 的路由分发需求

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| 自研 FSM | 开发成本高，状态持久化需自行实现 |
| Temporal | 过重，面向长时间运行的 Saga，不适合对话级编排 |
| AutoGen | 被 CLAUDE.md 明确禁止 |
| CrewAI | 被 CLAUDE.md 明确禁止 |

### 影响
- 所有 Agent 必须遵循 LangGraph StateGraph 节点接口规范
- 状态管理依赖 LangGraph Memory / Checkpointer

---

## ADR-002: Master-Agent 集中路由模式

### 状态
✅ 已确认

### 背景
多 Agent 系统中存在两种主流通信模式：点对点直连 vs 中心路由。需要确定本系统的 Agent 间调度方式。

### 决策
采用 **MasterAgent 集中路由**，所有用户输入先经过 MasterAgent 做意图识别和安全检查，再分发到专业 Agent。

### 理由
1. 统一的安全拦截点——红旗检测只需在一处执行
2. 意图识别集中在 MasterAgent，专业 Agent 无需关心路由逻辑
3. 便于审计——每次路由决策都有明确日志
4. 符合 SRP 原则

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| Agent 点对点直连 | 安全拦截点分散，容易出现绕过漏洞 |
| 消息队列全广播 | 无法控制消息到达顺序和消费 |

### 影响
- MasterAgent 成为单点瓶颈（需要高性能实现 + 冗余部署）
- 新增 Agent 时需修改 MasterAgent 路由表

---

## ADR-003: 黑板模式 Agent 间通信

### 状态
✅ 已确认

### 背景
Agent 间需要共享问诊进度、检索结果等上下文。需要确定共享方式。

### 决策
通过 **LangGraph State（黑板模式）** 共享上下文，**禁止 Agent 间直接调用**。

### 理由
1. Agent 完全解耦——每个 Agent 只读写 State，不感知其他 Agent 存在
2. State 变更可追溯——每次写入都有 LangGraph Checkpoint
3. 新增 Agent 只需声明对 State 的读/写权限，不影响现有 Agent
4. 安全审计友好——State 变化可完整回放

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| Agent 间直接函数调用 | 强耦合，新增 Agent 需要改多个文件 |
| 独立消息队列 | 引入额外组件，初期过度设计 |

### 影响
- State 结构必须事先明确定义（TypedDict）
- 需明确定义每个 Agent 的读写权限矩阵

---

## ADR-004: 问诊与搜索异步并行

### 状态
✅ 已确认

### 背景
问诊阶段需要同步与用户交互，同时后台需要检索医学知识。需要确定两者的执行时序。

### 决策
**问诊与搜索并行执行**，搜索Agent 在后台异步运行，不阻塞用户对话主线程。诊断Agent 等待两者结果后串行执行。

### 理由
1. 用户感知延迟最小化——搜索对用户透明
2. 搜索可利用问诊间隙提前缓存相关知识
3. 诊断阶段拥有最新的病历+知识数据

### 影响
- 搜索Agent 必须异步化实现
- 诊断Agent 的启动条件：问诊完成 AND 搜索累积结果可用
- 需要处理搜索超时或失败的降级策略

---

## ADR-005: Milvus Lite → Distributed 渐进路径

### 状态
✅ 已确认

### 背景
需要选择向量数据库来存储医学知识嵌入向量。

### 决策
初期使用 **Milvus Lite**（pip install 嵌入模式），中期可无缝升级到 Milvus Standalone，大规模生产切换到 Milvus Distributed。

### 理由
1. 零配置启动——开发环境无需额外服务
2. 与分布式版 API 兼容——代码无需修改
3. 中文社区活跃，医疗领域有成熟案例

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| ChromaDB | 被 CLAUDE.md 明确禁止 |
| Pgvector（独用） | 单表 >10M 向量时性能不如 Milvus |
| Pinecone | 商业闭源，数据不能本地化 |

### 影响
- 开发环境：Milvus Lite 嵌入进程
- 生产环境：独立 Milvus 服务 + gRPC 通信

---

## ADR-006: JSONB 存储结构化病历与诊断

### 状态
✅ 已确认

### 背景
结构化病历（MedicalRecord）和诊断报告（DiagnosisResult）的字段因症状和诊断类型差异大，需要确定存储方式。

### 决策
使用 PostgreSQL **JSONB** 类型存储 `record_data` 和 `result_data`，配合 GIN 索引和 JSON Schema 校验。

### 理由
1. Schema 灵活——不同症状的病历字段不同（头痛问部位、发烧不问）
2. 诊断报告嵌套深（鉴别诊断数组、引用数组），关系建模过度复杂
3. PostgreSQL JSONB 支持索引（GIN）、路径查询（->/->>）、包含查询（@>）
4. 单字段存储避免 N 个稀疏 NULL 列

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| EAV 模式 | 查询复杂，性能差 |
| 纯关系列 | 字段稀疏，Schema 变更频繁 |
| MongoDB | 额外组件，ACID 不如 PostgreSQL |

### 影响
- 病历和诊断的 JSON Schema 版本化至关重要
- 需要 GIN 索引优化 JSONB 查询性能

---

## ADR-007: PII 双轨存储策略

### 状态
✅ 已确认

### 背景
安全红线要求"PII 脱敏前置"，但审计追溯又需要原始数据。需要平衡安全与合规。

### 决策
`messages` 表采用 **双轨存储**：
- `content`（TEXT 明文）：存储脱敏后文本，永久保留
- `content_raw_encrypted`（BYTEA）：AES-256-GCM 加密原始输入，**30 天自动清除**

### 理由
1. 满足"脱敏前置"红线——content 字段始终是安全可展示的
2. 满足审计追溯——30 天内可解密原始输入进行合规审查
3. 最小化隐私风险——30 天后原始数据不可恢复
4. 加密密钥不存储在数据库中

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| 只存脱敏文本 | 无法审计追溯原始输入 |
| 明文存储原始输入 | 严重违反 PII 红线 |
| 永久加密存储 | 隐私最小化原则不满足 |

### 影响
- 需要定时任务调用 `purge_message_raw_content()`
- 解密函数权限严格限制（仅安全审计角色）

---

## ADR-008: 审计日志按月分区

### 状态
✅ 已确认

### 背景
审计日志表（audit_logs）预计增长最快（每次 Agent 调用一条记录），需要分区策略。

### 决策
`audit_logs` 表使用 PostgreSQL **RANGE 分区，按月划分**，主键改为 `(created_at, id)`。

### 理由
1. audit_logs 增长最快（每次 Agent 调用一条，预估 500K→50M）
2. 按月分区查询时可以分区裁剪，性能优化显著
3. 旧分区可以独立归档/删除
4. PostgreSQL 16 原生支持，无需额外组件

### 影响
- 主键从单列 `id` 变为复合 `(created_at, id)`
- 需要自动化脚本按月创建新分区
- 跨月查询可能涉及多分区

---

## ADR-009: SSE 流式输出 + next_action 状态机

### 状态
✅ 已确认

### 背景
需要确定前端如何获取 Agent 处理结果：轮询 vs WebSocket vs SSE。

### 决策
采用 **SSE (Server-Sent Events)** + `POST /messages` 返回 `next_action` 状态机。

### 理由
1. 单向推送够用——服务器→客户端推送，无需双向
2. 浏览器原生支持 EventSource API，无需额外库
3. HTTP 协议兼容性好，Nginx 代理无需特殊配置（但需关闭缓冲）
4. `next_action` 让客户端明确知道下一步行为（连接SSE/展示报告/锁定界面）

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| 轮询 | 延迟大，服务器压力大 |
| WebSocket | 双向通信对本系统过度，Nginx 配置复杂 |

### 影响
- Nginx 配置需 `proxy_buffering off` 以确保 SSE 实时推送
- 客户端需实现 EventSource 事件监听和重连逻辑

---

## ADR-010: pgvector 双轨并行策略

### 状态
✅ 已确认

### 背景
主向量检索引擎是 Milvus，但开发环境和生产环境的需求不同。

### 决策
`knowledge_entries` 表同时保留 **pgvector embedding 列**（向量维度预留 2000），与 Milvus 形成双轨：
- 开发/测试环境：直接使用 pgvector 检索，无需部署 Milvus
- 生产环境：Milvus 主力检索，pgvector 作为降级方案

### 理由
1. 开发环境零依赖——pgvector 随 PostgreSQL 安装
2. 生产降级保障——Milvus 故障时可切到 pgvector
3. 向量维度预留 2000——兼容 text-embedding-v3 (1536) 和 BGE-M3 (1024)

### 替代方案
| 方案 | 拒绝理由 |
|------|---------|
| 只用 Milvus | 开发环境需额外部署 |
| 只用 pgvector | 大规模检索性能不如 Milvus |

### 影响
- 向量索引策略分阶段：<10K 暴力搜索，10K-100K IVFFlat，>100K HNSW
- 同步逻辑：Milvus 写入后更新 `embedding_id` 字段

---

## ADR-011: LLM 适配层无代码切换

### 状态
✅ 已确认

### 背景
技术支持多种 LLM 模型（DeepSeek-V3 → Qwen-Max → GPT-4o），需要无代码切换。

### 决策
设计 **LLMAdapter 抽象层**，通过 YAML 配置文件（`config/llm.yaml`）切换模型提供方，对上游 Agent 完全透明。

### 理由
1. 满足 PRD "模型配置化" 需求
2. 统一 `chat()` 和 `stream_chat()` 接口，Agent 层无感知
3. YAML 配置文件支持环境变量引用（`${DEEPSEEK_API_KEY}`）
4. 便于 A/B 测试不同模型效果

### 影响
- 配置文件变更后无需重启（热加载或重启即可）
- 适配器需处理不同模型的 token 计数差异

---

## ADR-012: 问诊核心字段终止条件

### 状态
🔶 待确认

### 背景
架构文档 §4.3.3 规定终止条件为"核心字段采集完成 OR 轮次≥5轮 OR 用户主动结束"，但"核心字段"未精确定义。

### 当前方案
SDD-01 §2.3 定义了 7 个 REQUIRED_CORE 字段，分三级优先级：
- **P0（不可缺失）**：chief_complaint、complaint_duration、complaint_location
- **P1（允许缺失，默认值）**：severity、age、accompanying_symptoms
- **P2（允许空数组）**：chronic_diseases、drug_allergies

### 待确认
1. P0/P1/P2 优先级划分需要医学顾问确认
2. 全身性症状（如"全身乏力"）的 complaint_location 是否应标记为可选
3. 是否增加"患者主动结束"作为提前终止条件

### 风险
若核心字段定义不合理，可能导致问诊过短（信息不足）或过长（用户流失）。

---

## 附录：决策追溯矩阵

| 决策 | 来源文档 | 影响范围 |
|------|---------|---------|
| ADR-001 | 系统架构设计文档 §2.2 ADR-001 | workflow/graph.py |
| ADR-002 | 系统架构设计文档 §2.2 ADR-002 | workflow/routes.py |
| ADR-003 | 系统架构设计文档 §2.2 ADR-003 | workflow/state.py |
| ADR-004 | 系统架构设计文档 §2.2 ADR-004 | workflow/graph.py, workflow/nodes/search_node.py |
| ADR-005 | 系统架构设计文档 §2.2 ADR-005 | knowledge/vector_store.py |
| ADR-006 | SDD-02-数据库Schema设计 §7 决策1 | persistence/models/, schema.sql |
| ADR-007 | SDD-02 §6.1, SDD-01 §2.2 | schema.sql (messages 表) |
| ADR-008 | SDD-02 §7 决策3 | schema.sql (audit_logs 表) |
| ADR-009 | SDD-03-API契约设计 §4.3 | api/routers/messages.py, api/schemas/message.py |
| ADR-010 | SDD-02 §7 决策2 | knowledge/vector_store.py, schema.sql |
| ADR-011 | 系统架构设计文档 §9.2, §12.2 | llm/adapter.py, config/llm.yaml |
| ADR-012 | SDD-01 §6 D1 | workflow/nodes/interview_node.py |

---

> **文档维护者：** 开发团队
> **最后更新：** 2026-06-19
> **更新规则：** 每项决策确认或变更时，更新状态并追加日期
