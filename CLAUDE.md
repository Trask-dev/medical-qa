# Role: 资深医疗AI全栈工程师 & 系统架构师

## Core Philosophy
你正在为「医疗智能问答系统」执行 Vibe Coding。必须严格遵守 SDD → DDD → TDD 工作流，**禁止跳过任何阶段**。所有代码生成必须以《系统架构设计文档.md》为唯一真理源。

## 🏗️ 当前架构（v3.0 — 阶段性串行双通道问诊）

```
safety_check → route_by_intent → basic_interview(循环) → expert_interview(循环) → response → END

阶段1: basic_interview  — 纯 prompt 模板，选择题式交互，收集基本信息
  终止条件: LLM 判断 next_action="assess" 或 round_count >= basic_max_rounds(默认5)

阶段2: expert_interview — 同步 RAG 检索 pgvector 知识库，注入 expert_consultation.j2
  终止条件: LLM 判断 next_action="assess" 或 round_count >= max_rounds(默认10)

阶段3: response — 调用 DiagnosisAgent 综合对话历史+患者信息+知识库→诊断报告+免责声明
```

**关键配置** (`messages.py:_detect_scenario`):
- `max_rounds`: 10 (总轮次上限)
- `use_expert`: True (启用专家阶段)
- `basic_max_rounds`: 5 (基础阶段轮次上限)

## ⚠️ 安全红线（最高优先级，不可覆盖）
1.  **紧急中断优先**：检测到红旗关键词（胸痛/呼吸困难/自杀等）时，立即中断所有 Agent 链，返回急救指引，禁止继续问诊或诊断。
2.  **禁止确诊/开方**：输出中严禁出现“确诊”“一定”“保证”等表述，强制使用“可能”“建议”“倾向于考虑”。
3.  **免责声明强制附加**：所有诊断类输出末尾必须自动附加固定免责声明。
4.  **PII 脱敏前置**：用户输入进入 LangGraph 前必须完成姓名/身份证/手机号脱敏。
5.  **Schema 校验兜底**：诊断 Agent 输出未通过 JSON Schema 校验时，降级返回安全就医建议。

## 🛠️ 技术栈约束（严格限定，禁止引入未授权依赖）
| 组件         | 初期选型          | 后期演进           | 禁止替代               |
|--------------|-------------------|--------------------|------------------------|
| LLM 基座     | DeepSeek-V3       | Qwen/GPT-4o        | 禁止硬编码模型调用     |
| Agent 框架   | LangGraph         | —                  | AutoGen/CrewAI/LangChain Agent |
| Web 框架     | FastAPI           | —                  | Flask/Django/Express   |
| 向量数据库   | PostgreSQL + pgvector | —               | ChromaDB/Weaviate      |
| 业务数据库   | PostgreSQL        | —                  | SQLite/MySQL/MongoDB   |
| 缓存/状态    | Memory (内置)     | Redis              | Memcached              |
| Embedding    | 阿里 text-v3      | BGE-M3 (本地)      | OpenAI embedding       |
| 语言         | Python 3.11+      | —                  | TypeScript/JavaScript  |

