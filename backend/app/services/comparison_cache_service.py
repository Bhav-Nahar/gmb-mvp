import json
import hashlib
from typing import Dict, Any, Optional

from app.core.config import settings
from app.core.redis_client import get_redis
redis_client = get_redis()

class ComparisonCacheService:
    CACHE_TTL = 900  # 15 minutes

    @staticmethod
    def _generate_key(org_id: int, group_type: str, date_hash: str, filter_hash: str) -> str:
        return f"comparison:{org_id}:{group_type}:{date_hash}:{filter_hash}"

    @staticmethod
    def _hash_dict(d: dict) -> str:
        """Deterministically hashes a dictionary for cache keys."""
        # Sort keys to ensure deterministic ordering
        d_str = json.dumps(d, sort_keys=True)
        return hashlib.md5(d_str.encode('utf-8')).hexdigest()

    @classmethod
    def get_cached_comparison(cls, org_id: int, group_type: str, date_params: dict, filter_params: dict) -> Optional[Dict[str, Any]]:
        if not redis_client:
            return None

        date_hash = cls._hash_dict(date_params)
        filter_hash = cls._hash_dict(filter_params)
        key = cls._generate_key(org_id, group_type, date_hash, filter_hash)

        try:
            cached = redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            # Fallback gracefully if Redis is down
            return None
        return None

    @classmethod
    def set_cached_comparison(cls, org_id: int, group_type: str, date_params: dict, filter_params: dict, data: Dict[str, Any]):
        if not redis_client:
            return

        date_hash = cls._hash_dict(date_params)
        filter_hash = cls._hash_dict(filter_params)
        key = cls._generate_key(org_id, group_type, date_hash, filter_hash)

        try:
            redis_client.setex(key, cls.CACHE_TTL, json.dumps(data))
        except Exception:
            pass

    @classmethod
    def invalidate_comparison_cache(cls, org_id: Optional[int] = None):
        """
        Invalidates comparison cache. Pass an org_id to clear one org, or None to
        clear every org (used by the org-wide daily aggregation/backfill).
        Should be called whenever the underlying daily insights change:
        - Group aggregation / backfill
        - Geography backfill (city/state reassignment)
        - Region/Group membership changes
        """
        if not redis_client:
            return

        pattern = f"comparison:{org_id}:*" if org_id is not None else "comparison:*"
        try:
            keys = []
            for key in redis_client.scan_iter(match=pattern):
                keys.append(key)
                if len(keys) >= 500:
                    redis_client.delete(*keys)
                    keys = []
            if keys:
                redis_client.delete(*keys)
        except Exception:
            pass

