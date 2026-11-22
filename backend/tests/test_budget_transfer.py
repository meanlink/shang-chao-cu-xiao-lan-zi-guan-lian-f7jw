import threading
import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException

from src.db import fetch_one, transaction
from src.schemas.promotion import BudgetTransferIn
from src.services import budget_transfer

from conftest import make_plan, enable_basket_offer, book_receipt, auth_header, user_row, TODAY


def transfer_in(source, target, units, **over):
    payload = {'source_plan_id': source, 'target_plan_id': target, 'transferred_units': units,
               'request_key': uuid.uuid4().hex}
    payload.update(over)
    return BudgetTransferIn(**payload)


def caps(source, target):
    s = fetch_one('SELECT unit_cap FROM promotion_plans WHERE id=%s', (source,))['unit_cap']
    t = fetch_one('SELECT unit_cap FROM promotion_plans WHERE id=%s', (target,))['unit_cap']
    return s, t


# ---------- happy path ----------

def test_transfer_moves_both_caps_and_leaves_audit_trail(pair, users):
    src, dst = pair['source'], pair['target']
    assert caps(src, dst) == (20, 10)
    result = budget_transfer.transfer_budget(transfer_in(src, dst, 6), user_row(users['manager']['id']))
    assert result['replayed'] is False
    assert caps(src, dst) == (14, 16)
    row = fetch_one('SELECT * FROM promotion_budget_transfers WHERE id=%s', (result['id'],))
    assert (row['source_cap_before'], row['source_cap_after'],
            row['target_cap_before'], row['target_cap_after']) == (20, 14, 10, 16)
    assert row['source_unit_discount'] == row['target_unit_discount'] == 5
    log = fetch_one('SELECT action,detail FROM audit_logs WHERE entity_type=%s ORDER BY id DESC LIMIT 1',
                    ('promotion_budget_transfer',))
    assert log['action'] == 'transfer_promotion_budget' and '#%s' % src in log['detail']


def test_transfer_history_shows_both_balances(pair, users):
    src, dst = pair['source'], pair['target']
    budget_transfer.transfer_budget(transfer_in(src, dst, 3), user_row(users['manager']['id']))
    history = budget_transfer.transfer_history()
    assert len(history) == 1
    h = history[0]
    assert h['source_cap_before'] == 20 and h['source_cap_after'] == 17
    assert h['target_cap_before'] == 10 and h['target_cap_after'] == 13
    assert h['sku'] == 'BK-001'
    # plan-scoped history works from either side
    assert len(budget_transfer.transfer_history(src)) == 1
    assert len(budget_transfer.transfer_history(dst)) == 1


def test_eligible_plans_pair_same_sku_same_discount(pair, catalog, users):
    # different discount -> not a partner
    other_discount = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-001'], 4.00, 8,
                               users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(other_discount, users['manager']['id'])
    # different SKU -> not a partner
    other_sku = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-002'], 5.00, 8,
                          users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(other_sku, users['manager']['id'])
    plans = {p['id']: p for p in budget_transfer.transferable_plans(user_row(users['manager']['id']))}
    assert plans[pair['source']]['partners'] == [pair['target']]
    assert plans[pair['target']]['partners'] == [pair['source']]
    assert plans[other_discount]['partners'] == []
    assert plans[other_sku]['partners'] == []
    assert plans[pair['source']]['remaining_units'] == 20


def test_operator_sees_own_plan_and_its_counterpart(pair, users):
    # The source belongs to the first operator, the target to the second one.
    rows = budget_transfer.transferable_plans(user_row(users['store_operator']['id']))
    ids = {r['id'] for r in rows}
    assert ids == {pair['source'], pair['target']}
    by_id = {r['id']: r for r in rows}
    assert by_id[pair['source']]['partners'] == [pair['target']]


# ---------- eligibility rejections ----------

def test_reject_different_sku(pair, catalog, users):
    other = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-002'], 5.00, 8,
                      users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(other, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], other, 2),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 422 and '同款' in exc.value.detail
    assert caps(pair['source'], pair['target']) == (20, 10)


def test_reject_different_unit_discount(pair, catalog, users):
    other = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-001'], 4.50, 8,
                      users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(other, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], other, 2),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 422 and '单件立减' in exc.value.detail
    assert caps(pair['source'], pair['target']) == (20, 10)


def test_reject_same_store(pair, catalog, users):
    same_store = make_plan(catalog['stores']['BJ-HS'], catalog['products']['BK-001'], 5.00, 9,
                           users['store_operator']['id'], users['manager']['id'])
    enable_basket_offer(same_store, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], same_store, 2),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 422 and '两家不同门店' in exc.value.detail


