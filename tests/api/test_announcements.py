import uuid

import pytest

pytestmark = pytest.mark.api


def test_create_announcement(api_context_multipart):
    topic = f"Test Topic {uuid.uuid4().hex[:8]}"

    response = api_context_multipart.post(
        "/api/announcements",
        multipart={
            "topic": topic,
            "subject": "Test Subject",
            "content": "Test content body",
            "factories": "1",
        },
    )

    assert response.status == 200
    body = response.json()
    assert body["topic"] == topic
    assert body["factories"] == [1]
    assert body["id"] is not None


def test_create_announcement_missing_required_field_fails(api_context_multipart):
    """An empty-string multipart field is dropped entirely by the client, so this
    exercises the "topic" @RequestParam missing case, not the empty-string branch of
    the controller's manual validation -- Spring's MissingServletRequestParameterException
    isn't given a specific handler here, so it falls through to the generic 500 handler."""
    response = api_context_multipart.post(
        "/api/announcements",
        multipart={"subject": "Subject", "content": "Body", "factories": "1"},
    )

    assert response.status == 500


def test_get_all_announcements(api_context):
    response = api_context.get("/api/announcements")

    assert response.status == 200
    assert isinstance(response.json(), list)


def test_get_announcement_not_found(api_context):
    response = api_context.get("/api/announcements/999999")

    assert response.status == 404


def test_delete_announcement(api_context, api_context_multipart):
    create_response = api_context_multipart.post(
        "/api/announcements",
        multipart={"topic": "Delete Me", "subject": "Subject", "content": "Body", "factories": "1"},
    )
    announcement_id = create_response.json()["id"]

    delete_response = api_context.delete(f"/api/announcements/{announcement_id}")
    assert delete_response.status == 200

    get_response = api_context.get(f"/api/announcements/{announcement_id}")
    assert get_response.status == 404
