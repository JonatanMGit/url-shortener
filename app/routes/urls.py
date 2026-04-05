import random
import string
import json
from flask import Blueprint, current_app, request, jsonify
from playhouse.shortcuts import model_to_dict
from urllib.parse import urlparse

from app.cache import build_resolve_cache_key
from app.metrics import observe_event_created, observe_url_created, observe_url_resolution
from app.models.url import Url
from app.models.user import User
from app.models.event import Event

urls_bp = Blueprint("urls", __name__, url_prefix="/urls")

def generate_short_code(length=6):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

@urls_bp.route("", methods=["POST"])
def create_url():
    data = request.get_json()
    
    if not data or "user_id" not in data or "original_url" not in data or "title" not in data:
        return jsonify({"error": "Bad Request", "details": {"fields": "Missing required fields: user_id, original_url, title"}}), 400
        
    if not is_valid_url(data["original_url"]):
        return jsonify({"error": "Bad Request", "details": {"original_url": "Invalid URL format. Must include scheme and netloc (e.g. https://)"}}), 400
        
    user = User.get_by_id(data["user_id"])
        
    attempts = 0
    short_code = None
    while attempts < 10:
        code = generate_short_code()
        if not Url.select().where(Url.short_code == code).exists():
            short_code = code
            break
        attempts += 1
        
    if not short_code:
        return jsonify({"error": "System Error", "details": {"generation": "Could not generate short code"}}), 500
        
    url = Url.create(
        user_id=user,
        short_code=short_code,
        original_url=data["original_url"],
        title=data["title"]
    )
    
    Event.create(
        url_id=url,
        user_id=user,
        event_type="created",
        details=json.dumps({"short_code": short_code, "original_url": data["original_url"]})
    )
    observe_url_created()
    observe_event_created("created")

    cache = current_app.extensions.get("cache")
    if cache:
        cache.delete(build_resolve_cache_key(short_code))
    
    return jsonify(model_to_dict(url, recurse=False)), 201

@urls_bp.route("", methods=["GET"])
def list_urls():
    user_id = request.args.get("user_id", type=int)
    is_active = request.args.get("is_active")
    
    query = Url.select()
    if user_id is not None:
        query = query.where(Url.user_id == user_id)
        
    if is_active is not None:
        is_active_val = str(is_active).lower() == "true"
        query = query.where(Url.is_active == is_active_val)
        
    results = [model_to_dict(url, recurse=False) for url in query]
    return jsonify({"kind": "list", "sample": results, "total_items": len(results)}), 200

@urls_bp.route("/<int:url_id>", methods=["GET"])
def get_url(url_id):
    url = Url.get_by_id(url_id)
    return jsonify(model_to_dict(url, recurse=False)), 200

@urls_bp.route("/<int:url_id>", methods=["PUT"])
def update_url(url_id):
    url = Url.get_by_id(url_id)
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Bad Request", "details": {"payload": "Invalid or missing data"}}), 400
        
    if "title" in data:
        url.title = data["title"]
    if "is_active" in data:
        url.is_active = data["is_active"]
        
    url.save()

    cache = current_app.extensions.get("cache")
    if cache:
        cache.delete(build_resolve_cache_key(url.short_code))

    return jsonify(model_to_dict(url, recurse=False)), 200

@urls_bp.route("/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    from peewee import DoesNotExist
    try:
        url = Url.get_by_id(url_id)
        short_code = url.short_code
        url.delete_instance(recursive=True)

        cache = current_app.extensions.get("cache")
        if cache:
            cache.delete(build_resolve_cache_key(short_code))

        return "", 204
    except DoesNotExist:
        return "", 204

@urls_bp.route("/<string:short_code>/redirect", methods=["GET"])
def redirect_short_code(short_code):
    from peewee import DoesNotExist
    from flask import redirect
    cache = current_app.extensions.get("cache")
    cache_key = build_resolve_cache_key(short_code)

    cached_payload = cache.get_json(cache_key) if cache else None
    if cached_payload:
        if not cached_payload.get("is_active", True):
            response = jsonify({"error": "Gone"})
            response.status_code = 410
            response.headers["X-Cache"] = "HIT"
            return response

        Event.create(
            url_id=cached_payload.get("url_id"),
            user_id=cached_payload.get("user_id"),
            event_type="click",
            details=json.dumps({"short_code": short_code, "action": "redirect"})
        )
        observe_event_created("click")
        observe_url_resolution(source="urls_redirect", cache="HIT")

        response = redirect(cached_payload.get("original_url"), code=302)
        response.headers["X-Cache"] = "HIT"
        return response

    try:
        url = Url.get(Url.short_code == short_code)
    except DoesNotExist:
        return jsonify({"error": "Not Found"}), 404
        
    if not url.is_active:
        return jsonify({"error": "Gone"}), 410
        
    # Log event
    Event.create(
        url_id=url,
        user_id=url.user_id,
        event_type="click",
        details=json.dumps({"short_code": short_code, "action": "redirect"})
    )
    observe_event_created("click")
    observe_url_resolution(source="urls_redirect", cache="MISS")

    if cache:
        cache.set_json(cache_key, {
            "url_id": url.id,
            "user_id": url.user_id.id,
            "original_url": url.original_url,
            "is_active": url.is_active,
        })

    response = redirect(url.original_url, code=302)
    response.headers["X-Cache"] = "MISS"
    return response