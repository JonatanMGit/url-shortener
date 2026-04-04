import io

from peewee import DataError, IntegrityError

from app.models.event import Event
from app.routes import events as events_routes
from app.routes import urls as urls_routes
from app.routes import users as users_routes


class FakeCache:
    def __init__(self, payload=None):
        self.payload = payload
        self.deleted_keys = []
        self.set_calls = []

    def get_json(self, key):
        return self.payload

    def set_json(self, key, payload, ttl_seconds=None):
        self.set_calls.append((key, payload, ttl_seconds))
        return True

    def delete(self, key):
        self.deleted_keys.append(key)
        return True


def create_user(client, username, email):
    response = client.post("/users", json={"username": username, "email": email})
    assert response.status_code == 201
    return response.get_json()


def create_url(client, user_id, original_url, title, is_active=True):
    response = client.post(
        "/urls",
        json={"user_id": user_id, "original_url": original_url, "title": title},
    )
    assert response.status_code == 201
    payload = response.get_json()
    if not is_active:
        deactivate = client.put(f"/urls/{payload['id']}", json={"is_active": False})
        assert deactivate.status_code == 200
    return payload


def test_events_list_rejects_non_integer_filters(client):
    response = client.get("/events?url_id=abc")
    assert response.status_code == 400
    assert response.get_json()["details"]["url_id"] == "Must be an integer"

    response = client.get("/events?user_id=xyz")
    assert response.status_code == 400
    assert response.get_json()["details"]["user_id"] == "Must be an integer"


def test_events_list_supports_filters(client):
    user = create_user(client, "events_filter_user", "events_filter@example.com")
    url = create_url(client, user["id"], "https://example.com/events/filter", "Events Filter")

    create_event = client.post(
        "/events",
        json={
            "event_type": "custom",
            "url_id": url["id"],
            "user_id": user["id"],
            "details": {"source": "test"},
        },
    )
    assert create_event.status_code == 201

    response = client.get(f"/events?url_id={url['id']}&user_id={user['id']}&event_type=custom")
    assert response.status_code == 200
    assert response.get_json()["total_items"] >= 1


def test_events_create_validation_branches(client):
    response = client.post("/events", json={"url_id": 1, "user_id": 1})
    assert response.status_code == 400

    response = client.post("/events", json={"event_type": "   ", "url_id": 1, "user_id": 1})
    assert response.status_code == 400

    response = client.post("/events", json={"event_type": "click"})
    assert response.status_code == 400

    response = client.post("/events", json={"event_type": "click", "url_id": "1", "user_id": 1})
    assert response.status_code == 400

    response = client.post("/events", json={"event_type": "click", "url_id": 1, "user_id": "1"})
    assert response.status_code == 400

    response = client.post(
        "/events",
        json={"event_type": "click", "url_id": 1, "user_id": 1, "details": "not-an-object"},
    )
    assert response.status_code == 400


def test_events_create_mismatched_identity(client):
    user_a = create_user(client, "events_mismatch_a", "events_mismatch_a@example.com")
    user_b = create_user(client, "events_mismatch_b", "events_mismatch_b@example.com")
    url = create_url(client, user_a["id"], "https://example.com/events/mismatch", "Mismatch")

    response = client.post(
        "/events",
        json={"event_type": "click", "url_id": url["id"], "user_id": user_b["id"]},
    )
    assert response.status_code == 422
    assert "does not belong" in response.get_json()["details"]["identity"]


def test_events_create_handles_data_error_branch(client, monkeypatch):
    def raise_data_error(*args, **kwargs):
        raise DataError("bad id")

    monkeypatch.setattr(events_routes.Url, "get_by_id", raise_data_error)

    response = client.post(
        "/events",
        json={"event_type": "click", "url_id": 123, "user_id": 456, "details": {}},
    )
    assert response.status_code == 400
    assert response.get_json()["details"]["identity"] == "Invalid ID format"


def test_events_create_allows_none_details(client):
    user = create_user(client, "events_none_details", "events_none_details@example.com")
    url = create_url(client, user["id"], "https://example.com/events/none", "None Details")

    response = client.post(
        "/events",
        json={"event_type": "click", "url_id": url["id"], "user_id": user["id"], "details": None},
    )
    assert response.status_code == 201
    assert response.get_json()["details"] == {}


