"""Evaluate one complete POS basket against the frozen offer and stock cap."""

from collections import Counter

from fastapi import HTTPException

from ..constants.enums import PromotionStatus
from .basket_ledger import CATALOG, ledger_units
from .promotion import one


def qualify(cur, plan, lines, today):
    if plan['status'] != PromotionStatus.active or not plan['starts_on'] <= today <= plan['ends_on']:
        raise HTTPException(409, '只有档期内已开档的促销可核定小票')
    offer = one(cur, 'SELECT per_receipt_cap FROM basket_offers WHERE plan_id=%s', (plan['id'],))
    if not offer:
        raise HTTPException(409, '该档期使用汇总对账，未启用逐票核销')
    cur.execute('''SELECT f.id, f.name, q.minimum_units FROM basket_offer_requirements q
                   JOIN product_families f ON f.id=q.family_id WHERE q.plan_id=%s ORDER BY f.name''', (plan['id'],))
    requirements = cur.fetchall()
    submitted = {line.sku: line.quantity for line in lines}
    placeholders = ','.join(['%s'] * len(submitted))
    cur.execute(f'{CATALOG} AND p.sku IN ({placeholders})', tuple(submitted))
    products = {product['sku'].upper(): product for product in cur.fetchall()}
    unavailable = sorted(submitted.keys() - products.keys())
    if unavailable:
        raise HTTPException(422, f'小票包含不可用 SKU：{"、".join(unavailable)}')

    family_units = Counter()
    reward_quantity = 0
    for sku, quantity in submitted.items():
        product = products[sku]
        if product['id'] == plan['product_id']:
            reward_quantity = quantity
        else:
            family_units[product['family_id']] += quantity
    missing = [f"{item['name']}还差 {item['minimum_units'] - family_units[item['id']]} 件"
               for item in requirements if family_units[item['id']] < item['minimum_units']]
    if missing:
        raise HTTPException(422, f'小票未达到前件门槛：{"、".join(missing)}')
    if not reward_quantity:
        raise HTTPException(422, '小票缺少本档期的立减 SKU')
    units = min(reward_quantity, offer['per_receipt_cap'])
    remaining = plan['unit_cap'] - ledger_units(cur, plan['id'])
    if units > remaining:
        raise HTTPException(409, f'档期只剩 {remaining} 件额度，本票需 {units} 件')
    return {
        'rewarded_units': units, 'discount_amount': units * plan['unit_discount'],
        'remaining_after': remaining - units,
        'lines': [{'sku': sku, 'quantity': submitted[sku], 'product_id': products[sku]['id']}
                  for sku in sorted(submitted)],
    }
