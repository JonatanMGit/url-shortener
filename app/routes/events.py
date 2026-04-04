import json
from flask import Blueprint, jsonify
from playhouse.shortcuts import model_to_dict

from app.models.event import Event

events_bp = Blueprint("events", __name__, url_prefix="/events")

@events_bp.route("", methods=["GET"])
def list_events():
    events = Event.select()
    result = []
    
    for event in events:
        event_dict = model_to_dict(event)
        
        # Parse details string back to JSON
        if event.details:
            try:
                event_dict["details"] = json.loads(event.details)
            except json.JSONDecodeError:
                pass
                
        result.append(event_dict)
        
    return jsonify(result), 200