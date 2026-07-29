import uuid

import pytest

# There is no manager-specific create endpoint (ManagerController is read-only).
# Manager accounts are created through the generic UserController with role=FACTORY_MANAGER
# (or any of the other *_MANAGER roles). This flow found and fixed a real bug: the service
# used BeanUtils.copyProperties(userDTO, user) to map UserDTO -> User, but "factory" is a
# FactoryDTO on the DTO and a Factory entity on the entity -- a type mismatch that
# BeanUtils silently skips. So every user created with a factory was silently saved with
# factory_id = NULL. Fixed in UserService by resolving the Factory via FactoryRepository
# and setting it explicitly, on both the create and read/response paths.


@pytest.fixture
def created_manager(api_context, db_conn):
    unique = uuid.uuid4().hex[:8]
    response = api_context.post(
        "/api/users",
        data={
            "firebaseUid": f"pw-mgr-uid-{unique}",
            "email": f"pw-manager-{unique}@test.com",
            "role": "FACTORY_MANAGER",
            "name": "PW Manager",
            "nic": f"PWMGR{unique}",
            "contactNo": "0771234567",
            "isActive": True,
            "address": "Kandy",
            "factory": {"id": 1, "name": "Wawlugala Tea Factory"},
        },
    )
    assert response.status == 200
    manager_id = response.json()["id"]

    yield response.json()

    cur = db_conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (manager_id,))
    cur.close()


def test_create_manager_persists_factory_assignment(created_manager):
    assert created_manager["role"] == "FACTORY_MANAGER"
    assert created_manager["factory"] is not None
    assert created_manager["factory"]["id"] == 1


def test_created_manager_appears_in_factory_manager_list(api_context, created_manager):
    response = api_context.get("/api/manager-info/1")

    assert response.status == 200
    ids = [m["id"] for m in response.json()]
    assert created_manager["id"] in ids


def test_get_manager_user_by_id(api_context, created_manager):
    response = api_context.get(f"/api/users/{created_manager['id']}")

    assert response.status == 200
    body = response.json()
    assert body["email"] == created_manager["email"]
    assert body["factory"]["id"] == 1
