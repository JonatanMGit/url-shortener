def test_create_user(client):
    response = client.post("/users", json={"username": "alice", "email": "alice@example.com"})
    assert response.status_code == 201
    data = response.json
    assert data["username"] == "alice"
    assert "id" in data

def test_duplicate_user(client):
    client.post("/users", json={"username": "bob", "email": "bob@example.com"})
    response = client.post("/users", json={"username": "bob", "email": "bob@example.com"})
    assert response.status_code == 422
    assert "error" in response.json
    assert response.json["error"] == "Unprocessable Entity"

def test_get_missing_user(client):
    response = client.get("/users/9999")
    assert response.status_code == 404
    assert response.json["error"] == "Not Found"

def test_bad_request_payload(client):
    response = client.post("/users", data="not valid json", content_type="application/json")
    assert response.status_code == 400
    assert response.json["error"] == "Bad Request"

def test_create_and_resolve_url(client):
    # 1. Create a user
    user_resp = client.post("/users", json={"username": "charlie", "email": "charlie@h.com"})
    user_id = user_resp.json["id"]
    
    # 2. Create a URL
    url_resp = client.post("/urls", json={
        "user_id": user_id, 
        "original_url": "https://mlh.io", 
        "title": "MLH"
    })
    assert url_resp.status_code == 201
    short_code = url_resp.json["short_code"]
    
    # 3. Resolve the URL
    resolve_resp = client.get(f"/r/{short_code}")
    assert resolve_resp.status_code == 302
    assert resolve_resp.headers["Location"] == "https://mlh.io"

def test_invalid_url_format(client):
    user_resp = client.post("/users", json={"username": "dave", "email": "dave@h.com"})
    user_id = user_resp.json["id"]
    
    response = client.post("/urls", json={
        "user_id": user_id, 
        "original_url": "invalid-url", 
        "title": "Missing HTTP"
    })
    assert response.status_code == 400

def test_resolve_missing_url(client):
    response = client.get("/r/NOCODE")
    assert response.status_code == 404
