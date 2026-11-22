"""Atomically book or reverse a POS receipt against a store promotion."""

from fastapi import HTTPException
from pymysql.err import IntegrityError

from ..constants.enums import PromotionStatus
from ..db import transaction
from .basket_qualification import qualify
from .promotion import audit, business_today, locked_plan, one


def preview(plan_id, data, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if existing_receipt(cur, plan, data.receipt_no):
            raise HTTPException(409, '该门店已登记此小票号，请查看核销流水')
        result = qualify(cur, plan, data.lines, business_today())
        return {key: result[key] for key in ('rewarded_units', 'discount_amount', 'remaining_after')}


def existing_receipt(cur, plan, reference):
    return one(cur, '''SELECT id, plan_id, rewarded_units, discount_amount, voided_at FROM basket_receipts
                       WHERE store_id=%s AND receipt_no=%s''', (plan['store_id'], reference))


def record(plan_id, data, user):
    try:
        with transaction() as cur:
            plan = locked_plan(cur, plan_id, user)
            existing = existing_receipt(cur, plan, data.receipt_no)
            if existing:
                if existing['plan_id'] == plan_id:
                    cur.execute('SELECT sku, quantity FROM basket_receipt_lines WHERE receipt_id=%s', (existing['id'],))
                    previous = {row['sku']: row['quantity'] for row in cur.fetchall()}
                    if previous == {line.sku: line.quantity for line in data.lines}:
                        return {**existing, 'replayed': True}
                raise HTTPException(409, '该门店已登记此小票号，档期或明细与原流水不同')
            today = business_today()
            result = qualify(cur, plan, data.lines, today)
            cur.execute('''INSERT INTO basket_receipts
                           (plan_id,store_id,receipt_no,business_date,rewarded_units,discount_amount,recorded_by)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)''',
                        (plan_id, plan['store_id'], data.receipt_no, today, result['rewarded_units'],
                         result['discount_amount'], user['id']))
            receipt_id = cur.lastrowid
            cur.executemany('INSERT INTO basket_receipt_lines (receipt_id,product_id,sku,quantity) VALUES (%s,%s,%s,%s)',
                            [(receipt_id, line['product_id'], line['sku'], line['quantity']) for line in result['lines']])
            audit(cur, user, 'record_basket_receipt', 'basket_receipt', receipt_id,
                  f"{data.receipt_no}，{result['rewarded_units']} 件，立减 ¥{result['discount_amount']}")
            return {'id': receipt_id, 'plan_id': plan_id, 'rewarded_units': result['rewarded_units'],
                    'discount_amount': result['discount_amount'], 'voided_at': None, 'replayed': False}
    except IntegrityError as exc:
        if exc.args[0] == 1062 and 'uq_store_basket_receipt' in str(exc):
            raise HTTPException(409, '该门店已登记此小票号，请核对原流水') from exc
        raise


def void(plan_id, receipt_id, data, user):
    with transaction() as cur:
        plan = locked_plan(cur, plan_id, user)
        if plan['status'] != PromotionStatus.active:
            raise HTTPException(409, '待复核或已结档的流水已冻结')
        receipt = one(cur, 'SELECT id, receipt_no, voided_at FROM basket_receipts WHERE id=%s AND plan_id=%s',
                      (receipt_id, plan_id))
        if not receipt:
            raise HTTPException(404, '该档期没有这笔小票')
        if receipt['voided_at']:
            raise HTTPException(409, '该小票已作废')
        cur.execute('''UPDATE basket_receipts SET voided_by=%s,voided_at=UTC_TIMESTAMP(),void_reason=%s
                       WHERE id=%s''', (user['id'], data.reason, receipt_id))
        audit(cur, user, 'void_basket_receipt', 'basket_receipt', receipt_id,
              f"{receipt['receipt_no']}，{data.reason}")
    return {'id': receipt_id, 'status': 'voided'}
