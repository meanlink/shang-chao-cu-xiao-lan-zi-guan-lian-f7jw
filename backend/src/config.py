import os

MYSQL = {
    "host": os.getenv("MYSQL_HOST", "127.0.0.1"),
    "port": int(os.getenv("MYSQL_PORT", "3306")),
    "user": os.getenv("MYSQL_USER", "app"),
    "password": os.getenv("MYSQL_PASSWORD", "app_pass"),
    "database": os.getenv("MYSQL_DATABASE", "supermarket_basket"),
    "charset": "utf8mb4",
    "cursorclass": None,
    "autocommit": True,
}
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
SEED_DEMO = os.getenv("SEED_DEMO", "true").lower() == "true"
JWT_SECRET = "supermarket-basket-rules-demo-secret"
