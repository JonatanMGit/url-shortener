import random
import string
from flask import Blueprint, request, jsonify
from playhouse.shortcuts import model_to_dict
from urllib.parse import urlparse

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
    
    import json
    Event.create(
        url_id=url,
        user_id=user,
        event_type="created",
        details=json.dumps({"short_code": short_code, "original_url": data["original_url"]})
    )
    
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
    return jsonify(model_to_dict(url, recurse=False)), 200

@urls_bp.route("/<int:url_id>", methods=["DELETE"])
def delete_url(url_id):
    from peewee import DoesNotExist
    try:
        url = Url.get_by_id(url_id)
        url.delete_instance(recursive=True)
        return "", 204
    except DoesNotExist:
        return "", 204

@urls_bp.route("/<string:short_code>/redirect", methods=["GET"])
def redirect_short_code(short_code):
    from peewee import DoesNotExist
    from flask import redirect
    try:
        url = Url.get(Url.short_code == short_code)
    except DoesNotExist:
        return jsonify({"error": "Not Found"}), 404
        
    if not url.is_active:
        return jsonify({"error": "Gone"}), 410
        
    # Log event
    import json
    Event.create(
        url_id=url,
        user_id=url.user_id,
        event_type="clicked",
        details=json.dumps({"short_code": short_code, "action": "redirect"})
    )
    return redirect(url.original_url, code=302)