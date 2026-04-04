import json
from types import SimpleNamespace

from flask import Flask
from peewee import IntegrityError
from werkzeug.exceptions import BadRequest

from app import cache as cache_module
from app.models.user import User
from app.routes import errors as errors_routes


class FakeRedisClient:
    def __init__(self):
        self.values = {}
        self.raise_get = False
        self.raise_set = False
        self.raise_delete = False
        self.raise_ping = False

    def ping(self):
        if self.raise_ping:
            raise RuntimeError("ping failed")

    def get(self, key):
        if self.raise_get:
            raise RuntimeError("get failed")
        return self.values.get(key)

    def set(self, key, value, ex):
        if self.raise_set:
            raise RuntimeError("set failed")
        self.values[key] = value
        self.values[f"ttl:{key}"] = ex

    def delete(self, key):
        if self.raise_delete:
            raise RuntimeError("delete failed")
        self.values.pop(key, None)


class FakeDiag:
    def __init__(self, constraint_name="", column_name="field"):
        self.constraint_name = constraint_name
        self.column_name = column_name


class FakeUniqueViolation(Exception):
    def __init__(self, constraint_name=""):
        self.diag = FakeDiag(constraint_name=constraint_name)


class FakeNotNullViolation(Exception):
    def __init__(self, column_name="field"):
        self.diag = FakeDiag(column_name=column_name)


def patch_fake_psycopg2(monkeypatch):
    monkeypatch.setattr(errors_routes.psycopg2.errors, "UniqueViolation", FakeUniqueViolation)
    monkeypatch.setattr(errors_routes.psycopg2.errors, "NotNullViolation", FakeNotNullViolation)


def test_null_cache_defaults():
    cache = cache_module.NullCache()
    assert cache.get_json("x") is None
    assert cache.set_json("x", {"a": 1}) is False
    assert cache.delete("x") is False


def test_redis_cache_roundtrip_and_ttl():
    client = FakeRedisClient()
    cache = cache_module.RedisCache(client=client, key_prefix="prefix", default_ttl_seconds=10)

    assert cache._key("abc") == "prefix:abc"
    assert cache.set_json("abc", {"ok": True}, ttl_seconds=3) is True
    assert client.values["ttl:prefix:abc"] == 3
    assert cache.get_json("abc") == {"ok": True}

    # ttl should be clamped to >= 1
    assert cache.set_json("abc", {"ok": True}, ttl_seconds=0) is True
    assert client.values["ttl:prefix:abc"] == 1


def test_redis_cache_handles_get_set_delete_errors_and_invalid_json():
    client = FakeRedisClient()
    cache = cache_module.RedisCache(client=client, key_prefix="prefix", default_ttl_seconds=5)

    client.values["prefix:broken"] = "not-json"
    assert cache.get_json("broken") is None

    client.raise_get = True
    assert cache.get_json("abc") is None
    client.raise_get = False

    client.raise_set = True
    assert cache.set_json("abc", {"x": 1}) is False
    client.raise_set = False

    client.raise_delete = True
    assert cache.delete("abc") is False


def test_build_resolve_cache_key():
    assert cache_module.build_resolve_cache_key("abc123") == "resolve:abc123"


