from fastapi import APIRouter, Depends
from ..db import fetch_all
from ..security import current_user
router = APIRouter(prefix="/catalog", tags=["catalog"])
@router.get("/families")
def families(user=Depends(current_user)): return fetch_all("SELECT id,name,category,description,active FROM product_families ORDER BY id")
@router.get("/products")
def products(user=Depends(current_user)):
    return fetch_all("SELECT p.id,p.sku,p.name,p.price,p.status,f.name family_name,f.category FROM products p JOIN product_families f ON f.id=p.family_id ORDER BY f.id,p.id")
@router.get("/stores")
def stores(user=Depends(current_user)): return fetch_all("SELECT id,code,name,region,active FROM stores ORDER BY id")
