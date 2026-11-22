"""Atomic budget transfers between two in-flight promotions for the same SKU."""

BUDGET_TRANSFER_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS promotion_budget_transfers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        request_key VARCHAR(64) NOT NULL UNIQUE,
        source_plan_id INT NOT NULL,
        target_plan_id INT NOT NULL,
        transferred_units INT NOT NULL,
        target_units INT NOT NULL,
        transfer_amount DECIMAL(10,2) NOT NULL,
        source_unit_discount DECIMAL(10,2) NOT NULL,
        target_unit_discount DECIMAL(10,2) NOT NULL,
        source_cap_before INT NOT NULL,
        source_cap_after INT NOT NULL,
        target_cap_before INT NOT NULL,
        target_cap_after INT NOT NULL,
        note VARCHAR(240) NULL,
        created_by INT NOT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_transfer_source FOREIGN KEY (source_plan_id)
            REFERENCES promotion_plans(id),
        CONSTRAINT fk_transfer_target FOREIGN KEY (target_plan_id)
            REFERENCES promotion_plans(id),
        CONSTRAINT fk_transfer_operator FOREIGN KEY (created_by) REFERENCES users(id),
        CHECK (transferred_units BETWEEN 1 AND 100000),
        CHECK (source_plan_id <> target_plan_id),
        CHECK (source_cap_after = source_cap_before - transferred_units),
        CHECK (target_cap_after = target_cap_before + target_units),
        CHECK (source_cap_before >= 1 AND source_cap_after >= 1),
        CHECK (target_cap_before >= 1 AND target_cap_after <= 100000),
        KEY ix_transfer_plans (source_plan_id, target_plan_id)
    )""",
]
