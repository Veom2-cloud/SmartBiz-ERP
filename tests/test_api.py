def test_company_api(client):
    response = client.get("/api/companies")
    assert response.status_code == 200
    assert response.is_json