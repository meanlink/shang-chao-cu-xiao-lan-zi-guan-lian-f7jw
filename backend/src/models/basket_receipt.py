"""Receipt journal and the POS lines used to qualify each discount."""

BASKET_RECEIPT_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS basket_receipts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        plan_id INT NOT NULL,
        store_id INT NOT NULL,
        receipt_no VARCHAR(40) NOT NULL,
        business_date DATE NOT NULL,
        rewarded_units INT NOT NULL,
        discount_amount DECIMAL(12,2) NOT NULL,
        recorded_by INT NOT NULL,
        recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        voided_by INT NULL,
        voided_at DATETIME NULL,
        void_reason VARCHAR(240) NULL,
        FOREIGN KEY (plan_id) REFERENCES basket_offers(plan_id),
        FOREIGN KEY (plan_id, store_id) REFERENCES promotion_plans(id, store_id),
        FOREIGN KEY (recorded_by) REFERENCES users(id),
        FOREIGN KEY (voided_by) REFERENCES users(id),
        UNIQUE KEY uq_store_basket_receipt (store_id, receipt_no),
        KEY ix_basket_plan_ledger (plan_id, voided_at),
        CHECK (rewarded_units BETWEEN 1 AND 100),
        CHECK (discount_amount > 0),
        CHECK ((voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL)
            OR (voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL))
    )""",
    """CREATE TABLE IF NOT EXISTS basket_receipt_lines (
        receipt_id INT NOT NULL,
        product_id INT NOT NULL,
        sku VARCHAR(30) NOT NULL,
        quantity INT NOT NULL,
        PRIMARY KEY (receipt_id, product_id),
        FOREIGN KEY (receipt_id) REFERENCES basket_receipts(id),
        FOREIGN KEY (product_id) REFERENCES products(id),
        CHECK (quantity BETWEEN 1 AND 100)
    )""",
]
