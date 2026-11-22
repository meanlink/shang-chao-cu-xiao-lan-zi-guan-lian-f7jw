"""Atomic, idempotent budget transfers between two in-flight promotions.

A transfer moves whole reward units from one still-running plan to another
plan that promotes the same product with the same per-unit discount. Both
rows are locked inside one transaction so a concurrent receipt booking or
settlement submit can never overspend: either both caps move or neither does.
"""

from fastapi import HTTPException
from pymysql.err import IntegrityError

from ..constants.enums import PromotionStatus
from ..db import fetch_all, fetch_one, transaction
from .promotion import audit, business_today, one

ELIGIBLE_STATUSES = (PromotionStatus.active, PromotionStatus.settling)

ELIGIBLE_PLAN_SELECT = """
    SELECT p.id, p.operator_id, p.store_id, p.product_id, p.unit_discount, p.unit_cap, p.status,
           p.starts_on, p.ends_on, s.code store_code, s.name store_name,
           sku.sku, sku.name product_name,
           (SELECT COALESCE(SUM(r.rewarded_units), 0) FROM basket_receipts r
            WHERE r.plan_id = p.id AND r.voided_at IS NULL) ledger_units
    FROM promotion_plans p
    JOIN stores s ON s.id = p.store_id
    JOIN products sku ON sku.id = p.product_id
"""


def transferable_plans(user):
    """Pair up still-running same-SKU, same-discount plans across stores.

    Operators keep visibility of the counterpart plan in another store so a
    transfer pair reads as a pair; only managers may actually move budget.
    """
    today = business_today()
    all_plans = fetch_all(f'{ELIGIBLE_PLAN_SELECT} ORDER BY p.id')
    if user['role'] == 'store_operator':
        mine = {p['id'] for p in all_plans if p['operator_id'] == user['id']}
        plans = [p for p in all_plans if p['operator_id'] == user['id']
                 or any(m['product_id'] == p['product_id']
                        and m['unit_discount'] == p['unit_discount']
                        and m['store_id'] != p['store_id'] for m in all_plans
                        if m['id'] in mine and m['status'] in ELIGIBLE_STATUSES
                        and m['starts_on'] <= today <= m['ends_on'])]
    else:
        plans = all_plans
    running = [p for p in plans if p['status'] in ELIGIBLE_STATUSES
               and p['starts_on'] <= today <= p['ends_on']]
    for plan in running:
        plan['remaining_units'] = plan['unit_cap'] - plan['ledger_units']
        plan['partners'] = [other['id'] for other in running
                            if other['id'] != plan['id']
                            and other['product_id'] == plan['product_id']
                            and other['unit_discount'] == plan['unit_discount']
                            and other['store_id'] != plan['store_id']]
    return running


def transfer_history(plan_id=None):
    where, args = ('WHERE t.source_plan_id=%s OR t.target_plan_id=%s', (plan_id, plan_id)) if plan_id else ('', ())
    return fetch_all(f"""
        SELECT t.*, u.display_name operator_name,
               ss.code source_store_code, ss.name source_store_name,
               st.code target_store_code, st.name target_store_name,
               sku.sku, sku.name product_name
        FROM promotion_budget_transfers t
        JOIN users u ON u.id = t.created_by
        JOIN promotion_plans ps ON ps.id = t.source_plan_id
        JOIN promotion_plans pt ON pt.id = t.target_plan_id
        JOIN stores ss ON ss.id = ps.store_id
        JOIN stores st ON st.id = pt.store_id
        JOIN products sku ON sku.id = ps.product_id
        {where}
        ORDER BY t.id DESC LIMIT 200
    """, args)


def _replay(cur, request_key):
    return one(cur, 'SELECT * FROM promotion_budget_transfers WHERE request_key=%s FOR UPDATE', (request_key,))


