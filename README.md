# 医疗智能问答系统

基于 LLM + LangGraph 的 AI 健康咨询平台。

## 快速启动

```powershell
# 1. 启动向量数据库 (Docker pgvector)
docker start pgvector

# 2. 启动后端
cd backend
python -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开 http://localhost:8000/docs

## 环境要求

- Python 3.11+
- Docker Desktop（pgvector 向量库）
- PostgreSQL 18（本机 5432，业务数据）
- Docker pgvector（5433，向量存储）

## 知识库导入

```powershell
cd backend
python scripts/load_knowledge.py ../docs/医学参考文献.json
```
