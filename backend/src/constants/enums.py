from enum import Enum

class UserRole(str, Enum):
    analyst = "analyst"
    manager = "manager"
    store_operator = "store_operator"

class RuleStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    blocked = "blocked"
    published = "published"


class PromotionStatus(str, Enum):
    planned = 'planned'
    active = 'active'
    settling = 'settling'
    closed = 'closed'
    cancelled = 'cancelled'


class SettlementStatus(str, Enum):
    submitted = 'submitted'
    returned = 'returned'
    confirmed = 'confirmed'