def transfer_budget(data, user):
    # Idempotency: a retried request with the same key never moves budget twice.
    existing = fetch_one('SELECT * FROM promotion_budget_transfers WHERE request_key=%s', (data.request_key,))
    if existing:
        if (existing['source_plan_id'] != data.source_plan_id
                or existing['target_plan_id'] != data.target_plan_id
                or existing['transferred_units'] != data.transferred_units):
            raise HTTPException(409, '该请求编号已用于另一笔调拨，请刷新后重新发起')
        return {'id': existing['id'], 'replayed': True,
                'transferred_units': existing['transferred_units']}
    try:
        with transaction() as cur:
            # Lock the lower id first to keep lock order deterministic across
            # two transfers moving budget in opposite directions concurrently.
            first_id, second_id = sorted((data.source_plan_id, data.target_plan_id))
            cur.execute('SELECT id FROM promotion_plans WHERE id IN (%s,%s) ORDER BY id FOR UPDATE',
                        (first_id, second_id))
            # Another request with the same key may have committed while we waited.
            duplicate = _replay(cur, data.request_key)
            if duplicate:
                return {'id': duplicate['id'], 'replayed': True,
                        'transferred_units': duplicate['transferred_units']}
            source = one(cur, 'SELECT * FROM promotion_plans WHERE id=%s FOR UPDATE', (data.source_plan_id,))
            target = one(cur, 'SELECT * FROM promotion_plans WHERE id=%s FOR UPDATE', (data.target_plan_id,))
            if not source or not target:
                raise HTTPException(404, '调出或调入档期不存在')
            if source['store_id'] == target['store_id']:
                raise HTTPException(422, '预算调拨只能在两家不同门店之间进行')
            if source['product_id'] != target['product_id']:
                raise HTTPException(422, '只能给同款商品的档期划拨预算')
            if source['unit_discount'] != target['unit_discount']:
                raise HTTPException(422, '两边单件立减不一致，划拨件数无法折成相同的整件预算')
            today = business_today()
            for side, plan in (('调出', source), ('调入', target)):
                if plan['status'] not in ELIGIBLE_STATUSES:
                    raise HTTPException(409, f'{side}档期须仍在执行（执行中或待对账），当前为 {plan["status"]}')
                if not plan['starts_on'] <= today <= plan['ends_on']:
                    raise HTTPException(409, f'{side}档期不在档期日期内，不能划拨预算')
            cur.execute('SELECT COALESCE(SUM(rewarded_units),0) units FROM basket_receipts '
                        'WHERE plan_id=%s AND voided_at IS NULL', (source['id'],))
            source_used = int(cur.fetchone()['units'])
            source_remaining = source['unit_cap'] - source_used
            if source_remaining <= 0:
                raise HTTPException(409, '调出档期预算已用完，无可划拨额度')
            if data.transferred_units > source_remaining:
                raise HTTPException(409, f'调出档期只剩 {source_remaining} 件可划拨，本笔申请 {data.transferred_units} 件')
            # The plan-level CHECK constraints require a positive cap; the
            # source must keep at least one unit of headroom after the move.
            if source['unit_cap'] - data.transferred_units < 1:
                raise HTTPException(422, '调出档期划拨后至少保留 1 件限量，不能全部清空')
            if target['unit_cap'] + data.transferred_units > 100000:
                raise HTTPException(422, '调入档期划拨后限量不能超过 100000 件')
            source_after = source['unit_cap'] - data.transferred_units
            target_after = target['unit_cap'] + data.transferred_units
            cur.execute('UPDATE promotion_plans SET unit_cap=%s WHERE id=%s',
                        (source_after, source['id']))
            cur.execute('UPDATE promotion_plans SET unit_cap=%s WHERE id=%s',
                        (target_after, target['id']))
            cur.execute('''INSERT INTO promotion_budget_transfers
                (request_key,source_plan_id,target_plan_id,transferred_units,
                 source_unit_discount,target_unit_discount,
                 source_cap_before,source_cap_after,target_cap_before,target_cap_after,
                 note,created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''', (
                data.request_key, source['id'], target['id'], data.transferred_units,
                source['unit_discount'], target['unit_discount'],
                source['unit_cap'], source_after, target['unit_cap'], target_after,
                data.note or None, user['id'],
            ))
            transfer_id = cur.lastrowid
            moved_budget = data.transferred_units * source['unit_discount']
            audit(cur, user, 'transfer_promotion_budget', 'promotion_budget_transfer', transfer_id,
                  f'档期 #{source["id"]} → #{target["id"]}，划拨 {data.transferred_units} 件，'
                  f'预算 ¥{moved_budget}；调出限量 {source["unit_cap"]}→{source_after}，'
                  f'调入限量 {target["unit_cap"]}→{target_after}')
    except IntegrityError as exc:
        if exc.args[0] == 1062 and 'request_key' in str(exc):
            # Lost an insert race against a concurrent identical request:
            # replay the winner instead of failing the retry.
            winner = fetch_one('SELECT * FROM promotion_budget_transfers WHERE request_key=%s',
                               (data.request_key,))
            if winner:
                return {'id': winner['id'], 'replayed': True,
                        'transferred_units': winner['transferred_units']}
        raise
    return {'id': transfer_id, 'replayed': False, 'transferred_units': data.transferred_units,
            'source_cap_after': source_after, 'target_cap_after': target_after}
