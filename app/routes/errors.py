from typing import Any, Dict, Tuple
from flask import Blueprint, jsonify, Response
from peewee import DoesNotExist, IntegrityError
import psycopg2.errors

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
    elif isinstance(orig_exc, psycopg2.errors.NotNullViolation):
        column = getattr(orig_exc.diag, 'column_name', 'field')
        details[column] = f"Missing required field: {column}"
    else:
        details["database"] = "Data integrity error"
        
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
