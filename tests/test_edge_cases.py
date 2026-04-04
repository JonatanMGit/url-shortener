import io

def test_bulk_missing_file(client):
    response = client.post("/users/bulk")
    assert response.status_code == 400
    assert response.json["error"] == "Bad Request"
    
def test_bulk_empty_filename(client):
    response = client.post(
        "/users/bulk",
        data={"file": (io.BytesIO(b""), "")},
        content_type="multipart/form-data"
    )
    assert response.status_code == 400

def test_bulk_invalid_csv(client):
    # Missing columns will trigger KeyError / KeyError on insert
    csv_data = "col1,col2\nval1,val2"
    response = client.post(
        "/users/bulk", 
        data={"file": (io.BytesIO(csv_data.encode("utf-8")), "users.csv")},
        content_type="multipart/form-data"
    )
    # The peewee insert handles mismatched dict keys by tossing an error mapped to 422 
    # based on missing NOT NULL constraints. 
    assert response.status_code == 422

def test_create_url_missing_user(client):
    response = client.post("/urls", json={
        "user_id": 99999,
        "original_url": "https://valid.com",
        "title": "Title"
    })
    # user_id is a foreign key, missing mapped DoesNotExist
    assert response.status_code == 404

def test_get_missing_url(client):
    response = client.get("/urls/99999")
    assert response.status_code == 404

def test_put_missing_url(client):
    response = client.put("/urls/99999", json={"title": "new"})
    assert response.status_code == 404
    
def test_put_invalid_url_payload(client):
    # Setup
    user_resp = client.post("/users", json={"username": "put_user", "email": "put@example.com"})
    url_resp = client.post("/urls", json={
        "user_id": user_resp.json["id"], 
        "original_url": "https://example.com/put", 
        "title": "Put"
    })
    
    url_id = url_resp.json["id"]
    
    # Try empty
    response = client.put(f"/urls/{url_id}", json={})
    assert response.status_code == 400
    
def test_put_missing_user(client):
    response = client.put("/users/99999", json={"username": "missing"})
    assert response.status_code == 404

def test_put_invalid_user_payload(client):
    user_resp = client.post("/users", json={"username": "u_put", "email": "u_put@example.com"})
    user_id = user_resp.json["id"]
    response = client.put(f"/users/{user_id}", json={})
    assert response.status_code == 400
    
def test_events_empty_list(client):
    # Should work fine (might be empty list or full)
    response = client.get("/events")
    assert response.status_code == 200

def test_json_details_parsing_fallback(app):
    # Creates an event with non-json in the JSON string explicitly to check coverage lines
    from app.models.event import Event
    from app.models.user import User
    
    with app.app_context():
        user = User.create(username="event_user", email="event@h.com")
        Event.create(user_id=user, event_type="test", details="plain text string")
        
    client = app.test_client()
    response = client.get("/events")
    assert response.status_code == 200
    # Must fallback and keep details as string
    found = any(e.get("details") == "plain text string" for e in response.json)
    assert found
