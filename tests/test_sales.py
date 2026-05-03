def test_sales_page_redirect(client):
    response = client.get("/sales")
    assert response.status_code == 302