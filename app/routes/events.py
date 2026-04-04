import json
from flask import Blueprint, jsonify, request
from playhouse.shortcuts import model_to_dict

from app.models.event import Event
from app.models.url import Url
from app.models.user import User

events_bp = Blueprint("events", __name__, url_prefix="/events")

@events_bp.route("", methods=["GET"])
def list_events():
    url_id = request.args.get("url_id", type=int)
    user_id = request.args.get("user_id", type=int)
    event_type = request.args.get("event_type")
    
    query = Event.select()
    if url_id is not None:
        query = query.where(Event.url_id == url_id)
    if user_id is not None:
        query = query.where(Event.user_id == user_id)
    if event_type is not None:
        query = query.where(Event.event_type == event_type)
        
    events = query
    result = []
    
    for event in events:
        event_dict = model_to_dict(event, recurse=False)
        
        # Parse details string back to JSON
        if event.details:
            try:
                event_dict["details"] = json.loads(event.details)
            except json.JSONDecodeError:
                pass
                
        result.append(event_dict)
        
    return jsonify({"kind": "list", "sample": result, "total_items": len(result)}), 200

@events_bp.route("", methods=["POST"])
def create_event():
    data = request.get_json()
    if not data or "event_type" not in data:
        return jsonify({"error": "Bad Request", "details": {"event_type": "Required"}}), 400
        
    url_id_val = data.get("url_id")
    user_id_val = data.get("user_id")
    
    url = Url.get_by_id(url_id_val) if url_id_val else None
    user = User.get_by_id(user_id_val) if user_id_val else None
    
    details_val = json.dumps(data.get("details", {}))
        
    event = Event.create(
        url_id=url,
        user_id=user,
        event_type=data["event_type"],
        details=details_val
    )
    
    event_dict = model_to_dict(event, recurse=False)
    event_dict["details"] = json.loads(event.details) if event.details else {}
    return jsonify(event_dict), 201