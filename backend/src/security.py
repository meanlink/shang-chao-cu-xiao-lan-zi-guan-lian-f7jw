import base64, hashlib, hmac, json, time
from fastapi import Depends, HTTPException, Request
from .db import fetch_one
from .constants.enums import UserRole
from .config import JWT_SECRET

def password_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def issue_token(user: dict) -> str:
    payload = {"sub": user["id"], "email": user["email"], "role": user["role"], "name": user["display_name"], "exp": int(time.time()) + 86400}
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return raw + "." + sig

def current_user(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "", 1)
    if not token or "." not in token:
        raise HTTPException(401, "需要登录")
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(401, "登录凭证无效")
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if payload["exp"] < time.time(): raise ValueError()
    except Exception:
        raise HTTPException(401, "登录凭证已过期")
    user = fetch_one("SELECT id, email, display_name, role FROM users WHERE id=%s", (payload["sub"],))
    if not user: raise HTTPException(401, "用户不存在")
    return user

def require_roles(*roles):
    def dep(user=Depends(current_user)):
        if user["role"] not in [r.value if isinstance(r, UserRole) else r for r in roles]:
            raise HTTPException(403, "当前角色无权执行该操作")
        return user
    return dep
