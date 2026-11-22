from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis
from .db import init_db, fetch_one
from .config import REDIS_URL, SEED_DEMO
from .services.seed import seed_demo
from .middlewares.headers import SecurityHeadersMiddleware
from .middlewares.rate_limit import SimpleRateLimitMiddleware
from .routes import auth, basket_offers, catalog, orders, rules, reviews, dashboard, promotion
app=FastAPI(title="Supermarket Basket Rules API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SecurityHeadersMiddleware); app.add_middleware(SimpleRateLimitMiddleware)
app.include_router(auth.router); app.include_router(catalog.router); app.include_router(orders.router); app.include_router(rules.router); app.include_router(reviews.router); app.include_router(dashboard.router)
app.include_router(promotion.router)
app.include_router(basket_offers.router)
@app.on_event("startup")
def startup():
    init_db()
    if SEED_DEMO:
        try: seed_demo()
        except Exception as e: print('seed failed',e,flush=True)
@app.get('/health')
def health():
    db=fetch_one('SELECT 1 as ok')['ok']; redis_ok=0
    try: redis_ok=int(redis.Redis.from_url(REDIS_URL).ping())
    except Exception: pass
    return {'status':'ok','db':db,'redis':redis_ok}
