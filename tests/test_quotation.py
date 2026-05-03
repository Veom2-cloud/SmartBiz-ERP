def test_quotation_home(client):
    response = client.get("/quotations")
    assert response.status_code == 200