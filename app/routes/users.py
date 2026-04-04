import csv
import io
from flask import Blueprint, request, jsonify
from playhouse.shortcuts import model_to_dict
from peewee import chunked

from app.database import db
from app.models.user import User

users_bp = Blueprint("users", __name__, url_prefix="/users")

@users_bp.route("/bulk", methods=["POST"])
def bulk_load():
    if "file" not in request.files:
        return jsonify({"error": "Bad Request", "details": {"file": "No file provided"}}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Bad Request", "details": {"file": "No selected file"}}), 400
    
    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        reader = csv.DictReader(stream)
        rows = list(reader)
        
        imported = 0
        with db.atomic():
            for batch in chunked(rows, 100):
                User.insert_many(batch).on_conflict_ignore().execute()
                imported += len(batch)
                
        return jsonify({"count": imported}), 200
    except Exception as e:
        return jsonify({"error": "Unprocessable Entity", "details": {"file": str(e)}}), 422

@users_bp.route("", methods=["GET"])
def list_users():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    
    users = User.select().paginate(page, per_page)
    results = [model_to_dict(u, recurse=False) for u in users]
    return jsonify({"kind": "list", "sample": results, "total_items": len(results)}), 200

@users_bp.route("", methods=["POST"])
def create_user():
    data = request.get_json()
    if not data or "username" not in data or "email" not in data:
        return jsonify({
            "error": "Bad Request",
            "details": {
                "username": "Required string field",
                "email": "Required email string field"
            }
        }), 400
        
    try:
        user, created = User.get_or_create(
            username=data["username"],
            email=data["email"]
        )
        return jsonify(model_to_dict(user, recurse=False)), 201
    except Exception as e:
        raise e

@users_bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = User.get_by_id(user_id)
    return jsonify(model_to_dict(user, recurse=False)), 200

@users_bp.route("/<int:user_id>", methods=["PUT"])
def update_user(user_id):
    user = User.get_by_id(user_id)
    data = request.get_json()
    if not data:
        return jsonify({"error": "Bad Request", "details": {"payload": "Invalid or missing data"}}), 400
        
    if "username" in data:
        user.username = data["username"]
    if "email" in data:
        user.email = data["email"]
        
    user.save()
    return jsonify(model_to_dict(user, recurse=False)), 200

@users_bp.route("/<int:user_id>", methods=["DELETE"])
def delete_user(user_id):
    from peewee import DoesNotExist
    try:
        user = User.get_by_id(user_id)
        user.delete_instance(recursive=True)
        return "", 204
    except DoesNotExist:
        return "", 204