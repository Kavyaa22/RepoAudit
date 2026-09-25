"""Tests for auth user store profile and deletion."""

from app.modules.auth.shared.store import user_store


def test_update_profile():
    user = user_store.create(
        email="tester@e2m.solutions",
        password="secret123",
        full_name="Tester",
        user_id="user-test-1",
    )
    updated = user_store.update_profile(user["user_id"], full_name="Updated Name")
    assert updated is not None
    assert updated["full_name"] == "Updated Name"


def test_delete_user_requires_password():
    import uuid

    email = f"delete-me-{uuid.uuid4().hex[:8]}@e2m.solutions"
    user_store.create(
        email=email,
        password="correct-pass",
        full_name="Delete Me",
        user_id="user-delete-1",
    )
    assert user_store.delete_user("user-delete-1", "wrong-pass") is False
    assert user_store.find_by_email(email) is not None
    assert user_store.delete_user("user-delete-1", "correct-pass") is True
    assert user_store.find_by_email(email) is None
