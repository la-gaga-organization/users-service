def test_create_user_success(client):
    payload = {
        "hashed_password": "admin",
        "email": "gaga@gaga.com",
        "name": "gaga",
        "surname": "gagoso"
    }
    response = client.post("/api/v1/users/", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == payload["email"]
    assert "id" in data
