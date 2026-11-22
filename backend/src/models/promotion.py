"""Additive schema for store activations and their POS reconciliation."""

PROMOTION_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS promotion_plans (
        id INT AUTO_INCREMENT PRIMARY KEY,
        rule_id INT NOT NULL,
        store_id INT NOT NULL,
        product_id INT NOT NULL,
        operator_id INT NOT NULL,
        created_by INT NOT NULL,
        starts_on DATE NOT NULL,
        ends_on DATE NOT NULL,
        list_price DECIMAL(10,2) NOT NULL,
        unit_discount DECIMAL(10,2) NOT NULL,
        unit_cap INT NOT NULL,
        status ENUM('planned','active','settling','closed','cancelled') NOT NULL DEFAULT 'planned',
        started_at DATETIME NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (rule_id) REFERENCES association_rules(id),
        FOREIGN KEY (store_id) REFERENCES stores(id),
        FOREIGN KEY (product_id) REFERENCES products(id),
        FOREIGN KEY (operator_id) REFERENCES users(id),
        FOREIGN KEY (created_by) REFERENCES users(id),
        UNIQUE KEY uq_plan_store (id, store_id),
        KEY ix_promotion_window (store_id, product_id, starts_on, ends_on),
        CHECK (DATEDIFF(ends_on, starts_on) BETWEEN 0 AND 30),
        CHECK (unit_cap BETWEEN 1 AND 100000),
        CHECK (unit_discount > 0 AND unit_discount * 2 <= list_price)
    )""",
    """CREATE TABLE IF NOT EXISTS promotion_settlements (
        id INT AUTO_INCREMENT PRIMARY KEY,
        plan_id INT NOT NULL UNIQUE,
        store_id INT NOT NULL,
        pos_reference VARCHAR(40) NOT NULL,
        redeemed_units INT NOT NULL,
        settlement_unit_cap INT NULL,
        settlement_unit_discount DECIMAL(10,2) NULL,
        settlement_list_price DECIMAL(10,2) NULL,
        note VARCHAR(240) NOT NULL,
        status ENUM('submitted','returned','confirmed') NOT NULL DEFAULT 'submitted',
        submitted_by INT NOT NULL,
        reviewed_by INT NULL,
        review_note VARCHAR(240) NULL,
        submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        reviewed_at DATETIME NULL,
        FOREIGN KEY (plan_id, store_id) REFERENCES promotion_plans(id, store_id),
        FOREIGN KEY (submitted_by) REFERENCES users(id),
        FOREIGN KEY (reviewed_by) REFERENCES users(id),
        UNIQUE KEY uq_store_pos (store_id, pos_reference),
        CHECK (redeemed_units BETWEEN 0 AND 100000)
    )""",
]


PROMOTION_MIGRATIONS = [
    'ALTER TABLE promotion_settlements ADD COLUMN settlement_unit_cap INT NULL',
    'ALTER TABLE promotion_settlements ADD COLUMN settlement_unit_discount DECIMAL(10,2) NULL',
    'ALTER TABLE promotion_settlements ADD COLUMN settlement_list_price DECIMAL(10,2) NULL',
]
