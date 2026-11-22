"""End-to-end smoke test over real HTTP: transfer vs receipt vs settlement concurrency."""
import os
import sys
import threading
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('MYSQL_HOST', '127.0.0.1')
os.environ.setdefault('MYSQL_PORT', '13306')
os.environ.setdefault('MYSQL_DATABASE', 'supermarket_basket_smoke')
os.environ.setdefault('SEED_DEMO', 'false')

import pymysql
from pymysql.cursors import DictCursor
from src.config import MYSQL
from src.db import execute, fetch_all, fetch_one, init_db
from src.security import issue_token, password_hash
from fastapi.testclient import TestClient
from src.main import app

TODAY = date.today()

# ---- provision a fresh smoke schema ----
root_cfg = dict(MYSQL); root_cfg.update(database=None, cursorclass=DictCursor, user='root', password=None,
                                        host='localhost', unix_socket='/tmp/mdb/run/mysql.sock')
root = pymysql.connect(**root_cfg)
with root.cursor() as cur:
    cur.execute('DROP DATABASE IF EXISTS supermarket_basket_smoke')
    cur.execute('CREATE DATABASE supermarket_basket_smoke CHARACTER SET utf8mb4')
    cur.execute("CREATE USER IF NOT EXISTS 'app'@'%' IDENTIFIED BY 'app_pass'")
    cur.execute("GRANT ALL PRIVILEGES ON supermarket_basket_smoke.* TO 'app'@'%'")
root.close()
init_db()

manager = execute("INSERT INTO users(email,display_name,role,password_hash) VALUES('m@x.cn','经理','manager',%s)",
                  (password_hash('x'),))
op1 = execute("INSERT INTO users(email,display_name,role,password_hash) VALUES('o1@x.cn','门店A','store_operator',%s)",
              (password_hash('x'),))
op2 = execute("INSERT INTO users(email,display_name,role,password_hash) VALUES('o2@x.cn','门店B','store_operator',%s)",
              (password_hash('x'),))
s1 = execute("INSERT INTO stores(code,name,region) VALUES('S1','门店甲','华北')")
s2 = execute("INSERT INTO stores(code,name,region) VALUES('S2','门店乙','华北')")
fam = execute("INSERT INTO product_families(name,category) VALUES('烘焙','烘焙')")
prod = execute("INSERT INTO products(sku,name,family_id,price) VALUES('BK-1','吐司',%s,20.00)", (fam,))
rule = execute("""INSERT INTO association_rules(antecedent,consequent,support,confidence,lift,store_scope,
                 store_consistent,status,source_run,created_by)
                 VALUES('乳品','烘焙',0.2,0.5,1.5,'全门店',1,'published','run',%s)""", (manager,))

def plan(store, op, cap):
    return execute("""INSERT INTO promotion_plans(rule_id,store_id,product_id,operator_id,created_by,
                     starts_on,ends_on,list_price,unit_discount,unit_cap,status,started_at)
                     VALUES(%s,%s,%s,%s,%s,%s,%s,20.00,5.00,%s,'active',UTC_TIMESTAMP())""",
                   (rule, store, prod, op, manager, TODAY, TODAY + timedelta(days=5), cap))

def offer(pid, cap):
    execute('INSERT INTO basket_offers(plan_id,per_receipt_cap,configured_by) VALUES(%s,%s,%s)', (pid, cap, manager))
    execute('INSERT INTO basket_offer_requirements(plan_id,family_id,minimum_units) VALUES(%s,%s,1)', (pid, fam))

p_a, p_b = plan(s1, op1, 8), plan(s2, op2, 6)
offer(p_a, 5); offer(p_b, 5)
client = TestClient(app)
mh = {'Authorization': f'Bearer {issue_token(fetch_one("SELECT id,email,display_name,role FROM users WHERE id=%s", (manager,)))}'}
oh = {'Authorization': f'Bearer {issue_token(fetch_one("SELECT id,email,display_name,role FROM users WHERE id=%s", (op1,)))}'}

print('== 1) eligible pairing ==')
rows = client.get('/promotions/budget-transfer/plans', headers=mh).json()
assert len(rows) == 2 and set(rows[0]['partners'] + rows[1]['partners']) == {p_a, p_b}
print('   partners:', [(r['id'], r['partners'], r['remaining_units']) for r in rows])

