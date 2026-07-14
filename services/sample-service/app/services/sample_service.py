"""Sample item business logic service."""

import math
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.schemas.item import ItemCreate, ItemPatch, ItemUpdate
from app.services.event_publisher import event_publisher

logger = structlog.get_logger()


def _item_payload(item: Item) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "owner_id": item.owner_id,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


class SampleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data: ItemCreate) -> Item:
        item = Item(
            name=data.name,
            description=data.description,
            owner_id=data.owner_id,
        )
        self.db.add(item)
        await self.db.commit()
        await self.db.refresh(item)

        await event_publisher.publish("item_created", _item_payload(item))
        return item

    async def get(self, item_id: UUID) -> Item | None:
        result = await self.db.execute(
            select(Item).where(Item.id == item_id, Item.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    async def list_items(
        self,
        owner_id: UUID | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[Item], int]:
        base = select(Item).where(Item.is_deleted.is_(False))
        if owner_id:
            base = base.where(Item.owner_id == owner_id)

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        query = base.order_by(Item.updated_at.desc())
        query = query.offset((page - 1) * size).limit(size)
        result = await self.db.execute(query)
        return list(result.scalars().all()), total

    async def update(self, item_id: UUID, data: ItemUpdate) -> Item | None:
        item = await self.get(item_id)
        if not item:
            return None

        item.name = data.name
        item.description = data.description
        await self.db.commit()
        await self.db.refresh(item)

        await event_publisher.publish("item_updated", _item_payload(item))
        return item

    async def patch(self, item_id: UUID, data: ItemPatch) -> Item | None:
        item = await self.get(item_id)
        if not item:
            return None

        changed = False
        if "name" in data.model_fields_set:
            item.name = data.name
            changed = True
        if "description" in data.model_fields_set:
            item.description = data.description
            changed = True

        await self.db.commit()
        await self.db.refresh(item)

        if changed:
            await event_publisher.publish("item_updated", _item_payload(item))
        return item

    async def delete(self, item_id: UUID) -> bool:
        item = await self.get(item_id)
        if not item:
            return False
        item.is_deleted = True
        await self.db.commit()

        await event_publisher.publish(
            "item_deleted", {"id": item_id, "type": "item"}
        )
        return True

    @staticmethod
    def paginate(total: int, page: int, size: int) -> int:
        return max(1, math.ceil(total / size)) if size > 0 else 1