## 📁 项目目录结构（权威定义，不可擅自变更）
```text
医疗智能问答系统/                    # 项目根目录
├── backend/                           # 后端服务（FastAPI + LangGraph）
│   ├── api/                           # API 层（仅负责 HTTP/SSE 接入）
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI 应用入口 + CORS + 生命周期
│   │   ├── routers/                   # 路由定义
│   │   │   ├── __init__.py
│   │   │   ├── sessions.py            # 会话创建/列表/删除
│   │   │   ├── messages.py            # 核心：SSE 流式消息入口
│   │   │   └── safety_events.py       # 安全事件上报（前端触发）
│   │   └── schemas/                   # Pydantic 请求/响应模型
│   │       ├── __init__.py
│   │       ├── session.py
│   │       ├── message.py             # 含 SSE 事件 payload 定义
│   │       └── safety.py
│   ├── workflow/                      # 🌟 核心工作流层（Agent 逻辑归于此）
│   │   ├── __init__.py
│   │   ├── state.py                   # MedicalQAState TypedDict + Reducer (dict_merge)
│   │   ├── graph.py                   # StateGraph 构建：safety→basic→expert→response
│   │   ├── routes.py                  # 条件边路由：route_by_intent / check_basic_complete / check_expert_complete
│   │   ├── diagnosis_agent.py         # 诊断报告生成 Agent
│   │   └── nodes/                     # 每个文件 = StateGraph 一个节点
│   │       ├── __init__.py
│   │       ├── _shared.py             # 共享工具：msg_role/msg_content/format_knowledge_context
│   │       ├── basic_interview_node.py  # 阶段1：基础问诊（纯 prompt 模板，选择题式交互）
│   │       ├── expert_interview_node.py # 阶段2：专家问诊（同步 RAG 检索 → 知识注入 prompt）
│   │       ├── safety_check_node.py   # PII脱敏 + 红旗词检测 + 内容审核
│   │       ├── response_node.py       # 阶段3：生成最终回复/诊断报告（含免责声明）
│   │       └── human_review_node.py   # 人工中断点（断点续传）
│   ├── knowledge/                     # 知识检索层
│   │   ├── __init__.py
│   │   ├── retriever.py               # 混合检索（向量+关键词）
│   │   ├── vector_store.py            # PostgreSQL + pgvector 向量存储
│   │   └── kb_loader.py               # 知识库导入/更新工具
│   ├── safety/                        # 安全护栏层（被 nodes/safety_check_node 调用）
│   │   ├── __init__.py
│   │   ├── pii_detector.py            # 患者隐私识别与脱敏
│   │   ├── red_flag_detector.py       # 危急重症关键词检测
│   │   └── content_filter.py          # 输出合规性校验
│   ├── persistence/                   # 数据持久层（精简版，聚焦合规）
│   │   ├── __init__.py
│   │   ├── database.py                # DB 连接 + LangGraph Checkpointer 配置
│   │   └── models/                    # SQLAlchemy ORM（仅合规必需表）
│   │       ├── __init__.py
│   │       ├── audit_log.py           # 操作审计日志（强制留存）
│   │       └── medical_record.py      # 最终问诊报告归档
│   ├── llm/                           # LLM 适配层
│   │   ├── __init__.py
│   │   ├── adapter.py                 # 统一多模型接口（抽象）
│   │   ├── real_llm_adapter.py        # DeepSeek 实现：RealLLMAdapter/RealL2Adapter/RealRouterLLM
│   │   └── streaming.py               # 流式输出标准化处理
│   ├── prompts/                       # Jinja2 提示词模板
│   │   ├── basic_consultation.j2     # 基础问诊模板（选择题式）
│   │   ├── expert_consultation.j2     # 专家问诊模板（含 {{ knowledge_context }} 区块）
│   │   └── diagnosis.j2               # 诊断报告模板
│   ├── config/                        # 配置管理
│   │   ├── __init__.py
│   │   ├── settings.py                # Pydantic Settings（环境变量绑定）
│   │   ├── llm.yaml                   # 模型参数 + 密钥引用
│   │   └── safety_rules.yaml          # 安全规则阈值配置
│   ├── scripts/                       # 运维脚本
│   │   ├── init_db.py                 # 初始化审计表 + 知识库
│   │   └── load_knowledge.py          # 批量导入医学文献
│   ├── tests/                         # 测试（按节点粒度组织）
│   │   ├── __init__.py
│   │   ├── unit_nodes/                # 单节点测试（TDD 核心）
│   │   │   ├── test_safety_check.py
│   │   │   └── test_interview.py
│   │   ├── integration/               # 工作流集成测试
│   │   └── e2e/                       # 端到端 SSE 流测试
│   ├── .env.example                   # 环境变量模板
│   ├── requirements.txt               # Python 依赖
│   └── Dockerfile                     # 后端容器化
├── frontend/                          # 前端应用（Vue3/React + Vite）
│   ├── public/
│   │   └── index.html
│   ├── src/
│   │   ├── components/                # UI 组件
│   │   │   ├── ChatMessage.vue        # 消息气泡（支持流式渲染）
│   │   │   ├── EmergencyAlert.vue     # 紧急告警弹窗
│   │   │   ├── HumanReviewPanel.vue   # 人工审核面板
│   │   │   └── SessionSidebar.vue     # 会话列表侧边栏
│   │   ├── views/                     # 页面视图
│   │   │   ├── ChatPage.vue           # 主问诊页（SSE 消费核心）
│   │   │   ├── HistoryPage.vue        # 历史记录
│   │   │   └── ReportPage.vue         # 报告详情页
│   │   ├── stores/                    # Pinia/Zustand 状态管理
│   │   │   ├── sessionStore.ts
│   │   │   ├── messageStore.ts        # 管理流式消息拼接
│   │   │   └── safetyStore.ts         # 本地安全状态（如输入预警）
│   │   ├── api/                       # API 封装
│   │   │   ├── sessionApi.ts
│   │   │   ├── messageApi.ts          # 含 SSE 订阅逻辑
│   │   │   └── safetyApi.ts
│   │   ├── utils/
│   │   │   ├── sseHandler.ts          # SSE 事件解析 + 重连
│   │   │   ├── piiMasker.ts           # 前端输入预脱敏
│   │   │   └── markdownRenderer.ts    # 医疗内容安全渲染
│   │   ├── types/                     # TS 类型（与后端 schemas 对齐）
│   │   │   ├── session.ts
│   │   │   ├── message.ts
│   │   │   └── sseEvent.ts            # SSE 事件类型定义
│   │   ├── App.vue
│   │   ├── main.ts
│   │   └── styles/
│   │       └── global.css
│   ├── .env.example
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── docs/                              # 🌟 运行时契约文档（替代传统 SDD）
├── docker-compose.yml                 # 一键启动：backend + frontend + db + vectorstore
├── nginx.conf                         # 生产环境反向代理 + SSE 缓冲关闭
├── CLAUDE.md                          # 👈 本文件即为 AI 协作的唯一权威指令集
└── README.md