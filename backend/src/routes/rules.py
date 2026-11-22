from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from ..db import fetch_all, fetch_one, execute
from ..security import current_user, require_roles
from ..services.association import apriori
router = APIRouter(prefix="/rules", tags=["rules"])
class RunIn(BaseModel): min_support: float = Field(0.08, ge=0.01, le=1); min_confidence: float = Field(0.25, ge=0.01, le=1)

def list_transactions():
    rows = fetch_all("SELECT o.id, f.name FROM basket_orders o JOIN basket_items i ON i.order_id=o.id JOIN products p ON p.id=i.product_id JOIN product_families f ON f.id=p.family_id ORDER BY o.id")
    grouped={}
    for r in rows: grouped.setdefault(r['id'],set()).add(r['name'])
    return list(grouped.values())
@router.get("")
def rules(user=Depends(current_user)):
    return fetch_all("SELECT r.*, u.display_name created_by_name, m.display_name reviewed_by_name FROM association_rules r JOIN users u ON u.id=r.created_by LEFT JOIN users m ON m.id=r.reviewed_by ORDER BY r.id DESC")
@router.post("/run")
def run(data: RunIn, user=Depends(require_roles("analyst"))):
    transactions = list_transactions(); results = apriori(transactions,data.min_support,data.min_confidence)
    run_key = f"run-{len(transactions)}-{int(data.min_support*1000)}-{int(data.min_confidence*1000)}"
    if not fetch_one("SELECT id FROM analysis_runs WHERE run_key=%s",(run_key,)):
        run_id=execute("INSERT INTO analysis_runs(run_key,min_support,min_confidence,basket_count,rule_count,created_by) VALUES(%s,%s,%s,%s,%s,%s)",(run_key,data.min_support,data.min_confidence,len(transactions),len(results),user['id']))
        for item in results[:12]:
            antecedent = " + ".join(item['antecedent']); consequent = " + ".join(item['consequent'])
            consistent = int(item['support'] >= 0.08)
            status = "draft" if consistent else "blocked"
            execute("INSERT INTO association_rules(antecedent,consequent,support,confidence,lift,store_scope,store_consistent,status,source_run,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(antecedent,consequent,item['support'],item['confidence'],item['lift'],'全门店',consistent,status,run_key,user['id']))
    execute("INSERT INTO audit_logs(actor_id,action,entity_type,detail) VALUES(%s,%s,%s,%s)",(user['id'],'run_apriori','analysis_runs',run_key))
    return {"run_key":run_key,"basket_count":len(transactions),"rule_count":len(results),"rules":results[:12]}
@router.post("/{rule_id}/submit")
def submit(rule_id:int,user=Depends(require_roles("analyst"))):
    rule=fetch_one("SELECT * FROM association_rules WHERE id=%s",(rule_id,))
    if not rule: raise HTTPException(404,"规则不存在")
    if rule['status'] != 'draft': raise HTTPException(409,"只有草稿规则可提交审核")
    if float(rule['support']) < 0.08 or not rule['store_consistent']: raise HTTPException(409,"规则未达到发布前置条件，不能提交审核")
    execute("UPDATE association_rules SET status='submitted' WHERE id=%s",(rule_id,)); execute("INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)",(user['id'],'submit_rule','association_rule',rule_id,'submitted'))
    return {"status":"submitted"}
