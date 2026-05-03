import sys
import os

# Add parent folder to Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run import app

def test_home():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200