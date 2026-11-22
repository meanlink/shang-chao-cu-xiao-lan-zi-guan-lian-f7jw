import time
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor
from .config import MYSQL
from .models.basket_offer import BASKET_OFFER_SCHEMA
from .models.basket_receipt import BASKET_RECEIPT_SCHEMA
from .models.promotion import PROMOTION_SCHEMA

SCHEMA = [
"""CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, email VARCHAR(120) UNIQUE NOT NULL, display_name VARCHAR(80) NOT NULL, role VARCHAR(30) NOT NULL, password_hash CHAR(64) NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
"""CREATE TABLE IF NOT EXISTS stores (id INT AUTO_INCREMENT PRIMARY KEY, code VARCHAR(20) UNIQUE NOT NULL, name VARCHAR(80) NOT NULL, region VARCHAR(40) NOT NULL, active TINYINT DEFAULT 1)""",
"""CREATE TABLE IF NOT EXISTS product_families (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(80) UNIQUE NOT NULL, category VARCHAR(50) NOT NULL, description VARCHAR(255), active TINYINT DEFAULT 1)""",
"""CREATE TABLE IF NOT EXISTS products (id INT AUTO_INCREMENT PRIMARY KEY, sku VARCHAR(30) UNIQUE NOT NULL, name VARCHAR(100) NOT NULL, family_id INT NOT NULL, price DECIMAL(10,2) NOT NULL, status VARCHAR(20) DEFAULT 'active', FOREIGN KEY (family_id) REFERENCES product_families(id))""",
"""CREATE TABLE IF NOT EXISTS basket_orders (id INT AUTO_INCREMENT PRIMARY KEY, external_id VARCHAR(60) UNIQUE NOT NULL, store_id INT NOT NULL, order_date DATE NOT NULL, total_amount DECIMAL(10,2) NOT NULL, source_file VARCHAR(120) NOT NULL, status VARCHAR(20) DEFAULT 'imported', FOREIGN KEY (store_id) REFERENCES stores(id))""",
"""CREATE TABLE IF NOT EXISTS basket_items (id INT AUTO_INCREMENT PRIMARY KEY, order_id INT NOT NULL, product_id INT NOT NULL, quantity INT NOT NULL, unit_price DECIMAL(10,2) NOT NULL, FOREIGN KEY (order_id) REFERENCES basket_orders(id), FOREIGN KEY (product_id) REFERENCES products(id), UNIQUE KEY uq_order_product(order_id, product_id))""",
"""CREATE TABLE IF NOT EXISTS association_rules (id INT AUTO_INCREMENT PRIMARY KEY, antecedent VARCHAR(255) NOT NULL, consequent VARCHAR(100) NOT NULL, support DECIMAL(8,4) NOT NULL, confidence DECIMAL(8,4) NOT NULL, lift DECIMAL(8,4) NOT NULL, store_scope VARCHAR(80) NOT NULL, store_consistent TINYINT NOT NULL DEFAULT 1, status VARCHAR(20) NOT NULL DEFAULT 'draft', source_run VARCHAR(60) NOT NULL, created_by INT NOT NULL, reviewed_by INT NULL, review_comment VARCHAR(255), published_at DATETIME NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (created_by) REFERENCES users(id), FOREIGN KEY (reviewed_by) REFERENCES users(id))""",
"""CREATE TABLE IF NOT EXISTS analysis_runs (id INT AUTO_INCREMENT PRIMARY KEY, run_key VARCHAR(60) UNIQUE NOT NULL, min_support DECIMAL(8,4) NOT NULL, min_confidence DECIMAL(8,4) NOT NULL, basket_count INT NOT NULL, rule_count INT NOT NULL, status VARCHAR(20) DEFAULT 'completed', created_by INT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (created_by) REFERENCES users(id))""",
"""CREATE TABLE IF NOT EXISTS audit_logs (id INT AUTO_INCREMENT PRIMARY KEY, actor_id INT, action VARCHAR(80) NOT NULL, entity_type VARCHAR(50) NOT NULL, entity_id INT, detail VARCHAR(500), created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (actor_id) REFERENCES users(id))""",
]

def connect():
    cfg = dict(MYSQL)
    cfg["cursorclass"] = DictCursor
    return pymysql.connect(**cfg)

def init_db():
    for attempt in range(30):
        try:
            with connect() as conn:
                with conn.cursor() as cur:
                    for sql in [*SCHEMA, *PROMOTION_SCHEMA, *BASKET_OFFER_SCHEMA, *BASKET_RECEIPT_SCHEMA]:
                        cur.execute(sql)
            return
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)

def fetch_all(sql, args=()):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

def fetch_one(sql, args=()):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()

def execute(sql, args=()):
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.lastrowid


@contextmanager
def transaction():
    with connect() as conn:
        conn.begin()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
