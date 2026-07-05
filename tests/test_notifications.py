"""
tests/test_notifications.py — Mixtape

Tests for notification logic.
"""

import pytest
from app import create_app, db
from models import User, Song, Notification
from services.notification_service import rate_song


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def seed_data(app):
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        rater = User(username="rater", email="rater@example.com")
        db.session.add_all([sharer, rater])
        db.session.flush()

        song = Song(title="Test Song", artist="Test Artist", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()

        yield {"sharer": sharer, "rater": rater, "song": song}


def test_rate_song_creates_notification(app, seed_data):
    """
    Rating a song should create a notification for the person who shared it.
    This is a regression test for Bug #4.
    """
    with app.app_context():
        rater_id = seed_data["rater"].id
        song_id = seed_data["song"].id
        sharer_id = seed_data["sharer"].id

        rate_song(rater_id, song_id, 5)

        notifications = db.session.query(Notification).filter_by(user_id=sharer_id).all()
        assert len(notifications) == 1
        assert notifications[0].notification_type == "song_rated"
        assert "rated your song" in notifications[0].body
