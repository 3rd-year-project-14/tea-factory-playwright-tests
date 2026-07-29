def test_get_all_vehicles(api_context):
    response = api_context.get("/api/vehicles")

    assert response.status == 200
    assert isinstance(response.json(), list)


def test_vehicle_full_crud_flow(api_context):
    vehicle = {
        "vehicleNo": "PW-TEST-001",
        "model": "Toyota Dyna",
        "capacity": 1000,
        "incomeCertificate": "",
        "image": "",
        "factoryId": None,
    }

    create_response = api_context.post("/api/vehicles", data=vehicle)
    assert create_response.status == 201

    get_response = api_context.get(f"/api/vehicles/{vehicle['vehicleNo']}")
    assert get_response.status == 200
    assert get_response.json()["model"] == "Toyota Dyna"

    vehicle["capacity"] = 1500
    update_response = api_context.put(f"/api/vehicles/{vehicle['vehicleNo']}", data=vehicle)
    assert update_response.status == 200
    assert update_response.json()["capacity"] == 1500

    delete_response = api_context.delete(f"/api/vehicles/{vehicle['vehicleNo']}")
    assert delete_response.status == 204

    confirm_response = api_context.get(f"/api/vehicles/{vehicle['vehicleNo']}")
    assert confirm_response.status == 404
