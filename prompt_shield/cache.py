import json
import logging
from typing import Optional
from abc import ABC, abstractmethod

from .models import ShieldResult

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract cache backend."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[ShieldResult]:
        pass
    
    @abstractmethod
    async def set(self, key: str, result: ShieldResult, ttl: int = 3600):
        pass


class InMemoryCache(CacheBackend):
    """Simple in-memory cache fallback."""
    
    def __init__(self, max_size: int = 10000):
        self._cache: dict[str, str] = {}
        self._max_size = max_size
    
    async def get(self, key: str) -> Optional[ShieldResult]:
        if key in self._cache:
            data = json.loads(self._cache[key])
            result = ShieldResult(**data)
            result.cached = True
            return result
        return None
    
    async def set(self, key: str, result: ShieldResult, ttl: int = 3600):
        # Simple LRU-ish eviction
        if len(self._cache) >= self._max_size:
            # Remove oldest 10%
            keys_to_remove = list(self._cache.keys())[: self._max_size // 10]
            for k in keys_to_remove:
                del self._cache[k]
        
        self._cache[key] = result.model_dump_json()


class RedisCache(CacheBackend):
    """Redis cache backend."""
    
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client = None
    
    async def _get_client(self):
        if self._client is None:
            import redis.asyncio as redis
            self._client = redis.from_url(self._redis_url)
        return self._client
    
    async def get(self, key: str) -> Optional[ShieldResult]:
        try:
            client = await self._get_client()
            data = await client.get(f"shield:{key}")
            if data:
                result = ShieldResult(**json.loads(data))
                result.cached = True
                return result
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
        return None
    
    async def set(self, key: str, result: ShieldResult, ttl: int = 3600):
        try:
            client = await self._get_client()
            await client.setex(
                f"shield:{key}",
                ttl,
                result.model_dump_json(),
            )
        except Exception as e:
            logger.warning(f"Redis set error: {e}")


def create_cache(redis_url: Optional[str] = None) -> CacheBackend:
    """Factory to create appropriate cache backend."""
    if redis_url:
        try:
            return RedisCache(redis_url)
        except Exception as e:
            logger.warning(f"Failed to create Redis cache: {e}, falling back to in-memory")
    
    return InMemoryCache()
