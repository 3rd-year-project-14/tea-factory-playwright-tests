import pytest

pytestmark = pytest.mark.api

def test_get_all_factories(api_context):
    response = api_context.get("/api/factories")

    assert response.status == 200
    assert isinstance(response.json(), list)


def test_create_and_fetch_factory(api_context):
    new_factory = {
        "name": "Playwright Test Factory",
        "location": "Kandy",
        "image": "",
        "mapUrl": "",
    }

    create_response = api_context.post("/api/factories", data=new_factory)
    assert create_response.status == 200

    created = create_response.json()
    assert created["name"] == new_factory["name"]
    assert created["id"] is not None

    get_response = api_context.get(f"/api/factories/{created['id']}")
    assert get_response.status == 200
    assert get_response.json()["location"] == "Kandy"


def test_get_factory_not_found(api_context):
    response = api_context.get("/api/factories/999999")

    assert response.status == 404
