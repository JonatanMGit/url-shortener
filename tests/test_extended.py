import io

def test_list_users(client):
    client.post("/users", json={"username": "list_user", "email": "list@example.com"})
    response = client.get("/users")
    assert response.status_code == 200
    assert len(response.json["sample"]) >= 1

def test_update_user(client):
    user_resp = client.post("/users", json={"username": "update_user", "email": "update@example.com"})
    user_id = user_resp.json["id"]
    
    response = client.put(f"/users/{user_id}", json={"username": "updated_user"})
    assert response.status_code == 200
    assert response.json["username"] == "updated_user"

def test_bulk_users(client):
    csv_data = "username,email\nbulk1,bulk1@example.com\nbulk2,bulk2@example.com"
    response = client.post(
        "/users/bulk", 
        data={"file": (io.BytesIO(csv_data.encode("utf-8")), "users.csv")},
        content_type="multipart/form-data"
    )
    assert response.status_code == 200
    assert response.json["count"] >= 2

def test_list_and_update_urls(client):
    user_resp = client.post("/users", json={"username": "url_user", "email": "url@example.com"})
    user_id = user_resp.json["id"]
    
    url_resp = client.post("/urls", json={
        "user_id": user_id, 
        "original_url": "https://example.com/one", 
        "title": "One"
    })
    url_id = url_resp.json["id"]
    
    # List
    list_resp = client.get("/urls")
    assert list_resp.status_code == 200
    assert len(list_resp.json["sample"]) >= 1
    
    # Update Active Status
    put_resp = client.put(f"/urls/{url_id}", json={"is_active": False})
    assert put_resp.status_code == 200
    assert put_resp.json["is_active"] is False
    
    # Try resolving inactive
    short_code = url_resp.json["short_code"]
    res_resp = client.get(f"/r/{short_code}")
    assert res_resp.status_code == 410

def test_list_events(client):
    response = client.get("/events")
    assert response.status_code == 200
    assert response.json["kind"] == "list"
    assert isinstance(response.json["sample"], list)
