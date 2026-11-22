"""Journal queries shared by the receipt desk and finance reconciliation."""

from collections import defaultdict

from fastapi import HTTPException

from ..db import fetch_all, transaction


LEDGER_TOTALS = """
    SELECT plan_id, SUM(rewarded_units) ledger_units, SUM(discount_amount) ledger_discount,
           COUNT(*) receipt_count
    FROM basket_receipts WHERE voided_at IS NULL GROUP BY plan_id
"""

CATALOG = """
    SELECT p.id, p.sku, p.name, p.family_id, f.name family
    FROM products p JOIN product_families f ON f.id=p.family_id
    WHERE p.status='active' AND f.active=1
"""


def ledger_units(cur, plan_id):
    cur.execute('SELECT COALESCE(SUM(rewarded_units),0) units FROM basket_receipts '
                'WHERE plan_id=%s AND voided_at IS NULL', (plan_id,))
    return int(cur.fetchone()['units'])


def desk_plans(user):
    where, args = ('WHERE p.operator_id=%s', (user['id'],)) if user['role'] == 'store_operator' else ('', ())
    return fetch_all(f'''
        SELECT p.id, p.status, p.starts_on, p.ends_on, p.unit_cap, p.unit_discount,
               p.list_price, r.antecedent, s.code store_code, s.name store_name,
               sku.sku, sku.name product_name, u.display_name operator_name, o.per_receipt_cap,
               COALESCE(l.ledger_units,0) ledger_units, COALESCE(l.ledger_discount,0) ledger_discount,
               COALESCE(l.receipt_count,0) receipt_count
        FROM promotion_plans p JOIN association_rules r ON r.id=p.rule_id
        JOIN stores s ON s.id=p.store_id JOIN products sku ON sku.id=p.product_id
        JOIN users u ON u.id=p.operator_id LEFT JOIN basket_offers o ON o.plan_id=p.id
        LEFT JOIN ({LEDGER_TOTALS}) l ON l.plan_id=p.id
        {where}
        ORDER BY p.id DESC
    ''', args)


def desk_detail(plan_id, user):
    with transaction() as cur:
        cur.execute('SELECT operator_id FROM promotion_plans WHERE id=%s', (plan_id,))
        plan = cur.fetchone()
        if not plan or (user['role'] == 'store_operator' and plan['operator_id'] != user['id']):
            raise HTTPException(404, '档期不存在或未分配给当前账号')
        cur.execute('''SELECT f.name family, q.minimum_units FROM basket_offer_requirements q
                       JOIN product_families f ON f.id=q.family_id WHERE q.plan_id=%s ORDER BY f.name''', (plan_id,))
        requirements = cur.fetchall()
        if user['role'] == 'analyst':
            return {'requirements': requirements, 'receipts': [], 'catalog': []}
        cur.execute('''SELECT id, receipt_no, business_date, rewarded_units, discount_amount,
                              recorded_at, voided_at, void_reason FROM basket_receipts
                       WHERE plan_id=%s ORDER BY id DESC LIMIT 100''', (plan_id,))
        receipts = cur.fetchall()
        if receipts:
            ids = [receipt['id'] for receipt in receipts]
            placeholders = ','.join(['%s'] * len(ids))
            cur.execute(f'''SELECT receipt_id, sku, quantity FROM basket_receipt_lines
                           WHERE receipt_id IN ({placeholders}) ORDER BY sku''', ids)
            grouped = defaultdict(list)
            for line in cur.fetchall():
                grouped[line['receipt_id']].append({'sku': line['sku'], 'quantity': line['quantity']})
            for receipt in receipts:
                receipt['lines'] = grouped[receipt['id']]
        catalog = []
        if user['role'] == 'store_operator' and requirements:
            cur.execute(f'{CATALOG} ORDER BY p.sku')
            catalog = cur.fetchall()
        return {'requirements': requirements, 'receipts': receipts, 'catalog': catalog}
