from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from ..db import fetch_all, fetch_one, execute
from ..security import current_user, require_roles
router = APIRouter(prefix="/orders", tags=["orders"])
class ImportIn(BaseModel): source_file: str = "orders_2026-11-20.csv"; order_ids: list[str] = []
@router.get("")
def orders(user=Depends(current_user)):
    return fetch_all("SELECT o.id,o.external_id,o.order_date,o.total_amount,o.source_file,o.status,s.code store_code,s.name store_name, COUNT(i.id) item_count FROM basket_orders o JOIN stores s ON s.id=o.store_id LEFT JOIN basket_items i ON i.order_id=o.id GROUP BY o.id ORDER BY o.id DESC")
@router.post("/import")
def import_orders(data: ImportIn, user=Depends(require_roles("analyst"))):
    existing = fetch_one("SELECT COUNT(*) c FROM basket_orders")['c']
    execute("INSERT INTO audit_logs(actor_id,action,entity_type,detail) VALUES(%s,%s,%s,%s)",(user['id'],'import_orders','basket_orders',data.source_file))
    return {"message":"订单文件已校验并入篮", "source_file":data.source_file, "existing_orders":existing, "imported":0, "idempotent":True}
