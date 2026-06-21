# =============================================================================
# 问诊会话管理 API 路由层（FastAPI Router）
#
# 这个文件是AI问诊系统的"挂号处"与"病历档案室"。
# 负责会话的全生命周期管理：创建、查询、更新状态、归档删除。
#
# 包含五个核心接口：
# 1. POST   /sessions          ：新建问诊会话（相当于挂号建档）
# 2. GET    /sessions          ：分页+条件筛选会话列表
# 3. GET    /sessions/{id}     ：获取单个会话详情
# 4. PATCH  /sessions/{id}     ：更新会话状态或配置（如中途修改最大轮次）
# 5. DELETE /sessions/{id}     ：删除/归档会话
#
# ⚠️ 注意：_sessions_store 是内存字典，仅用于开发调试
#    生产环境必须替换为 Redis / PostgreSQL 等持久化存储
# =============================================================================

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.schemas.session import CreateSessionRequest, UpdateSessionRequest, SessionResponse

router = APIRouter()

# 内存级会话存储（开发用，重启即丢失，多实例不共享）
_sessions_store: dict[str, dict] = {}


@router.post("/sessions", status_code=201)
async def create_session(req: CreateSessionRequest):
    """
    创建新会话：用户发起一次新的问诊时调用。
    初始化所有会话元数据，后续消息和诊断结果都挂载在这个 session_id 下。
    """
    sid = str(uuid.uuid4())
    now = datetime.utcnow()

    session = {
        "id": sid,
        "user_id": req.user_id,
        "status": "active",             # 初始状态：进行中
        "intent": "greeting",           # 初始意图：问候/开场
        "current_stage": "init",        # 当前阶段：初始化
        "red_flag_raised": False,       # 是否触发危急重症标志
        "round_count": 0,               # 已对话轮次
        "max_rounds": req.max_rounds,   # 最大允许轮次（防止无限追问）
        "close_reason": None,           # 关闭原因（正常结束/紧急中断/超时等）
        "closed_at": None,              # 关闭时间
        "created_at": now,
        "updated_at": now,
    }

    _sessions_store[sid] = session
    return session


@router.get("/sessions")
async def list_sessions(status: str = None, user_id: str = None, limit: int = 20, offset: int = 0):
    """
    查询会话列表：支持按状态和用户ID过滤 + 分页。
    用于前端展示"我的问诊记录"或后台管理面板。
    """
    result = list(_sessions_store.values())

    # 条件过滤（内存遍历，生产环境应改为数据库WHERE子句）
    if status:
        result = [s for s in result if s.get("status") == status]
    if user_id:
        result = [s for s in result if s.get("user_id") == user_id]

    total = len(result)
    data = result[offset:offset + limit]

    return {
        "data": data,
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        },
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """
    获取单个会话详情。
    额外附加了 medical_record_summary 和 message_count 占位字段，
    生产环境应从消息表和病历表中实时聚合。
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {
        **session,
        "medical_record_summary": None,  # TODO: 从病历服务获取结构化摘要
        "message_count": 0,              # TODO: 从消息表 COUNT 获取
    }


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, req: UpdateSessionRequest):
    """
    更新会话：仅允许修改未终止的会话。
    典型场景：问诊结束后标记 completed、触发急症后标记 emergency_terminated。
    """
    session = _sessions_store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 🔒 终态保护：已结束的会话不允许再修改
    if session["status"] in ("completed", "emergency_terminated"):
        raise HTTPException(status_code=409, detail="会话已终止，不可修改")

    # 按需更新字段（PATCH 语义：只传需要改的字段）
    if req.status:
        session["status"] = req.status
    if req.max_rounds is not None:
        session["max_rounds"] = req.max_rounds

    session["updated_at"] = datetime.utcnow()
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """
    删除会话：物理删除（开发环境）。
    生产环境建议改为软删除（设置 deleted_at），保留审计痕迹。
    返回 204 No Content 表示删除成功且无响应体。
    """
    if session_id not in _sessions_store:
        raise HTTPException(status_code=404, detail="会话不存在")

    del _sessions_store[session_id]