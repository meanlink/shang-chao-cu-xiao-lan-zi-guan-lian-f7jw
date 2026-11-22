"""Convert the rule's antecedent families into enforceable offer terms."""

from fastapi import HTTPException

from ..constants.enums import PromotionStatus
from ..db import transaction
from .promotion import audit, locked_plan, one


def configure(plan_id, data, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if plan['status'] != PromotionStatus.planned:
            raise HTTPException(409, '仅可在开档前设置购物篮门槛')
        if data.per_receipt_cap > plan['unit_cap']:
            raise HTTPException(422, '单票折扣上限不能超过档期总限量')
        rule = one(cur, 'SELECT antecedent FROM association_rules WHERE id=%s', (plan['rule_id'],))
        families = set(rule['antecedent'].split(' + '))
        if families != data.minimums.keys():
            raise HTTPException(422, '须为已发布规则的每个前件商品族填写件数')
        placeholders = ','.join(['%s'] * len(families))
        cur.execute(f'SELECT id, name FROM product_families WHERE active=1 AND name IN ({placeholders})',
                    tuple(sorted(families)))
        rows = cur.fetchall()
        if {row['name'] for row in rows} != families:
            raise HTTPException(409, '规则的前件商品族已不可用，请核对商品目录')
        cur.execute('''INSERT INTO basket_offers (plan_id,per_receipt_cap,configured_by)
                       VALUES (%s,%s,%s) AS incoming
                       ON DUPLICATE KEY UPDATE per_receipt_cap=incoming.per_receipt_cap,
                           configured_by=incoming.configured_by,configured_at=UTC_TIMESTAMP()''',
                    (plan_id, data.per_receipt_cap, user['id']))
        cur.execute('DELETE FROM basket_offer_requirements WHERE plan_id=%s', (plan_id,))
        cur.executemany('''INSERT INTO basket_offer_requirements (plan_id,family_id,minimum_units)
                           VALUES (%s,%s,%s)''',
                        [(plan_id, row['id'], data.minimums[row['name']]) for row in rows])
        terms = '、'.join(f'{name} {minimum} 件' for name, minimum in sorted(data.minimums.items()))
        audit(cur, user, 'configure_basket_offer', 'promotion_plan', plan_id,
              f'{terms}，单票最多 {data.per_receipt_cap} 件'[:500])
    return {'plan_id': plan_id, 'per_receipt_cap': data.per_receipt_cap, 'minimums': data.minimums}
