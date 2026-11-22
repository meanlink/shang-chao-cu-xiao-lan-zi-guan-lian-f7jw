"""Snapshot of the basket terms attached to a scheduled promotion."""

BASKET_OFFER_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS basket_offers (
        plan_id INT PRIMARY KEY,
        per_receipt_cap INT NOT NULL,
        configured_by INT NOT NULL,
        configured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (plan_id) REFERENCES promotion_plans(id),
        FOREIGN KEY (configured_by) REFERENCES users(id),
        CHECK (per_receipt_cap BETWEEN 1 AND 100)
    )""",
    """CREATE TABLE IF NOT EXISTS basket_offer_requirements (
        plan_id INT NOT NULL,
        family_id INT NOT NULL,
        minimum_units INT NOT NULL,
        PRIMARY KEY (plan_id, family_id),
        FOREIGN KEY (plan_id) REFERENCES basket_offers(plan_id),
        FOREIGN KEY (family_id) REFERENCES product_families(id),
        CHECK (minimum_units BETWEEN 1 AND 100)
    )""",
]
