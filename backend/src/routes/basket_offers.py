from fastapi import APIRouter, Depends, Response

from ..schemas.basket_offer import BasketReceiptIn, OfferTermsIn, VoidReceiptIn
from ..security import current_user, require_roles
from ..services import basket_ledger, basket_receipts, basket_terms

router = APIRouter(prefix='/basket-offers', tags=['basket-offers'])
manager = Depends(require_roles('manager'))
operator = Depends(require_roles('store_operator'))
reader = Depends(current_user)


@router.get('/plans')
def plans(user=reader):
    return basket_ledger.desk_plans(user)


@router.get('/plans/{plan_id}')
def detail(plan_id: int, user=reader):
    return basket_ledger.desk_detail(plan_id, user)


@router.put('/plans/{plan_id}/terms')
def terms(plan_id: int, data: OfferTermsIn, user=manager):
    return basket_terms.configure(plan_id, data, user)


@router.post('/plans/{plan_id}/quote')
def quote(plan_id: int, data: BasketReceiptIn, user=operator):
    return basket_receipts.preview(plan_id, data, user)


@router.post('/plans/{plan_id}/receipts', status_code=201)
def record(plan_id: int, data: BasketReceiptIn, response: Response, user=operator):
    receipt = basket_receipts.record(plan_id, data, user)
    if receipt['replayed']:
        response.status_code = 200
    return receipt


@router.post('/plans/{plan_id}/receipts/{receipt_id}/void')
def void(plan_id: int, receipt_id: int, data: VoidReceiptIn, user=operator):
    return basket_receipts.void(plan_id, receipt_id, data, user)
