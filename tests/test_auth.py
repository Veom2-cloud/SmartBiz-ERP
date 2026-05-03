def test_login_page(client):
    response = client.get("/auth/login")
    assert response.status_code == 200