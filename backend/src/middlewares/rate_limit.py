import time
from collections import defaultdict
from starlette.middleware.base import BaseHTTPMiddleware
class SimpleRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app): super().__init__(app); self.hits=defaultdict(list)
    async def dispatch(self, request, call_next):
        key=request.client.host if request.client else 'unknown'; now=time.time(); self.hits[key]=[t for t in self.hits[key] if now-t<60]
        if len(self.hits[key])>=120: from fastapi.responses import JSONResponse; return JSONResponse({'detail':'请求过于频繁'},status_code=429)
        self.hits[key].append(now); return await call_next(request)
