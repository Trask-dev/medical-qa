"""认证路由：注册 + 登录"""
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
import bcrypt
from jose import jwt
from sqlalchemy import text

from persistence.database import _get_engine
from api.schemas.auth import RegisterRequest, LoginRequest, TokenResponse

router = APIRouter()

import os
SECRET_KEY = os.getenv("JWT_SECRET", "change-me-to-a-random-secret-in-env")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 72


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


@router.post("/auth/register", status_code=201)
async def register(req: RegisterRequest):
    """用户注册"""
    engine = _get_engine()

    # 手机号已存在？
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id FROM users WHERE phone = :phone"),
            {"phone": req.phone},
        )
        if result.fetchone():
            raise HTTPException(status_code=409, detail="该手机号已注册")

    # 创建用户
    user_id = str(uuid.uuid4())
    password_hash = _hash_password(req.password)
    async with engine.begin() as conn:
        await conn.execute(
            text("""
                INSERT INTO users (id, phone, password_hash, nickname)
                VALUES (:id, :phone, :hash, :nickname)
            """),
            {"id": user_id, "phone": req.phone, "hash": password_hash, "nickname": req.nickname},
        )

    # 签发 token
    token = _create_token(user_id, req.phone)
    return TokenResponse(access_token=token, user_id=user_id, nickname=req.nickname)


@router.post("/auth/login")
async def login(req: LoginRequest):
    """用户登录"""
    engine = _get_engine()

    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT id, phone, password_hash, nickname FROM users WHERE phone = :phone"),
            {"phone": req.phone},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="手机号或密码错误")
        if not _verify_password(req.password, row[2]):
            raise HTTPException(status_code=401, detail="手机号或密码错误")

    token = _create_token(str(row[0]), row[1])
    return TokenResponse(access_token=token, user_id=str(row[0]), nickname=row[3])


def _create_token(user_id: str, phone: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "phone": phone, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
