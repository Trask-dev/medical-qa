# 医疗智能问答系统

基于 LLM + LangGraph 的 AI 健康咨询平台，采用**阶段性串行问诊架构**（安全检测 → 基础问诊 → 专家问诊 → 诊断报告）。

## 架构概览

```
safety_check → basic_interview(循环) → expert_interview(循环) → response → END
                   │                          │
              纯 prompt 模板              RAG 知识增强
              (收集基本信息)              (知识库注入追问)
```

- **安全检测**：PII 脱敏（身份证/手机号）→ 危急重症关键词过滤 → 内容合规审核。脱敏后的文本**写回** state，LLM 不会看到原始隐私数据。
- **基础问诊**：Jinja2 提示词模板驱动，选择题式交互，快速收集主诉、症状、病史。
- **专家问诊**：同步检索 pgvector 知识库（BGE-M3 嵌入），将医学知识注入 prompt 生成鉴别诊断级别的追问。
- **诊断报告**：综合对话历史 + 患者信息 + 知识库参考，生成安全合规的分析报告（含强制免责声明）。

## 鉴权

所有会话和消息端点均已接入 JWT 鉴权（`Depends(get_current_user)`）。未登录请求返回 401。

## 前端

系统提供两套前端实现：

### Vue 3 + TypeScript（主力）

```powershell
cd frontend
npm install
npm run dev        # http://localhost:5173，自动代理 /api → localhost:8000
npm run build      # 生产构建
```

- **技术栈**：Vue 3 Composition API + Pinia + TailwindCSS 3 + Lucide Icons
- **状态管理**：authStore / sessionStore / messageStore（含竞态保护）
- **组件**：AuthPage → HomePage(Sidebar + ChatView + ChatInput + EmergencyAlert + ProfileModal)
- **安全**：前端 PII 预脱敏 (`piiMasker.ts`)、DOMPurify XSS 防护、401 自动登出

### 原生 JS（兼容）

```
frontend/
├── index.html        # 入口（登录/注册 + 主应用）
├── css/style.css     # 设计系统（茄子紫主题）
└── js/
    ├── api.js        # REST API 封装
    └── app.js        # 业务逻辑（含竞态保护、PII 脱敏、AI 思考中锁定）
```

## 快速启动

```powershell
# 1. 启动数据库 (Docker pgvector)
docker start medical-pgvector

# 2. 启动后端
cd backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 3. 启动前端（Vue 开发服务器）
cd frontend
npm run dev
```

浏览器打开 http://localhost:5173（Vue）或 http://localhost:8000（后端文档）

## 环境要求

- Python 3.11+
- Node.js 18+
- Docker Desktop（`medical-pgvector` 容器：PostgreSQL + pgvector，端口 5433）

## 知识库导入

```powershell
cd backend
python scripts/load_knowledge.py ../docs/医学参考文献.json
```

## 问诊阶段配置

在 `backend/api/routers/messages.py` 的 `_detect_scenario()` 中调整：

```python
"max_rounds": 10,          # 总轮次上限
"use_expert": True,        # 是否启用专家问诊阶段
"basic_max_rounds": 5,     # 基础阶段轮次上限
```

- 基础阶段：LLM 判断信息足够（`next_action="assess"`）或达到 `basic_max_rounds` → 结束
- 专家阶段：LLM 判断信息足够或达到 `max_rounds` → 进入诊断报告
- 诊断完成后：前端自动禁用输入，提示"诊断已完成，可新建会话继续"

## 数据持久化

- **会话状态**：PostgreSQL `session_state` 表，JSONB 列（merge 写入，不丢失字段）
- **消息历史**：PostgreSQL `messages` 表，含 `options JSONB` 列（AI 选择题选项完整保留，历史回显可用）
- **用户表**：`users` 表（手机号 UNIQUE + bcrypt 密码哈希）

## 安全特性

| 层次 | 措施 |
|------|------|
| 前端输入 | `piiMasker.ts` / `maskPII()` 预脱敏（身份证/手机号） |
| 后端入口 | `safety_check_node` L0 过滤 + PII 脱敏回写 state |
| 工作流保护 | 紧急中断优先、LLM JSON 解析失败降级、Schema 校验兜底 |
| API 鉴权 | 所有会话/消息端点 JWT 认证 |
| 前端渲染 | DOMPurify 防护 v-html XSS |
| 数据完整性 | save_state merge 写入、用户消息仅在工作流成功后持久化 |
| 并发安全 | 注册 TOCTOU 单事务修复、前端 AbortController + 会话 ID 校验 |

## 项目结构

```
医疗智能问答系统/
├── backend/
│   ├── api/                          # FastAPI 路由 + Pydantic Schema
│   │   ├── routers/
│   │   │   ├── auth.py               # 登录/注册（bcrypt + JWT + 单事务注册）
│   │   │   ├── sessions.py           # 会话 CRUD
│   │   │   ├── messages.py           # 核心问诊入口
│   │   │   ├── profile.py            # 用户个人信息
│   │   │   └── safety_events.py      # 安全事件上报
│   │   ├── schemas/                  # Pydantic 请求/响应模型
│   │   └── dependencies.py           # JWT 鉴权依赖
│   ├── workflow/                     # LangGraph 工作流
│   │   ├── nodes/
│   │   │   ├── safety_check_node.py  # PII脱敏 + 红旗词 + 合规审核
│   │   │   ├── basic_interview_node.py
│   │   │   ├── expert_interview_node.py
│   │   │   ├── response_node.py
│   │   │   └── human_review_node.py
│   │   ├── state.py / graph.py / routes.py
│   │   └── diagnosis_agent.py
│   ├── knowledge/                    # pgvector + BGE-M3 混合检索
│   ├── safety/                       # pii_detector / l0_filter / content_filter
│   ├── llm/                          # DeepSeek 适配（含 ValidationError 降级）
│   ├── persistence/
│   │   ├── session_store.py          # state merge 写入 + messages CRUD
│   │   └── database.py
│   ├── prompts/                      # Jinja2 模板（basic/expert/diagnosis）
│   └── config/                       # settings.py + Pydantic Settings
├── frontend/
│   ├── src/                          # Vue 3 + TypeScript
│   │   ├── api/          (client.ts, auth.ts, messages.ts, sessions.ts, profile.ts)
│   │   ├── stores/       (authStore.ts, sessionStore.ts, messageStore.ts)
│   │   ├── types/        (api.ts, session.ts, message.ts, diagnosis.ts, sse.ts)
│   │   ├── components/
│   │   │   ├── auth/     (AuthPage.vue)
│   │   │   ├── chat/     (ChatView, ChatMessage, ChatInput, ChoiceCards, DiagnosisReport, ThinkingIndicator)
│   │   │   ├── common/   (EmergencyAlert.vue)
│   │   │   ├── layout/   (AppSidebar, AppHeader)
│   │   │   └── profile/  (ProfileModal.vue)
│   │   ├── views/        (HomePage.vue)
│   │   ├── composables/  (useScroll.ts)
│   │   └── utils/        (report.ts, date.ts, piiMasker.ts)
│   ├── js/                           # 原生 JS 前端（兼容）
│   │   ├── api.js
│   │   └── app.js
│   └── css/style.css
├── docs/
│   └── openapi.yaml                  # OpenAPI 3.0 规范
├── docker-compose.yml
├── CLAUDE.md
└── README.md
```
