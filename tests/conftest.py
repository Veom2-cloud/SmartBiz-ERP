import os
import sys
import pytest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

import app
from app import db
from app.models import User   # adjust path if needed


@pytest.fixture(scope="function")
def app_instance():
    flask_app = app.create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "LOGIN_DISABLED": False,
        "WTF_CSRF_ENABLED": False,
    })

    with flask_app.app_context():
        db.create_all()

        user = User(
            username="testuser",
            email="test@test.com"
        )
        user.set_password("123456")   # if method exists
        db.session.add(user)
        db.session.commit()

        yield flask_app

        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app_instance):
    return app_instance.test_client()