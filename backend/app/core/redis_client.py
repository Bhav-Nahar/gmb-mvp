import redis as _redis_lib
from app.core.config import settings

_pool = None

def get_redis() -> _redis_lib.Redis:
    global _pool
    if _pool is None:
        _pool = _redis_lib.ConnectionPool.from_url(
            settings.REDIS_URL,
            max_connections=10,
            socket_timeout=5,
            socket_connect_timeout=5,
            decode_responses=False,
        )
    return _redis_lib.Redis(connection_pool=_pool)