def test_is_valid_url_handles_value_error(monkeypatch):
    def raise_value_error(_value):
        raise ValueError("invalid")

    monkeypatch.setattr(urls_routes, "urlparse", raise_value_error)
    assert urls_routes.is_valid_url("https://example.com") is False


def test_create_url_missing_fields_returns_400(client):
    response = client.post("/urls", json={})
    assert response.status_code == 400
    assert "Missing required fields" in response.get_json()["details"]["fields"]


def test_create_url_generation_exhaustion_returns_500(client, monkeypatch):
    user = create_user(client, "url_exhaustion_user", "url_exhaustion@example.com")

    class AlwaysExistsQuery:
        def where(self, *args, **kwargs):
            return self

        def exists(self):
            return True

    monkeypatch.setattr(urls_routes, "generate_short_code", lambda length=6: "AAAAAA")
    monkeypatch.setattr(urls_routes.Url, "select", lambda: AlwaysExistsQuery())

    response = client.post(
        "/urls",
        json={
            "user_id": user["id"],
            "original_url": "https://example.com/exhaust",
            "title": "Exhaust",
        },
    )
    assert response.status_code == 500
    assert "generation" in response.get_json()["details"]


def test_list_urls_supports_user_and_active_filters(client):
    user_a = create_user(client, "urls_filter_a", "urls_filter_a@example.com")
    user_b = create_user(client, "urls_filter_b", "urls_filter_b@example.com")

    create_url(client, user_a["id"], "https://example.com/a1", "A1", is_active=True)
    create_url(client, user_a["id"], "https://example.com/a2", "A2", is_active=False)
    create_url(client, user_b["id"], "https://example.com/b1", "B1", is_active=True)

    response_user = client.get(f"/urls?user_id={user_a['id']}")
    assert response_user.status_code == 200
    assert response_user.get_json()["total_items"] == 2

    response_active = client.get(f"/urls?user_id={user_a['id']}&is_active=true")
    assert response_active.status_code == 200
    assert response_active.get_json()["total_items"] == 1


def test_get_url_endpoint(client):
    user = create_user(client, "urls_get_user", "urls_get_user@example.com")
    url = create_url(client, user["id"], "https://example.com/get", "Get URL")

    response = client.get(f"/urls/{url['id']}")
    assert response.status_code == 200
    assert response.get_json()["id"] == url["id"]


def test_delete_url_is_idempotent(client):
    user = create_user(client, "urls_delete_user", "urls_delete_user@example.com")
    url = create_url(client, user["id"], "https://example.com/delete", "Delete URL")

    response = client.delete(f"/urls/{url['id']}")
    assert response.status_code == 204

    response = client.delete(f"/urls/{url['id']}")
    assert response.status_code == 204


def test_urls_redirect_cache_hit_active_creates_event(app):
    client = app.test_client()
    user = create_user(client, "urls_cache_hit_user", "urls_cache_hit_user@example.com")
    url = create_url(client, user["id"], "https://example.com/cache-hit", "Cache Hit")

    cache = FakeCache(
        payload={
            "url_id": url["id"],
            "user_id": user["id"],
            "original_url": "https://example.com/cache-hit",
            "is_active": True,
        }
    )
    app.extensions["cache"] = cache

    with app.app_context():
        initial_count = Event.select().where(Event.event_type == "click").count()

    response = client.get(f"/urls/{url['short_code']}/redirect")
    assert response.status_code == 302
    assert response.headers["X-Cache"] == "HIT"

    with app.app_context():
        new_count = Event.select().where(Event.event_type == "click").count()
    assert new_count == initial_count + 1


def test_urls_redirect_cache_hit_inactive_returns_410(app):
    client = app.test_client()
    user = create_user(client, "urls_cache_inactive_user", "urls_cache_inactive_user@example.com")
    url = create_url(client, user["id"], "https://example.com/cache-inactive", "Cache Inactive")

    app.extensions["cache"] = FakeCache(
        payload={
            "url_id": url["id"],
            "user_id": user["id"],
            "original_url": "https://example.com/cache-inactive",
            "is_active": False,
        }
    )

    response = client.get(f"/urls/{url['short_code']}/redirect")
    assert response.status_code == 410
    assert response.headers["X-Cache"] == "HIT"


