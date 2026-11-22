from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException
from pymysql.err import IntegrityError

from ..constants.enums import PromotionStatus as Plan, SettlementStatus as Report
from ..db import fetch_all, transaction
from .basket_ledger import LEDGER_TOTALS, ledger_units

BUSINESS_TZ = timezone(timedelta(hours=8))
PLAN_VIEW = """
    SELECT p.*, r.antecedent, r.consequent, s.code store_code, s.name store_name,
           sku.sku, sku.name product_name, u.display_name operator_name,
           p.unit_discount * p.unit_cap reserved_discount
    FROM promotion_plans p JOIN association_rules r ON r.id=p.rule_id
    JOIN stores s ON s.id=p.store_id JOIN products sku ON sku.id=p.product_id
    JOIN users u ON u.id=p.operator_id
"""


def business_today():
    return datetime.now(BUSINESS_TZ).date()


def plan_options():
    return {
        'today': business_today(),
        'rules': fetch_all("SELECT id, antecedent, consequent FROM association_rules "
                           "WHERE status='published' AND support >= 0.08 AND store_consistent=1 ORDER BY id"),
        'stores': fetch_all('SELECT id, code, name FROM stores WHERE active=1 ORDER BY code'),
        'products': fetch_all("SELECT p.id,p.sku,p.name,p.price,f.name family FROM products p "
                              "JOIN product_families f ON f.id=p.family_id "
                              "WHERE p.status='active' AND f.active=1 ORDER BY p.sku"),
        'operators': fetch_all("SELECT id,display_name FROM users WHERE role='store_operator' ORDER BY id"),
    }


def list_plans(user):
    where, args = ('WHERE p.operator_id=%s', (user['id'],)) if user['role'] == 'store_operator' else ('', ())
    return fetch_all(f'{PLAN_VIEW} {where} ORDER BY p.starts_on DESC, p.id DESC', args)


def audit(cur, user, action, entity, entity_id, detail):
    cur.execute('INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,detail) VALUES(%s,%s,%s,%s,%s)',
                (user['id'], action, entity, entity_id, detail))


def one(cur, sql, args):
    cur.execute(sql, args)
    return cur.fetchone()


