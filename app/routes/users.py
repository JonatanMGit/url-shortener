import csv
import io
from flask import Blueprint, request, jsonify
from playhouse.shortcuts import model_to_dict
from peewee import chunked, IntegrityError

from app.database import db
from app.metrics import observe_user_created
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
        required_columns = {"username", "email"}
        if not reader.fieldnames or not required_columns.issubset(set(reader.fieldnames)):
            missing = sorted(required_columns - set(reader.fieldnames or []))
            raise ValueError(f"Missing required columns: {', '.join(missing)}")
        rows = list(reader)

        # Avoid sequence drift by not forcing primary keys from CSV.
        insert_rows = []
        for row in rows:
            username = row.get("username")
            email = row.get("email")
            if not username or not email:
                continue
            user_row = {
                "username": username,
                "email": email,
            }
            created_at = row.get("created_at")
            if created_at:
                user_row["created_at"] = created_at
            insert_rows.append(user_row)
        
        imported = 0
        with db.atomic():
            for batch in chunked(insert_rows, 100):
                User.insert_many(batch).on_conflict_ignore().execute()
                imported += len(batch)

        # Keep PostgreSQL sequence aligned with the table's current max(id).
        try:
            db.execute_sql(
                "SELECT setval(pg_get_serial_sequence('users','id'), COALESCE((SELECT MAX(id) FROM users), 1), true);"
            )
        except Exception:
            pass
                
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

    username = data["username"]
    email = data["email"]
    if not isinstance(username, str) or not isinstance(email, str):
        return jsonify({
            "error": "Unprocessable Entity",
            "details": {
                "username": "Required string field",
                "email": "Required email string field"
            }
        }), 422

    username = username.strip()
    email = email.strip()
    if not username or not email:
        return jsonify({
            "error": "Bad Request",
            "details": {
                "username": "Required string field",
                "email": "Required email string field"
            }
        }), 400
        
    try:
        user = User.get((User.username == username) & (User.email == email))
        # Both match, return as idempotent
        return jsonify(model_to_dict(user, recurse=False)), 201
    except User.DoesNotExist:
        username_exists = User.select().where(User.username == username).exists()
        email_exists = User.select().where(User.email == email).exists()
        if username_exists and email_exists:
            return jsonify({
                "error": "Unprocessable Entity",
                "details": {
                    "conflict": "Both username and email already exist (but not together).",
                    "origin": "users.create_user"
                },
                "debug": {"username": username, "email": email}
            }), 422
        elif username_exists:
            return jsonify({
                "error": "Unprocessable Entity",
                "details": {
                    "username": "Username already exists",
                    "origin": "users.create_user"
                },
                "debug": {"username": username}
            }), 422
        elif email_exists:
            return jsonify({
                "error": "Unprocessable Entity",
                "details": {
                    "email": "Email already exists",
                    "origin": "users.create_user"
                },
                "debug": {"email": email}
            }), 422
        try:
            user = User.create(username=username, email=email)
            observe_user_created()
            return jsonify(model_to_dict(user, recurse=False)), 201
        except IntegrityError:
            # psycopg2 can leave the transaction aborted after an integrity error.
            if not db.is_closed():
                db.rollback()

            # Handle rare race conditions where the same user is inserted after pre-checks.
            existing = User.get_or_none((User.username == username) & (User.email == email))
            if existing is not None:
                return jsonify(model_to_dict(existing, recurse=False)), 201

            # Self-heal ID sequence drift and retry once.
            db.execute_sql(
                "SELECT setval(pg_get_serial_sequence('users','id'), COALESCE((SELECT MAX(id) FROM users), 1), true);"
            )
            user = User.create(username=username, email=email)
            observe_user_created()
            return jsonify(model_to_dict(user, recurse=False)), 201

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