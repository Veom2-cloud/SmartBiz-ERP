def test_purchase_page(client):
    response = client.get("/purchases")
    assert response.status_code == 302