print('== 2) transfer 5 units A -> B, idempotent key ==')
key = uuid.uuid4().hex
body = {'source_plan_id': p_a, 'target_plan_id': p_b, 'transferred_units': 5, 'request_key': key}
r1 = client.post('/promotions/budget-transfer', json=body, headers=mh)
r2 = client.post('/promotions/budget-transfer', json=body, headers=mh)
assert r1.status_code == 201 and r2.json()['replayed'] is True and r1.json()['id'] == r2.json()['id']
print('  ', r1.json(), 'retry ->', r2.json())
assert fetch_one('SELECT unit_cap c FROM promotion_plans WHERE id=%s', (p_a,))['c'] == 3
assert fetch_one('SELECT unit_cap c FROM promotion_plans WHERE id=%s', (p_b,))['c'] == 11

print('== 3) concurrent transfer (overdraw) vs receipts on source ==')
# After step 2: A cap=3, B cap=11. One in-bounds transfer of 2 can succeed;
# anything larger must be rejected. Two receipts of 1 unit each stay within cap.
errors, accepted = [], []
def transfer(n):
    r = client.post('/promotions/budget-transfer',
                    json={'source_plan_id': p_a, 'target_plan_id': p_b, 'transferred_units': n,
                          'request_key': uuid.uuid4().hex}, headers=mh)
    (accepted if r.status_code == 201 else errors).append((r.status_code, r.json().get('detail')))

def receipt(n, no):
    execute("""INSERT INTO basket_receipts(plan_id,store_id,receipt_no,business_date,
                 rewarded_units,discount_amount,recorded_by)
                 VALUES(%s,%s,%s,%s,%s,%s,%s)""",
            (p_a, s1, no, TODAY, n, n * 5.00, op1))

ts = [threading.Thread(target=transfer, args=(n,)) for n in (2, 3, 3)]
rs = [threading.Thread(target=receipt, args=(1, f'RC-{i}')) for i in range(2)]  # 2 units used
for t in ts + rs: t.start()
for t in ts + rs: t.join()
print('   accepted transfers:', accepted)
print('   rejected transfers:', errors)
cap_a = fetch_one('SELECT unit_cap c FROM promotion_plans WHERE id=%s', (p_a,))['c']
used_a = fetch_one("SELECT COALESCE(SUM(rewarded_units),0) u FROM basket_receipts WHERE plan_id=%s AND voided_at IS NULL", (p_a,))['u']
moved = fetch_one('SELECT COALESCE(SUM(transferred_units),0) m FROM promotion_budget_transfers WHERE source_plan_id=%s', (p_a,))['m']
print(f'   A: cap={cap_a} used={used_a} moved_out={moved}; used+moved={used_a+moved} <= original 8')
assert used_a + moved <= 8, 'budget conservation violated'
assert all(code == 409 for code, _ in errors), 'only 409 conflict rejections expected'
# No matter which thread wins the row lock, every accepted transfer must fit the
# remaining headroom and rejected ones must leave both balances untouched.
transfer_rows = fetch_all("SELECT source_cap_before, source_cap_after, target_cap_before, target_cap_after, "
                          "transferred_units FROM promotion_budget_transfers WHERE source_plan_id=%s", (p_a,))
for row in transfer_rows:
    assert row['source_cap_after'] == row['source_cap_before'] - row['transferred_units']
    assert row['target_cap_after'] == row['target_cap_before'] + row['transferred_units']
print(f'   {len(accepted)} transfer(s) landed, {len(errors)} rejected; all-or-nothing invariant holds')

print('== 4) settlement submit enforces transferred cap ==')
# A has cap 3 (or less after step 3), receipts total 4+ units -> submitting redeemed beyond cap rejected
r = client.post(f'/promotions/settlements/{p_a}/submit',
                json={'pos_reference': f'POS-{uuid.uuid4().hex[:8]}', 'redeemed_units': 99, 'note': 'x'}, headers=oh)
print('   over-cap settlement ->', r.status_code, r.json().get('detail'))
assert r.status_code == 422

print('== 5) plan detail exposes transfer trail with before/after balances ==')
detail = client.get(f'/basket-offers/plans/{p_a}', headers=oh).json()
assert detail['transfers'], 'transfer trail missing'
for t in detail['transfers']:
    print('   trail:', {k: t[k] for k in ('source_plan_id', 'target_plan_id', 'transferred_units',
                                          'source_cap_before', 'source_cap_after',
                                          'target_cap_before', 'target_cap_after')})

print('== 6) historical receipt amount preserved ==')
old = fetch_one('SELECT discount_amount d FROM basket_receipts WHERE receipt_no=%s', ('RC-0',))
print('   old receipt discount still', old['d'])
assert old['d'] == 5.00

print('\nALL SMOKE CHECKS PASSED')
