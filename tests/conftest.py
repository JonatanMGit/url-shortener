import pytest
from app import create_app
from app.database import db
from app.models.user import User
from app.models.url import Url
from app.models.event import Event

@pytest.fixture
def app():
    app = create_app()
    app.config.update({"TESTING": True})
    
    with app.app_context():
        # Setup DB explicitly for tests
        db.create_tables([User, Url, Event])
        yield app
        # Teardown
        db.drop_tables([User, Url, Event])

@pytest.fixture
def client(app):
    return app.test_client()
