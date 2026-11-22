import json, os, time
from datetime import datetime, timezone
try:
    import redis
    from .config import REDIS_URL
except Exception: redis=None; REDIS_URL=''
os.makedirs('/shared', exist_ok=True)
while True:
    payload={'service':'basket-rule-worker','heartbeat':datetime.now(timezone.utc).isoformat(),'queue':'promotion-review'}
    with open('/shared/worker-heartbeat.json','w') as f: json.dump(payload,f)
    if redis:
        try: redis.Redis.from_url(REDIS_URL).set('basket-rule-worker:last-heartbeat', payload['heartbeat'], ex=60)
        except Exception: pass
    time.sleep(8)