def test_reject_closed_or_out_of_window_plan(pair, catalog, users):
    closed = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-001'], 5.00, 8,
                       users['store_operator_east']['id'], users['manager']['id'], status='closed')
    enable_basket_offer(closed, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], closed, 1),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 409 and '仍在执行' in exc.value.detail
    expired = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-001'], 5.00, 8,
                        users['store_operator_east']['id'], users['manager']['id'],
                        starts_on=TODAY - timedelta(days=20), ends_on=TODAY - timedelta(days=2))
    enable_basket_offer(expired, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], expired, 1),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 409 and '档期日期' in exc.value.detail


def test_settling_plan_can_still_transfer(pair, users):
    with transaction() as cur:
        cur.execute("UPDATE promotion_plans SET status='settling' WHERE id=%s", (pair['target'],))
    result = budget_transfer.transfer_budget(transfer_in(pair['source'], pair['target'], 2),
                                             user_row(users['manager']['id']))
    assert result['transferred_units'] == 2
    assert caps(pair['source'], pair['target']) == (18, 12)


# ---------- no overdraw ----------

def test_cannot_transfer_more_than_remaining_units(pair, users):
    book_receipt(pair['source'], 1, users['store_operator']['id'], 'BK-001', 17)  # cap 20 -> 3 remaining
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], pair['target'], 4),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 409 and '3 件' in exc.value.detail
    assert caps(pair['source'], pair['target']) == (20, 10)


def test_source_must_keep_one_unit(pair, users):
    # 20 cap, no receipts: transferring 20 would empty the source
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], pair['target'], 20),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 422 and '保留 1 件' in exc.value.detail
    assert caps(pair['source'], pair['target']) == (20, 10)


def test_target_cap_ceiling_enforced(pair, catalog, users):
    # A target already sitting at the plan-level cap cannot absorb any units.
    full = make_plan(catalog['stores']['SH-XH'], catalog['products']['BK-001'], 5.00, 100000,
                     users['store_operator_east']['id'], users['manager']['id'])
    enable_basket_offer(full, users['manager']['id'])
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(transfer_in(pair['source'], full, 1),
                                        user_row(users['manager']['id']))
    assert exc.value.status_code == 422 and '100000' in exc.value.detail


# ---------- idempotency ----------

def test_retry_with_same_request_key_does_not_double_transfer(pair, users):
    data = transfer_in(pair['source'], pair['target'], 4)
    first = budget_transfer.transfer_budget(data, user_row(users['manager']['id']))
    second = budget_transfer.transfer_budget(data, user_row(users['manager']['id']))
    third = budget_transfer.transfer_budget(data, user_row(users['manager']['id']))
    assert first['id'] == second['id'] == third['id']
    assert second['replayed'] is True
    assert caps(pair['source'], pair['target']) == (16, 14)
    assert fetch_one('SELECT COUNT(*) c FROM promotion_budget_transfers')['c'] == 1


def test_same_request_key_with_different_payload_rejected(pair, users):
    data = transfer_in(pair['source'], pair['target'], 4)
    budget_transfer.transfer_budget(data, user_row(users['manager']['id']))
    hijacked = transfer_in(pair['source'], pair['target'], 5, request_key=data.request_key)
    with pytest.raises(HTTPException) as exc:
        budget_transfer.transfer_budget(hijacked, user_row(users['manager']['id']))
    assert exc.value.status_code == 409 and '另一笔调拨' in exc.value.detail
    assert caps(pair['source'], pair['target']) == (16, 14)


# ---------- concurrency ----------

