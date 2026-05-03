from app.models import User

def test_password_hash(client):
    user = User(username="x", email="x@test.com")
    user.set_password("1234")

    assert user.check_password("1234")