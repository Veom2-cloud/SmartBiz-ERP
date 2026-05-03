def test_home(client):
    response = client.get("/")
    assert response.status_code == 200


def test_view_all_companies(client):
    response = client.get("/view-all-companies")
    assert response.status_code == 200