def test_concurrent_transfers_and_receipts_never_overdraw(pair, users):
    src, dst = pair['source'], pair['target']
    errors, results = [], []

    def do_transfer(units):
        try:
            results.append(budget_transfer.transfer_budget(
                transfer_in(src, dst, units), user_row(users['manager']['id'])))
        except HTTPException as exc:
            errors.append(exc.status_code)

    def do_receipt(units, no):
        try:
            class Line:  # minimal stand-in matching qualification-free direct booking
                pass
            book_receipt(src, 1, users['store_operator']['id'], 'BK-001', units, receipt_no=f'CC-{no}')
        except Exception as exc:  # pragma: no cover - booking here is raw SQL, always fits
            errors.append(exc)

    threads = [threading.Thread(target=do_transfer, args=(6,)) for _ in range(3)]
    threads += [threading.Thread(target=do_receipt, args=(2, i)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Source: cap 20, two receipts take 4 units, three transfers of 6 each = 18;
    # remaining must stay non-negative and only the transfer fitting the cap lands.
    source = fetch_one('SELECT unit_cap cap FROM promotion_plans WHERE id=%s', (src,))
    used = fetch_one('SELECT COALESCE(SUM(rewarded_units),0) u FROM basket_receipts '
                     'WHERE plan_id=%s AND voided_at IS NULL', (src,))['u']
    moved = fetch_one('SELECT COALESCE(SUM(transferred_units),0) m FROM promotion_budget_transfers '
                      'WHERE source_plan_id=%s', (src,))['m']
    assert source['cap'] == 20 - moved
    assert used + moved <= 20
    assert moved <= 16  # at least one unit of headroom remains
    successful = [r for r in results if not r['replayed']]
    assert len(successful) >= 1
    # failing sides left no partial rows
    assert fetch_one('SELECT COUNT(*) c FROM promotion_budget_transfers')['c'] == len(successful)


def test_opposite_direction_concurrent_transfers_deadlock_free(pair, users):
    src, dst = pair['source'], pair['target']
    outcomes = []

    def forward():
        try:
            budget_transfer.transfer_budget(transfer_in(src, dst, 2),
                                            user_row(users['manager']['id']))
            outcomes.append('ok')
        except HTTPException as exc:
            outcomes.append(exc.status_code)

    def backward():
        try:
            budget_transfer.transfer_budget(transfer_in(dst, src, 1),
                                            user_row(users['manager']['id']))
            outcomes.append('ok')
        except HTTPException as exc:
            outcomes.append(exc.status_code)

    threads = [threading.Thread(target=forward), threading.Thread(target=backward)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert all(t.is_alive() is False for t in threads)
    assert outcomes.count('ok') >= 1
    # books always balance: total caps unchanged
    s, t = caps(src, dst)
    assert s + t == 30


# ---------- downstream behaviour ----------

def test_new_receipt_respects_transferred_cap(pair, users):
    src, dst = pair['source'], pair['target']
    budget_transfer.transfer_budget(transfer_in(src, dst, 15), user_row(users['manager']['id']))
    assert caps(src, dst) == (5, 25)
    # target can now redeem beyond its original cap of 10
    book_receipt(dst, 2, users['store_operator_east']['id'], 'BK-001', 12, receipt_no='DST-12')
    assert fetch_one('SELECT rewarded_units u FROM basket_receipts WHERE receipt_no=%s',
                     ('DST-12',))['u'] == 12
    # source overdraw against the reduced cap is rejected via qualification path
    from src.services.basket_ledger import ledger_units
    with transaction() as cur:
        assert ledger_units(cur, dst) == 12


def test_historical_receipt_keeps_original_amount_after_transfer(pair, users):
    src, dst = pair['source'], pair['target']
    before = book_receipt(src, 1, users['store_operator']['id'], 'BK-001', 3, receipt_no='OLD-1')
    original = fetch_one('SELECT discount_amount d FROM basket_receipts WHERE id=%s', (before,))['d']
    budget_transfer.transfer_budget(transfer_in(src, dst, 10), user_row(users['manager']['id']))
    again = fetch_one('SELECT discount_amount d FROM basket_receipts WHERE id=%s', (before,))['d']
    assert again == original == 15.00


def test_receipt_booking_api_enforces_reduced_cap_and_uses_expanded_cap(pair, users):
    """End-to-end through the qualification service (not raw SQL)."""
    from fastapi.testclient import TestClient
    from src.main import app
    src, dst = pair['source'], pair['target']
    # Move 17 of src's 20 units away: src cap -> 3, dst cap -> 27.
    budget_transfer.transfer_budget(transfer_in(src, dst, 17),
                                    user_row(users['manager']['id']))
    assert caps(src, dst) == (3, 27)
    client = TestClient(app)
    headers = auth_header(user_row(users['store_operator']['id']))
    # Each basket needs one dairy antecedent plus the rewarded bakery SKU.
    payload = {'receipt_no': 'HTTP-001',
               'lines': [{'sku': 'ML-001', 'quantity': 1}, {'sku': 'BK-001', 'quantity': 5}]}
    # src only has 3 units of headroom -> a 5-unit reward must be refused.
    r = client.post(f'/basket-offers/plans/{src}/receipts', json=payload, headers=headers)
    assert r.status_code == 409 and '3 件' in r.json()['detail']
    assert fetch_one('SELECT COUNT(*) c FROM basket_receipts WHERE plan_id=%s', (src,))['c'] == 0
    # dst can redeem past its original cap of 10 (now 27); the per-receipt cap
    # of 10 still applies to a single ticket.
    dst_headers = auth_header(user_row(users['store_operator_east']['id']))
    r = client.post(f'/basket-offers/plans/{dst}/receipts',
                    json={'receipt_no': 'HTTP-002',
                          'lines': [{'sku': 'ML-001', 'quantity': 1}, {'sku': 'BK-001', 'quantity': 12}]},
                    headers=dst_headers)
    if r.status_code != 201:
        raise AssertionError(f'dst booking failed {r.status_code}: {r.text}')
    assert r.json()['rewarded_units'] == 10
    # A second ticket keeps accumulating against the expanded 27-unit cap,
    # which would have been impossible under the original cap of 10.
    r = client.post(f'/basket-offers/plans/{dst}/receipts',
                    json={'receipt_no': 'HTTP-004',
                          'lines': [{'sku': 'ML-001', 'quantity': 1}, {'sku': 'BK-001', 'quantity': 5}]},
                    headers=dst_headers)
    assert r.status_code == 201 and r.json()['rewarded_units'] == 5
    from src.services.basket_ledger import ledger_units
    with transaction() as cur:
        assert ledger_units(cur, dst) == 15
    assert fetch_one('SELECT unit_cap c FROM promotion_plans WHERE id=%s', (dst,))['c'] == 27
    # src can still book within its reduced 3-unit cap.
    r = client.post(f'/basket-offers/plans/{src}/receipts',
                    json={'receipt_no': 'HTTP-003',
                          'lines': [{'sku': 'ML-001', 'quantity': 1}, {'sku': 'BK-001', 'quantity': 3}]},
                    headers=headers)
    assert r.status_code == 201 and r.json()['rewarded_units'] == 3


def test_replay_safe_against_concurrent_same_key(pair, users):
    data = transfer_in(pair['source'], pair['target'], 3)
    holder = threading.Event()
    seen = []

    def first():
        # block inside the transaction to force the second caller to wait on row locks
        real = budget_transfer.fetch_one

        def slow_fetch(sql, args=()):
            if 'request_key' in sql and not seen:
                seen.append(1)
                holder.wait(5)
            return real(sql, args)

        budget_transfer.fetch_one = slow_fetch
        try:
            budget_transfer.transfer_budget(data, user_row(users['manager']['id']))
        finally:
            budget_transfer.fetch_one = real

    t1 = threading.Thread(target=first)
    t1.start()
    # ensure t1 has passed its initial idempotency check, then race the same key
    holder.wait(0.2)
    t2 = threading.Thread(target=lambda: seen.append(
        budget_transfer.transfer_budget(data, user_row(users['manager']['id']))))
    t2.start()
    holder.set()
    t1.join(10)
    t2.join(10)
    assert caps(pair['source'], pair['target']) == (17, 13)
    assert fetch_one('SELECT COUNT(*) c FROM promotion_budget_transfers')['c'] == 1


# ---------- HTTP layer ----------

def test_http_role_guard_and_end_to_end(pair, users):
    from fastapi.testclient import TestClient
    from src.main import app
    client = TestClient(app)
    # operator cannot initiate a transfer
    r = client.post('/promotions/budget-transfer',
                    json={'source_plan_id': pair['source'], 'target_plan_id': pair['target'],
                          'transferred_units': 2, 'request_key': uuid.uuid4().hex},
                    headers=auth_header(user_row(users['store_operator']['id'])))
    assert r.status_code == 403
    # manager succeeds
    r = client.post('/promotions/budget-transfer',
                    json={'source_plan_id': pair['source'], 'target_plan_id': pair['target'],
                          'transferred_units': 2, 'request_key': uuid.uuid4().hex},
                    headers=auth_header(user_row(users['manager']['id'])))
    assert r.status_code == 201 and r.json()['source_cap_after'] == 18
    # read endpoints available to any logged-in role
    r = client.get('/promotions/budget-transfer/plans',
                   headers=auth_header(user_row(users['analyst']['id'])))
    assert r.status_code == 200 and len(r.json()) == 2
    r = client.get('/promotions/budget-transfer/history',
                   headers=auth_header(user_row(users['store_operator']['id'])))
    assert r.status_code == 200 and r.json()[0]['transferred_units'] == 2
    # unauthenticated rejected
    assert client.get('/promotions/budget-transfer/history').status_code == 401


def test_http_idempotent_retry(pair, users):
    from fastapi.testclient import TestClient
    from src.main import app
    client = TestClient(app)
    body = {'source_plan_id': pair['source'], 'target_plan_id': pair['target'],
            'transferred_units': 2, 'request_key': uuid.uuid4().hex}
    headers = auth_header(user_row(users['manager']['id']))
    first = client.post('/promotions/budget-transfer', json=body, headers=headers)
    second = client.post('/promotions/budget-transfer', json=body, headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()['id'] == second.json()['id'] and second.json()['replayed'] is True
    assert caps(pair['source'], pair['target']) == (18, 12)
