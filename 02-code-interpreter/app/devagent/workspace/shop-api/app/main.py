from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="shop-api")


class ItemIn(BaseModel):
    name: str
    price: float


class Item(ItemIn):
    id: int


_items: dict[int, Item] = {}
_next_id = 1


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items")
def list_items() -> list[Item]:
    return list(_items.values())


@app.post("/items", status_code=201)
def create_item(item: ItemIn) -> Item:
    global _next_id
    created = Item(id=_next_id, **item.model_dump())
    _items[created.id] = created
    _next_id += 1
    return created


@app.get("/items/{item_id}")
def get_item(item_id: int) -> Item:
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="Item not found")
    return _items[item_id]


@app.delete("/items/{item_id}")
def delete_item(item_id: int):
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="Item not found")
    del _items[item_id]
    return {"detail": "Item deleted"}