from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..db import fetch_one, execute
from ..security import current_user, require_roles
router = APIRouter(prefix="/reviews", tags=["reviews"])
class ReviewIn(BaseModel): decision: str; comment: str = ""
@router.post("/{rule_id}")
def review(rule_id:int,data:ReviewIn,user=Depends(require_roles("manager"))):
    if data.decision not in ('approve','reject'): raise HTTPException(400,"decision 必须为 approve 或 reject")
    rule=fetch_one("SELECT * FROM association_rules WHERE id=%s",(rule_id,))
    if not rule: raise HTTPException(404,"规则不存在")
    if rule['status'] != 'submitted': raise HTTPException(409,"只有待审核规则可审核")
    status='approved' if data.decision=='approve' else 'rejected'
    execute("UPDATE association_rules SET status=%s,reviewed_by=%s,review_comment=%s WHERE id=%s",(status,user['id'],data.comment,rule_id))
    execute("INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)",(user['id'],'review_rule','association_rule',rule_id,data.decision))
    return {"status":status}
@router.post("/{rule_id}/publish")
def publish(rule_id:int,user=Depends(require_roles("manager"))):
    rule=fetch_one("SELECT * FROM association_rules WHERE id=%s",(rule_id,))
    if not rule: raise HTTPException(404,"规则不存在")
    reasons=[]
    if rule['status'] != 'approved': reasons.append('需要先完成运营审核')
    if float(rule['support']) < 0.08: reasons.append('组合支持度低于 8%')
    if not rule['store_consistent']: reasons.append('跨门店支持度口径偏差超过 12 个百分点')
    if reasons:
        execute("UPDATE association_rules SET status='blocked',review_comment=%s WHERE id=%s",('；'.join(reasons),rule_id))
        raise HTTPException(409,"；".join(reasons))
    execute("UPDATE association_rules SET status='published',published_at=NOW() WHERE id=%s",(rule_id,))
    execute("INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)",(user['id'],'publish_rule','association_rule',rule_id,'store execution queue'))
    return {"status":"published","message":"已进入门店执行队列"}
