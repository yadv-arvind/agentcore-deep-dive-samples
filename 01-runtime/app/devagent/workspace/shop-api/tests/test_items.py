import pytest
from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


@pytest.fixture(autouse=True)
def reset_state():
    main._items.clear()
    main._next_id = 1


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_and_get_item():
    created = client.post("/items", json={"name": "mug", "price": 9.5})
    assert created.status_code == 201
    assert created.json() == {"id": 1, "name": "mug", "price": 9.5}

    fetched = client.get("/items/1")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "mug"


def test_list_items():
    client.post("/items", json={"name": "mug", "price": 9.5})
    client.post("/items", json={"name": "hat", "price": 15})
    response = client.get("/items")
    assert [item["name"] for item in response.json()] == ["mug", "hat"]


def test_missing_item_returns_404():
    assert client.get("/items/99").status_code == 404


def test_delete_item():
    client.post("/items", json={"name": "mug", "price": 9.5})
    response = client.delete("/items/1")
    assert response.status_code == 200
    assert response.json() == {"detail": "Item deleted"}

    response = client.get("/items/1")
    assert response.status_code == 404


def test_delete_missing_item():
    response = client.delete("/items/99")
    assert response.status_code == 404
    assert response.json() == {"detail": "Item not found"}