def test_urls_redirect_cache_miss_sets_cache(app):
    client = app.test_client()
    user = create_user(client, "urls_cache_miss_user", "urls_cache_miss_user@example.com")
    url = create_url(client, user["id"], "https://example.com/cache-miss", "Cache Miss")

    cache = FakeCache(payload=None)
    app.extensions["cache"] = cache

    response = client.get(f"/urls/{url['short_code']}/redirect")
    assert response.status_code == 302
    assert response.headers["X-Cache"] == "MISS"
    assert len(cache.set_calls) == 1


def test_urls_redirect_handles_not_found_and_db_inactive(client):
    response = client.get("/urls/DOESNOT/redirect")
    assert response.status_code == 404

    user = create_user(client, "urls_db_inactive_user", "urls_db_inactive_user@example.com")
    url = create_url(client, user["id"], "https://example.com/db-inactive", "DB Inactive", is_active=False)

    response = client.get(f"/urls/{url['short_code']}/redirect")
    assert response.status_code == 410


def test_resolve_cache_hit_active_and_inactive(app):
    client = app.test_client()
    user = create_user(client, "resolve_cache_user", "resolve_cache_user@example.com")
    url = create_url(client, user["id"], "https://example.com/resolve-cache", "Resolve Cache")

    app.extensions["cache"] = FakeCache(
        payload={
            "url_id": url["id"],
            "user_id": user["id"],
            "original_url": "https://example.com/resolve-cache",
            "is_active": True,
        }
    )
    response = client.get(f"/r/{url['short_code']}")
    assert response.status_code == 302
    assert response.headers["X-Cache"] == "HIT"

    app.extensions["cache"] = FakeCache(
        payload={
            "url_id": url["id"],
            "user_id": user["id"],
            "original_url": "https://example.com/resolve-cache",
            "is_active": False,
        }
    )
    response = client.get(f"/r/{url['short_code']}")
    assert response.status_code == 410
    assert response.headers["X-Cache"] == "HIT"


def test_create_user_validation_and_conflict_variants(client):
    response = client.post("/users", json={"username": 123, "email": ["bad"]})
    assert response.status_code == 422

    response = client.post("/users", json={"username": "   ", "email": "   "})
    assert response.status_code == 400

    create_user(client, "conflict_alpha", "alpha@example.com")
    create_user(client, "conflict_beta", "beta@example.com")

    response = client.post("/users", json={"username": "conflict_alpha", "email": "new@example.com"})
    assert response.status_code == 422
    assert "username" in response.get_json()["details"]

    response = client.post("/users", json={"username": "new_user", "email": "alpha@example.com"})
    assert response.status_code == 422
    assert "email" in response.get_json()["details"]

    response = client.post("/users", json={"username": "conflict_alpha", "email": "beta@example.com"})
    assert response.status_code == 422
    assert "conflict" in response.get_json()["details"]


def test_create_user_integrity_retry_branch(client, monkeypatch):
    real_create = users_routes.User.create
    call_count = {"count": 0}

    def flaky_create(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] == 1:
            raise IntegrityError("forced")
        return real_create(*args, **kwargs)

    monkeypatch.setattr(users_routes.User, "create", flaky_create)

    response = client.post(
        "/users",
        json={"username": "retry_create_user", "email": "retry_create_user@example.com"},
    )
    assert response.status_code == 201
    assert call_count["count"] == 2


def test_users_get_update_delete_branches(client):
    user = create_user(client, "users_branch_user", "users_branch_user@example.com")

    response = client.get(f"/users/{user['id']}")
    assert response.status_code == 200

    response = client.put(
        f"/users/{user['id']}",
        json={"username": "users_branch_user_updated", "email": "users_branch_user_updated@example.com"},
    )
    assert response.status_code == 200
    assert response.get_json()["username"] == "users_branch_user_updated"

    response = client.delete(f"/users/{user['id']}")
    assert response.status_code == 204

    response = client.delete(f"/users/{user['id']}")
    assert response.status_code == 204


def test_bulk_load_missing_columns_and_created_at_branch(client):
    csv_missing = "bad1,bad2\nvalue1,value2"
    response = client.post(
        "/users/bulk",
        data={"file": (io.BytesIO(csv_missing.encode("utf-8")), "users.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 422
    assert "Missing required columns" in response.get_json()["details"]["file"]

    csv_data = "username,email,created_at\nwith_created,with_created@example.com,2026-01-01 10:00:00\n,skip@example.com,2026-01-02 10:00:00"
    response = client.post(
        "/users/bulk",
        data={"file": (io.BytesIO(csv_data.encode("utf-8")), "users.csv")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json()["count"] == 1
