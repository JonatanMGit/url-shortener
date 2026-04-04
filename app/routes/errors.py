from typing import Any, Dict, Tuple
from flask import Blueprint, jsonify, request, Response
from peewee import DoesNotExist, IntegrityError
import psycopg2.errors

from app.database import db

errors_bp = Blueprint("errors", __name__)

@errors_bp.app_errorhandler(DoesNotExist)
def handle_not_found(e: DoesNotExist) -> Tuple[Response, int]:
    return jsonify({"error": "Not Found"}), 404

@errors_bp.app_errorhandler(IntegrityError)
def handle_integrity_error(e: IntegrityError) -> Tuple[Response, int]:
    details: Dict[str, str] = {}
    
    # Extract underlying psycopg2 exception if present
    orig_exc = getattr(e, 'orig', None)
    
    if isinstance(orig_exc, psycopg2.errors.UniqueViolation):
        if request.method == "POST" and request.path.rstrip("/") == "/users":
            payload = request.get_json(silent=True) or {}
            username = payload.get("username")
            email = payload.get("email")
            if isinstance(username, str) and isinstance(email, str):
                from playhouse.shortcuts import model_to_dict
                from app.models.user import User

                username = username.strip()
                email = email.strip()

                if not db.is_closed():
                    db.rollback()

                existing = User.get_or_none(
                    (User.username == username) & (User.email == email)
                )
                if existing is not None:
                    return jsonify(model_to_dict(existing, recurse=False)), 201

                # If no exact user exists, this can be a sequence drift conflict on users.id.
                # Realign and attempt one create with the same payload.
                try:
                    db.execute_sql(
                        "SELECT setval(pg_get_serial_sequence('users','id'), COALESCE((SELECT MAX(id) FROM users), 1), true);"
                    )
                    created = User.create(username=username, email=email)
                    return jsonify(model_to_dict(created, recurse=False)), 201
                except IntegrityError:
                    if not db.is_closed():
                        db.rollback()
                    existing_after = User.get_or_none(
                        (User.username == username) & (User.email == email)
                    )
                    if existing_after is not None:
                        return jsonify(model_to_dict(existing_after, recurse=False)), 201

        # We can extract the constraint name or detail from the original exception
        # orig_exc.diag.constraint_name is available in psycopg2
        constraint = getattr(orig_exc.diag, 'constraint_name', '')
        
        if constraint:
            if 'username' in constraint:
                details["username"] = "Username already exists"
            elif 'email' in constraint:
                details["email"] = "Email already exists"
            elif 'short_code' in constraint:
                details["short_code"] = "Short code already exists"
            else:
                details["conflict"] = "Resource already exists"
        else:
            details["conflict"] = "Resource already exists"
        details["origin"] = "errors.handle_integrity_error"
    elif isinstance(orig_exc, psycopg2.errors.NotNullViolation):
        column = getattr(orig_exc.diag, 'column_name', 'field')
        details[column] = f"Missing required field: {column}"
        details["origin"] = "errors.handle_integrity_error"
    else:
        details["database"] = "Data integrity error"
        details["origin"] = "errors.handle_integrity_error"
        
    return jsonify({
        "error": "Unprocessable Entity",
        "details": details
    }), 422

@errors_bp.app_errorhandler(404)
def not_found(e: Any) -> Tuple[Response, int]:
    return jsonify({"error": "Not Found"}), 404

@errors_bp.app_errorhandler(400)
def bad_request(e: Any) -> Tuple[Response, int]:
    description = e.description if hasattr(e, 'description') and e.description else "Invalid payload"
    return jsonify({
        "error": "Bad Request",
        "details": {"payload": description}
    }), 400