def test_init_cache_disabled_uses_null_cache(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setenv("REDIS_ENABLED", "false")

    cache_module.init_cache(app)

    assert isinstance(app.extensions["cache"], cache_module.NullCache)


def test_init_cache_enabled_without_dependency_falls_back(monkeypatch):
    app = Flask(__name__)
    warnings = []

    monkeypatch.setenv("REDIS_ENABLED", "true")
    monkeypatch.setattr(cache_module, "redis", None)
    monkeypatch.setattr(app.logger, "warning", lambda msg: warnings.append(msg))

    cache_module.init_cache(app)

    assert isinstance(app.extensions["cache"], cache_module.NullCache)
    assert any("dependency is unavailable" in msg for msg in warnings)


def test_init_cache_enabled_success_with_invalid_ttl_defaults(monkeypatch):
    app = Flask(__name__)
    fake_client = FakeRedisClient()

    class FakeRedisFactory:
        @staticmethod
        def from_url(url, decode_responses, socket_connect_timeout, socket_timeout):
            assert url == "redis://cache:6379/0"
            assert decode_responses is True
            assert socket_connect_timeout == 0.5
            assert socket_timeout == 0.5
            return fake_client

    info_logs = []
    monkeypatch.setenv("REDIS_ENABLED", "yes")
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/0")
    monkeypatch.setenv("REDIS_CACHE_TTL_SECONDS", "not-a-number")
    monkeypatch.setenv("REDIS_CACHE_KEY_PREFIX", "svc")
    monkeypatch.setattr(cache_module, "redis", SimpleNamespace(Redis=FakeRedisFactory))
    monkeypatch.setattr(app.logger, "info", lambda msg: info_logs.append(msg))

    cache_module.init_cache(app)

    cache = app.extensions["cache"]
    assert isinstance(cache, cache_module.RedisCache)
    assert cache.key_prefix == "svc"
    assert cache.default_ttl_seconds == 300
    assert any("enabled" in msg.lower() for msg in info_logs)


def test_init_cache_enabled_ping_failure_falls_back(monkeypatch):
    app = Flask(__name__)
    fake_client = FakeRedisClient()
    fake_client.raise_ping = True

    class FakeRedisFactory:
        @staticmethod
        def from_url(*args, **kwargs):
            return fake_client

    warnings = []
    monkeypatch.setenv("REDIS_ENABLED", "on")
    monkeypatch.setattr(cache_module, "redis", SimpleNamespace(Redis=FakeRedisFactory))
    monkeypatch.setattr(app.logger, "warning", lambda msg: warnings.append(msg))

    cache_module.init_cache(app)

    assert isinstance(app.extensions["cache"], cache_module.NullCache)
    assert any("init failed" in msg.lower() for msg in warnings)


def test_error_not_found_handler(app):
    with app.app_context():
        response, status = errors_routes.not_found(Exception("missing"))
    assert status == 404
    assert response.get_json() == {"error": "Not Found"}


def test_error_bad_request_handler_with_description(app):
    with app.app_context():
        response, status = errors_routes.bad_request(BadRequest(description="payload issue"))
    assert status == 400
    assert response.get_json()["details"]["payload"] == "payload issue"


def test_error_bad_request_handler_default_description(app):
    class BareError:
        description = ""

    with app.app_context():
        response, status = errors_routes.bad_request(BareError())
    assert status == 400
    assert response.get_json()["details"]["payload"] == "Invalid payload"


def test_error_integrity_unique_for_users_returns_existing(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    with app.app_context():
        existing = User.create(username="dup_user", email="dup@example.com")

    err = IntegrityError("duplicate")
    err.orig = FakeUniqueViolation("users_username_key")

    with app.test_request_context("/users", method="POST", json={"username": "dup_user", "email": "dup@example.com"}):
        response, status = errors_routes.handle_integrity_error(err)

    assert status == 201
    assert response.get_json()["id"] == existing.id


def test_error_integrity_unique_for_users_sequence_realign_creates_user(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    err = IntegrityError("duplicate")
    err.orig = FakeUniqueViolation("users_email_key")

    with app.test_request_context("/users", method="POST", json={"username": "fresh_user", "email": "fresh@example.com"}):
        response, status = errors_routes.handle_integrity_error(err)

    assert status == 201
    assert response.get_json()["username"] == "fresh_user"


def test_error_integrity_unique_for_users_retry_finds_user(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    real_create = User.create

    def create_then_raise(*args, **kwargs):
        real_create(*args, **kwargs)
        raise IntegrityError("forced retry")

    monkeypatch.setattr(User, "create", create_then_raise)

    err = IntegrityError("duplicate")
    err.orig = FakeUniqueViolation("users_username_key")

    with app.test_request_context("/users", method="POST", json={"username": "retry_user", "email": "retry@example.com"}):
        response, status = errors_routes.handle_integrity_error(err)

    assert status == 201
    assert response.get_json()["username"] == "retry_user"


def test_error_integrity_unique_constraint_mappings(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    with app.test_request_context("/urls", method="POST", json={}):
        err_username = IntegrityError("dup")
        err_username.orig = FakeUniqueViolation("users_username_key")
        response, status = errors_routes.handle_integrity_error(err_username)
        assert status == 422
        assert response.get_json()["details"]["username"] == "Username already exists"

        err_email = IntegrityError("dup")
        err_email.orig = FakeUniqueViolation("users_email_key")
        response, status = errors_routes.handle_integrity_error(err_email)
        assert response.get_json()["details"]["email"] == "Email already exists"

        err_short = IntegrityError("dup")
        err_short.orig = FakeUniqueViolation("urls_short_code_key")
        response, status = errors_routes.handle_integrity_error(err_short)
        assert response.get_json()["details"]["short_code"] == "Short code already exists"

        err_other = IntegrityError("dup")
        err_other.orig = FakeUniqueViolation("other_constraint")
        response, status = errors_routes.handle_integrity_error(err_other)
        assert response.get_json()["details"]["conflict"] == "Resource already exists"

        err_empty = IntegrityError("dup")
        err_empty.orig = FakeUniqueViolation("")
        response, status = errors_routes.handle_integrity_error(err_empty)
        assert response.get_json()["details"]["conflict"] == "Resource already exists"


def test_error_integrity_not_null_mapping(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    err = IntegrityError("not null")
    err.orig = FakeNotNullViolation("email")

    with app.test_request_context("/users", method="POST", json={}):
        response, status = errors_routes.handle_integrity_error(err)

    assert status == 422
    payload = response.get_json()
    assert payload["details"]["email"] == "Missing required field: email"


def test_error_integrity_generic_mapping(app, monkeypatch):
    patch_fake_psycopg2(monkeypatch)

    err = IntegrityError("integrity")
    err.orig = RuntimeError("unknown")

    with app.test_request_context("/users", method="POST", json={}):
        response, status = errors_routes.handle_integrity_error(err)

    assert status == 422
    payload = response.get_json()
    assert payload["details"]["database"] == "Data integrity error"
    assert payload["details"]["origin"] == "errors.handle_integrity_error"
