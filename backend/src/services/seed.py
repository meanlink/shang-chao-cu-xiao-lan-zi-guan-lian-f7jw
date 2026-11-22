from datetime import date
from ..db import execute, fetch_one, fetch_all
from ..security import password_hash

def seed_demo():
    users = [
        ("ops@linli.local", "林晨 / 运营分析", "analyst"),
        ("manager@linli.local", "周宁 / 促销经理", "manager"),
        ("store@linli.local", "陈杰 / 门店执行", "store_operator"),
        ("store-east@linli.local", "徐琳 / 门店执行", "store_operator"),
    ]
    for email, name, role in users:
        if not fetch_one("SELECT id FROM users WHERE email=%s", (email,)):
            execute("INSERT INTO users(email,display_name,role,password_hash) VALUES(%s,%s,%s,%s)", (email,name,role,password_hash("basket123")))
    stores = [("BJ-HS", "海淀星河店", "华北"), ("BJ-CY", "朝阳望京店", "华北"), ("SH-XH", "徐汇滨江店", "华东")]
    for code, name, region in stores:
        if not fetch_one("SELECT id FROM stores WHERE code=%s", (code,)): execute("INSERT INTO stores(code,name,region) VALUES(%s,%s,%s)", (code,name,region))
    families = [("咖啡与冲调", "饮品", "咖啡豆、挂耳与即饮咖啡"), ("乳品", "食品", "牛奶、酸奶与植物奶"), ("早餐烘焙", "烘焙", "面包、麦片与早餐饼"), ("清洁纸品", "家清", "抽纸、湿巾与厨房纸"), ("零食坚果", "零食", "坚果、饼干与巧克力")]
    for name, cat, desc in families:
        if not fetch_one("SELECT id FROM product_families WHERE name=%s", (name,)): execute("INSERT INTO product_families(name,category,description) VALUES(%s,%s,%s)", (name,cat,desc))
    family_ids = {r['name']: r['id'] for r in fetch_all("SELECT id,name FROM product_families")}
    products = [("CF-001","山野拼配咖啡豆",family_ids["咖啡与冲调"],59.0),("CF-002","冷萃挂耳咖啡",family_ids["咖啡与冲调"],29.0),("ML-001","高钙纯牛奶 1L",family_ids["乳品"],12.5),("ML-002","燕麦植物奶 1L",family_ids["乳品"],18.9),("BK-001","全麦吐司",family_ids["早餐烘焙"],15.8),("BK-002","燕麦早餐饼",family_ids["早餐烘焙"],22.0),("CL-001","厨房抽纸 3层",family_ids["清洁纸品"],18.5),("SN-001","混合坚果 250g",family_ids["零食坚果"],36.0)]
    for sku,name,fid,price in products:
        if not fetch_one("SELECT id FROM products WHERE sku=%s", (sku,)): execute("INSERT INTO products(sku,name,family_id,price) VALUES(%s,%s,%s,%s)",(sku,name,fid,price))
    product_ids = {r['sku']: r['id'] for r in fetch_all("SELECT id,sku FROM products")}
    store_ids = {r['code']: r['id'] for r in fetch_all("SELECT id,code FROM stores")}
    baskets = [
        ("POS-1120-0001","BJ-HS",["CF-001","ML-001","BK-001"]),("POS-1120-0002","BJ-HS",["CF-002","ML-001"]),("POS-1120-0003","BJ-CY",["CF-001","ML-001","BK-002"]),("POS-1120-0004","BJ-CY",["CF-001","ML-001"]),("POS-1120-0005","SH-XH",["CF-002","ML-002","BK-002"]),("POS-1120-0006","SH-XH",["CF-001","ML-001","BK-001"]),("POS-1120-0007","BJ-HS",["CL-001","SN-001"]),("POS-1120-0008","BJ-CY",["CL-001"]),("POS-1120-0009","SH-XH",["SN-001","BK-002"]),("POS-1120-0010","BJ-HS",["CF-001","ML-001"]),("POS-1120-0011","BJ-CY",["CF-001","ML-001","BK-001"]),("POS-1120-0012","SH-XH",["CF-001","ML-001"]),
    ]
    for external, store, skus in baskets:
        if not fetch_one("SELECT id FROM basket_orders WHERE external_id=%s",(external,)):
            total = sum(float(fetch_one("SELECT price FROM products WHERE sku=%s",(s,))["price"]) for s in skus)
            oid = execute("INSERT INTO basket_orders(external_id,store_id,order_date,total_amount,source_file) VALUES(%s,%s,%s,%s,%s)",(external,store_ids[store],date(2026,11,20),total,"orders_2026-11-20.csv"))
            for sku in skus:
                p = fetch_one("SELECT id,price FROM products WHERE sku=%s",(sku,))
                execute("INSERT INTO basket_items(order_id,product_id,quantity,unit_price) VALUES(%s,%s,1,%s)",(oid,p['id'],p['price']))
    analyst = fetch_one("SELECT id FROM users WHERE email='ops@linli.local'")['id']
    if not fetch_one("SELECT id FROM association_rules WHERE antecedent=%s AND consequent=%s", ("咖啡与冲调 + 乳品", "早餐烘焙")):
        execute("INSERT INTO association_rules(antecedent,consequent,support,confidence,lift,store_scope,store_consistent,status,source_run,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", ("咖啡与冲调 + 乳品","早餐烘焙",0.25,0.60,1.80,"全门店",1,"submitted","seed-20261120",analyst))
    if not fetch_one("SELECT id FROM association_rules WHERE antecedent=%s AND consequent=%s", ("清洁纸品", "零食坚果")):
        execute("INSERT INTO association_rules(antecedent,consequent,support,confidence,lift,store_scope,store_consistent,status,source_run,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", ("清洁纸品","零食坚果",0.04,0.18,0.72,"BJ-HS / BJ-CY / SH-XH",1,"blocked","seed-20261120",analyst))
    if not fetch_one("SELECT id FROM association_rules WHERE antecedent=%s AND consequent=%s", ("乳品", "清洁纸品")):
        execute("INSERT INTO association_rules(antecedent,consequent,support,confidence,lift,store_scope,store_consistent,status,source_run,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", ("乳品","清洁纸品",0.17,0.42,1.26,"BJ-HS / BJ-CY / SH-XH",0,"blocked","seed-20261120",analyst))
