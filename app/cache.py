import json
import os
from typing import Any

try:
    import redis
except ImportError:  # pragma: no cover - optional dependency at runtime
    redis = None


class NullCache:
    enabled = False

    def get_json(self, key: str) -> dict[str, Any] | None:
        return None

    def set_json(self, key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        return False

    def delete(self, key: str) -> bool:
        return False


class RedisCache:
    enabled = True

    def __init__(self, client: "redis.Redis", key_prefix: str, default_ttl_seconds: int) -> None:
        self.client = client
        self.key_prefix = key_prefix
        self.default_ttl_seconds = default_ttl_seconds

    def _key(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    def get_json(self, key: str) -> dict[str, Any] | None:
        try:
            raw = self.client.get(self._key(key))
        except Exception:
            return None
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None

    def set_json(self, key: str, payload: dict[str, Any], ttl_seconds: int | None = None) -> bool:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        try:
            self.client.set(self._key(key), json.dumps(payload), ex=max(ttl, 1))
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        try:
            self.client.delete(self._key(key))
            return True
        except Exception:
            return False


def build_resolve_cache_key(short_code: str) -> str:
    return f"resolve:{short_code}"


def init_cache(app):
    app.extensions["cache"] = NullCache()

    enabled = os.environ.get("REDIS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    if redis is None:
        app.logger.warning("REDIS_ENABLED=true but redis dependency is unavailable; using NullCache")
        return

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    ttl_raw = os.environ.get("REDIS_CACHE_TTL_SECONDS", "300")
    key_prefix = os.environ.get("REDIS_CACHE_KEY_PREFIX", "url-shortener")

    try:
        ttl_seconds = int(ttl_raw)
    except ValueError:
        ttl_seconds = 300

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        client.ping()
        app.extensions["cache"] = RedisCache(client=client, key_prefix=key_prefix, default_ttl_seconds=max(ttl_seconds, 1))
        app.logger.info("Redis cache enabled")
    except Exception:
        app.logger.warning("Redis cache init failed; using NullCache")
