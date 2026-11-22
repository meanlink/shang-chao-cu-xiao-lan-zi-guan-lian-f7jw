import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
os.environ.setdefault('MYSQL_HOST', '127.0.0.1')
os.environ.setdefault('MYSQL_PORT', '13306')
os.environ.setdefault('MYSQL_USER', 'app')
os.environ.setdefault('MYSQL_PASSWORD', 'app_pass')
os.environ.setdefault('MYSQL_DATABASE', 'supermarket_basket_test')
os.environ.setdefault('SEED_DEMO', 'false')

import pymysql  # noqa: E402
from pymysql.cursors import DictCursor  # noqa: E402

from src.config import MYSQL  # noqa: E402
from src.db import connect, init_db  # noqa: E402
from src.security import issue_token, password_hash  # noqa: E402

TODAY = date.today()


def admin_cursor():
    cfg = dict(MYSQL)
    cfg['database'] = None
    cfg['cursorclass'] = DictCursor
    return pymysql.connect(**cfg)


@pytest.fixture(scope='session', autouse=True)
def database():
    # The application user only owns the application schema; create the test
    # schema over a privileged local socket and hand it over.
    root_cfg = dict(MYSQL)
    root_cfg.update(database=None, cursorclass=DictCursor,
                    user=os.environ.get('TEST_DB_ADMIN_USER', 'root'),
                    password=os.environ.get('TEST_DB_ADMIN_PASSWORD', None))
    socket = os.environ.get('TEST_DB_ADMIN_SOCKET')
    if socket:
        root_cfg.update(host='localhost', unix_socket=socket)
    try:
        root = pymysql.connect(**root_cfg)
    except Exception:
        root = admin_cursor()  # environments where the app user is already privileged
    with root.cursor() as cur:
        cur.execute('CREATE DATABASE IF NOT EXISTS supermarket_basket_test CHARACTER SET utf8mb4')
        cur.execute("CREATE USER IF NOT EXISTS 'app'@'%%' IDENTIFIED BY 'app_pass'")
        cur.execute("CREATE USER IF NOT EXISTS 'app'@'localhost' IDENTIFIED BY 'app_pass'")
        cur.execute("GRANT ALL PRIVILEGES ON supermarket_basket_test.* TO 'app'@'%%'")
        cur.execute("GRANT ALL PRIVILEGES ON supermarket_basket_test.* TO 'app'@'localhost'")
        cur.execute('FLUSH PRIVILEGES')
    root.close()
    init_db()
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    conn = connect()
    with conn.cursor() as cur:
        cur.execute('SET FOREIGN_KEY_CHECKS=0')
        cur.execute('SHOW TABLES')
        for row in cur.fetchall():
            name = next(iter(row.values()))
            cur.execute(f'TRUNCATE TABLE `{name}`')
        cur.execute('SET FOREIGN_KEY_CHECKS=1')
    conn.commit()
    conn.close()
    yield


@pytest.fixture
def users():
    from src.db import execute
    rows = [
        ('manager@linli.local', '周宁 / 促销经理', 'manager'),
        ('store@linli.local', '陈杰 / 门店执行', 'store_operator'),
        ('store-east@linli.local', '徐琳 / 门店执行', 'store_operator'),
        ('ops@linli.local', '林晨 / 运营分析', 'analyst'),
    ]
    out = {}
    keys = ['manager', 'store_operator', 'store_operator_east', 'analyst']
    for (email, name, role), key in zip(rows, keys):
        uid = execute('INSERT INTO users(email,display_name,role,password_hash) VALUES(%s,%s,%s,%s)',
                      (email, name, role, password_hash('basket123')))
        out[key] = {'id': uid, 'email': email}
    return out