def create_plan(data, user):
    if data.starts_on < business_today() or not 0 <= (data.ends_on - data.starts_on).days <= 30:
        raise HTTPException(422, '档期须从今天或之后开始，且最多连续 31 天')
    with transaction() as cur:
        # Serialize reservation checks for a store, including when its first plan is created.
        store = one(cur, 'SELECT active FROM stores WHERE id=%s FOR UPDATE', (data.store_id,))
        if not store or not store['active']:
            raise HTTPException(422, '请选择启用门店')
        rule = one(cur, 'SELECT * FROM association_rules WHERE id=%s FOR SHARE', (data.rule_id,))
        if not rule or rule['status'] != 'published' or rule['support'] < Decimal('0.08') or not rule['store_consistent']:
            raise HTTPException(409, '只有通过统计门槛且已发布的规则能用于排期')
        sku = one(cur, "SELECT p.price, f.name family FROM products p JOIN product_families f ON f.id=p.family_id "
                       "WHERE p.id=%s AND p.status='active' AND f.active=1", (data.product_id,))
        if not sku or sku['family'] != rule['consequent']:
            raise HTTPException(422, '请选择规则后件商品族下的在售 SKU')
        if data.unit_discount * 2 > sku['price']:
            raise HTTPException(422, '单件立减不能超过目录单价的 50%')
        operator = one(cur, "SELECT id FROM users WHERE id=%s AND role='store_operator'", (data.operator_id,))
        if not operator:
            raise HTTPException(422, '请选择门店执行人')
        overlap = one(cur, """SELECT id FROM promotion_plans WHERE store_id=%s AND product_id=%s
            AND status IN ('planned','active','settling') AND starts_on<=%s AND ends_on>=%s
            LIMIT 1 FOR UPDATE""", (data.store_id, data.product_id, data.ends_on, data.starts_on))
        if overlap:
            raise HTTPException(409, f"同门店、同 SKU 已存在交叠档期 #{overlap['id']}")
        cur.execute('''INSERT INTO promotion_plans
            (rule_id,store_id,product_id,operator_id,created_by,starts_on,ends_on,list_price,unit_discount,unit_cap)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (
            data.rule_id, data.store_id, data.product_id, data.operator_id, user['id'],
            data.starts_on, data.ends_on, sku['price'], data.unit_discount, data.unit_cap,
        ))
        plan_id = cur.lastrowid
        audit(cur, user, 'schedule_promotion', 'promotion_plan', plan_id, f'规则 #{data.rule_id}，限量 {data.unit_cap} 件')
    return {'id': plan_id, 'status': Plan.planned}


def locked_plan(cur, plan_id, user):
    plan = one(cur, 'SELECT * FROM promotion_plans WHERE id=%s FOR UPDATE', (plan_id,))
    if not plan or (user['role'] == 'store_operator' and plan['operator_id'] != user['id']):
        raise HTTPException(404, '档期不存在或未分配给当前账号')
    return plan


def activate_plan(plan_id, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if plan['status'] != Plan.planned:
            raise HTTPException(409, '只有已排期档期可开档')
        if not plan['starts_on'] <= business_today() <= plan['ends_on']:
            raise HTTPException(409, '只能在约定档期内开档')
        cur.execute('UPDATE promotion_plans SET status=%s, started_at=UTC_TIMESTAMP() WHERE id=%s', (Plan.active, plan_id))
        audit(cur, user, 'activate_promotion', 'promotion_plan', plan_id, '门店开档')
    return {'status': Plan.active}


def cancel_plan(plan_id, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if plan['status'] != Plan.planned:
            raise HTTPException(409, '只有未开档的档期可以取消')
        cur.execute('UPDATE promotion_plans SET status=%s WHERE id=%s', (Plan.cancelled, plan_id))
        audit(cur, user, 'cancel_promotion', 'promotion_plan', plan_id, '开档前取消')
    return {'status': Plan.cancelled}


def list_settlements(user):
    scope, args = ('AND p.operator_id=%s', (user['id'],)) if user['role'] == 'store_operator' else ('', ())
    return fetch_all(f'''
        SELECT p.id plan_id, p.status plan_status, p.ends_on, p.unit_cap, p.unit_discount,
               p.list_price, s.code store_code, s.name store_name, sku.sku, sku.name product_name,
               e.id, e.status, e.pos_reference, e.redeemed_units, e.note, e.review_note,
               IF(o.plan_id IS NULL,NULL,COALESCE(l.ledger_units,0)) ledger_units,
               e.redeemed_units * p.unit_discount actual_discount,
               (p.unit_cap - e.redeemed_units) * p.unit_discount unspent_discount,
               e.redeemed_units * (p.list_price - p.unit_discount) promo_net_sales
        FROM promotion_plans p JOIN stores s ON s.id=p.store_id JOIN products sku ON sku.id=p.product_id
        LEFT JOIN promotion_settlements e ON e.plan_id=p.id
        LEFT JOIN basket_offers o ON o.plan_id=p.id
        LEFT JOIN ({LEDGER_TOTALS}) l ON l.plan_id=p.id
        WHERE p.status IN ('active','settling','closed') {scope}
        ORDER BY (p.status='closed'), p.id DESC
    ''', args)


def submit_settlement(plan_id, data, user):
    try:
        with transaction() as cur:
            plan = locked_plan(cur, plan_id, user)
            if plan['status'] != Plan.active:
                raise HTTPException(409, '只有执行中或被退回的档期可提交对账')
            if data.redeemed_units > plan['unit_cap']:
                raise HTTPException(422, '核销件数不能超过档期限量')
            if one(cur, 'SELECT plan_id FROM basket_offers WHERE plan_id=%s', (plan_id,)):
                actual = ledger_units(cur, plan_id)
                if data.redeemed_units != actual:
                    raise HTTPException(422, f'POS 填报件数须与逐票流水一致，当前有效核销 {actual} 件')
            if (business_today() < plan['ends_on'] or data.redeemed_units == 0) and not data.note:
                raise HTTPException(422, '提前结档或零核销须填写说明')
            previous = one(cur, 'SELECT id,status FROM promotion_settlements WHERE plan_id=%s FOR UPDATE', (plan_id,))
            reference = data.pos_reference.upper()
            if previous:
                if previous['status'] != Report.returned:
                    raise HTTPException(409, '只有已退回的对账单可以更正')
                report_id = previous['id']
                cur.execute('''UPDATE promotion_settlements SET pos_reference=%s, redeemed_units=%s, note=%s,
                    status=%s, submitted_by=%s, submitted_at=UTC_TIMESTAMP(), reviewed_by=NULL,
                    reviewed_at=NULL, review_note=NULL WHERE id=%s''',
                    (reference, data.redeemed_units, data.note, Report.submitted, user['id'], report_id))
            else:
                cur.execute('''INSERT INTO promotion_settlements
                    (plan_id,store_id,pos_reference,redeemed_units,note,submitted_by)
                    VALUES(%s,%s,%s,%s,%s,%s)''',
                    (plan_id, plan['store_id'], reference, data.redeemed_units, data.note, user['id']))
                report_id = cur.lastrowid
            cur.execute('UPDATE promotion_plans SET status=%s WHERE id=%s', (Plan.settling, plan_id))
            audit(cur, user, 'submit_settlement', 'promotion_settlement', report_id,
                  f'{reference}，{data.redeemed_units} 件，{data.note}')
    except IntegrityError as exc:
        if exc.args[0] == 1062:
            raise HTTPException(409, '同门店的 POS 对账凭证已被另一档期登记') from exc
        raise
    return {'id': report_id, 'status': Report.submitted}


def review_settlement(plan_id, data, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if plan['status'] != Plan.settling:
            raise HTTPException(409, '只有待对账档期可复核')
        report = one(cur, 'SELECT id,status FROM promotion_settlements WHERE plan_id=%s FOR UPDATE', (plan_id,))
        if not report or report['status'] != Report.submitted:
            raise HTTPException(409, '没有待复核的对账单')
        if data.decision == 'return' and not data.note:
            raise HTTPException(422, '退回须填写更正意见')
        status, plan_status = (Report.confirmed, Plan.closed) if data.decision == 'confirm' else (Report.returned, Plan.active)
        cur.execute('''UPDATE promotion_settlements SET status=%s,reviewed_by=%s,review_note=%s,
            reviewed_at=UTC_TIMESTAMP() WHERE id=%s''', (status, user['id'], data.note, report['id']))
        cur.execute('UPDATE promotion_plans SET status=%s WHERE id=%s', (plan_status, plan_id))
        audit(cur, user, f'{data.decision}_settlement', 'promotion_settlement', report['id'], data.note)
    return {'status': status, 'plan_status': plan_status}
