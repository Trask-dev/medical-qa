# 医疗智能问答系统

基于 LLM + LangGraph 的 AI 健康咨询平台，采用**阶段性串行问诊架构**（基础问诊 → 专家问诊 → 诊断报告）。

## 架构概览

```
safety_check → basic_interview(循环) → expert_interview(循环) → response → END
                   │                          │
              纯 prompt 模板              RAG 知识增强
              (收集基本信息)              (知识库注入追问)
```

- **基础问诊**：基于 Jinja2 提示词模板，快速收集主诉、症状、病史等基本信息
- **专家问诊**：同步检索 pgvector 知识库（BGE-M3 嵌入），将医学知识注入 prompt 生成鉴别诊断级别的选择题
- **诊断报告**：综合对话历史 + 患者信息 + 知识库参考，生成安全合规的分析报告

## 快速启动

```powershell
# 1. 启动数据库 (Docker pgvector)
docker start medical-pgvector

# 2. 启动后端
cd backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 http://localhost:8000/docs

## 环境要求

- Python 3.11+
- Docker Desktop（`medical-pgvector` 容器：PostgreSQL + pgvector，端口 5433，业务表+向量存储）

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

## 项目结构

```
backend/
├── api/                  # FastAPI 路由 + Pydantic Schema
├── workflow/             # LangGraph 工作流
│   ├── nodes/            # 节点实现
│   │   ├── basic_interview_node.py    # 基础问诊
│   │   ├── expert_interview_node.py   # 专家问诊（RAG）
│   │   ├── safety_check_node.py       # 安全检测
│   │   ├── response_node.py           # 回复/诊断生成
│   │   └── human_review_node.py       # 人工兜底
│   ├── state.py          # 状态定义 + Reducer
│   ├── graph.py          # Graph 编排
│   └── routes.py         # 路由决策
├── knowledge/            # RAG 知识检索（pgvector + BGE-M3）
├── safety/               # 安全护栏（PII/红旗词/内容审核）
├── llm/                  # LLM 适配层（DeepSeek）
├── config/               # 配置管理
├── persistence/          # 数据持久层
└── prompts/              # Jinja2 提示词模板
    ├── basic_consultation.j2    # 基础问诊模板
    ├── expert_consultation.j2    # 专家问诊模板（含知识库上下文）
    └── diagnosis.j2             # 诊断报告模板
```
