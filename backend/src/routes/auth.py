from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from ..db import fetch_one, execute
from ..security import password_hash, issue_token, current_user
router = APIRouter(prefix="/auth", tags=["auth"])
class LoginIn(BaseModel): email: str; password: str
@router.post("/login")
def login(data: LoginIn):
    user = fetch_one("SELECT id,email,display_name,role,password_hash FROM users WHERE email=%s", (data.email,))
    if not user or user["password_hash"] != password_hash(data.password): raise HTTPException(401, "邮箱或密码不正确")
    execute("INSERT INTO audit_logs(actor_id,action,entity_type,detail) VALUES(%s,%s,%s,%s)",(user['id'],'login','session','web login'))
    return {"token": issue_token(user), "user": {k:user[k] for k in ('id','email','display_name','role')}}
@router.get("/me")
def me(user=Depends(current_user)): return user
