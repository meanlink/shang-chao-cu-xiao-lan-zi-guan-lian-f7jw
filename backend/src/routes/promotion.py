from fastapi import APIRouter, Depends

from ..schemas.promotion import BudgetTransferIn, PromotionPlanIn, SettlementIn, SettlementReviewIn
from ..security import current_user, require_roles
from ..services import budget_transfer, promotion

router = APIRouter(prefix='/promotions', tags=['promotions'])
manager = Depends(require_roles('manager'))
operator = Depends(require_roles('store_operator'))
reader = Depends(current_user)


@router.get('/plan-options')
def plan_options(user=manager):
    return promotion.plan_options()


@router.get('/plans')
def list_plans(user=reader):
    return promotion.list_plans(user)


@router.post('/plans', status_code=201)
def create_plan(data: PromotionPlanIn, user=manager):
    return promotion.create_plan(data, user)


@router.post('/plans/{plan_id}/activate')
def activate_plan(plan_id: int, user=operator):
    return promotion.activate_plan(plan_id, user)


@router.post('/plans/{plan_id}/cancel')
def cancel_plan(plan_id: int, user=manager):
    return promotion.cancel_plan(plan_id, user)


@router.get('/settlements')
def list_settlements(user=reader):
    return promotion.list_settlements(user)


@router.post('/settlements/{plan_id}/submit')
def submit_settlement(plan_id: int, data: SettlementIn, user=operator):
    return promotion.submit_settlement(plan_id, data, user)


@router.post('/settlements/{plan_id}/review')
def review_settlement(plan_id: int, data: SettlementReviewIn, user=manager):
    return promotion.review_settlement(plan_id, data, user)


@router.get('/budget-transfer/plans')
def transferable_plans(user=reader):
    return budget_transfer.transferable_plans(user)


@router.get('/budget-transfer/history')
def transfer_history(plan_id: int | None = None, user=reader):
    return budget_transfer.transfer_history(plan_id)


@router.post('/budget-transfer', status_code=201)
def transfer_budget(data: BudgetTransferIn, user=manager):
    return budget_transfer.transfer_budget(data, user)