@pytest.fixture
def catalog(users):
    from src.db import execute
    families = {}
    for name, category in [('咖啡与冲调', '饮品'), ('乳品', '食品'), ('早餐烘焙', '烘焙')]:
        fid = execute('INSERT INTO product_families(name,category) VALUES(%s,%s)', (name, category))
        families[name] = fid
    sku1 = execute('INSERT INTO products(sku,name,family_id,price) VALUES(%s,%s,%s,%s)',
                   ('BK-001', '全麦吐司', families['早餐烘焙'], 15.80))
    sku2 = execute('INSERT INTO products(sku,name,family_id,price) VALUES(%s,%s,%s,%s)',
                   ('BK-002', '燕麦早餐饼', families['早餐烘焙'], 22.00))
    ml1 = execute('INSERT INTO products(sku,name,family_id,price) VALUES(%s,%s,%s,%s)',
                  ('ML-001', '高钙纯牛奶 1L', families['乳品'], 12.50))
    stores = {}
    for code, name in [('BJ-HS', '海淀星河店'), ('BJ-CY', '朝阳望京店'), ('SH-XH', '徐汇滨江店')]:
        sid = execute('INSERT INTO stores(code,name,region) VALUES(%s,%s,%s)', (code, name, '华北'))
        stores[code] = sid
    rule_id = execute('''INSERT INTO association_rules
        (antecedent,consequent,support,confidence,lift,store_scope,store_consistent,status,source_run,created_by)
        VALUES(%s,%s,%s,%s,%s,%s,1,'published','test-run',%s)''',
        ('咖啡与冲调 + 乳品', '早餐烘焙', 0.25, 0.6, 1.8, '全门店', users['manager']['id']))
    return {'products': {'BK-001': sku1, 'BK-002': sku2, 'ML-001': ml1},
            'stores': stores, 'rule_id': rule_id, 'families': families}


def make_plan(store_id, product_id, unit_discount, unit_cap, operator_id, created_by,
              starts_on=None, ends_on=None, status='active'):
    from src.db import execute
    starts = starts_on or TODAY
    ends = ends_on or (TODAY + timedelta(days=7))
    return execute('''INSERT INTO promotion_plans
        (rule_id,store_id,product_id,operator_id,created_by,starts_on,ends_on,list_price,unit_discount,unit_cap,
         status,started_at)
        VALUES(1,%s,%s,%s,%s,%s,%s,30.00,%s,%s,%s,UTC_TIMESTAMP())''',
        (store_id, product_id, operator_id, created_by, starts, ends, unit_discount, unit_cap, status))


def enable_basket_offer(plan_id, user_id, per_receipt_cap=10):
    from src.db import execute
    execute('INSERT INTO basket_offers(plan_id,per_receipt_cap,configured_by) VALUES(%s,%s,%s)',
            (plan_id, per_receipt_cap, user_id))
    # Require one dairy unit (family id 2, ML-001) as the antecedent purchase.
    execute('INSERT INTO basket_offer_requirements(plan_id,family_id,minimum_units) VALUES(%s,2,1)',
            (plan_id,))


def book_receipt(plan_id, store_id, user_id, sku, units, receipt_no=None):
    from src.db import execute
    receipt_no = receipt_no or f'R-{uuid.uuid4().hex[:10].upper()}'
    rid = execute('''INSERT INTO basket_receipts
        (plan_id,store_id,receipt_no,business_date,rewarded_units,discount_amount,recorded_by)
        VALUES(%s,%s,%s,%s,%s,%s,%s)''',
        (plan_id, store_id, receipt_no, TODAY, units, units * 5.00, user_id))
    return rid


def auth_header(user):
    return {'Authorization': f'Bearer {issue_token(user)}'}


def user_row(uid):
    from src.db import fetch_one
    return fetch_one('SELECT id,email,display_name,role FROM users WHERE id=%s', (uid,))


@pytest.fixture
def pair(users, catalog):
    """Two active same-SKU, same-discount plans in different stores."""
    src = make_plan(catalog['stores']['BJ-HS'], catalog['products']['BK-001'], 5.00, 20,
                    users['store_operator']['id'], users['manager']['id'])
    dst = make_plan(catalog['stores']['BJ-CY'], catalog['products']['BK-001'], 5.00, 10,
                    users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(src, users['manager']['id'])
    enable_basket_offer(dst, users['manager']['id'])
    return {'source': src, 'target': dst}
