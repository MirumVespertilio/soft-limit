import os
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_for_tests")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999999")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ContentItem, ContentStatus, MediaType, ContentItemMedia, MediaAsset, FileRole
from app.models.delivery import DeliveryStatus
from app.models.wheel import Wheel, WheelSegment
from app.models.spin import Spin
from app.models.welcome import WelcomeRewardItem
from tests.test_auth import generate_init_data


async def _create_admin_user(client, session, engine) -> str:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as s:
        admin_tg_id = 999999
        init_data = generate_init_data(telegram_id=admin_tg_id)
        response = await client.post("/api/v1/auth/telegram", json={"init_data": init_data})
        return response.json()["access_token"]


async def _create_content(session, title="Test Card"):
    item = ContentItem(title=title, status=ContentStatus.PUBLISHED, media_type=MediaType.PHOTO)
    session.add(item)
    await session.flush()
    return item.id


async def _create_wheel_with_segments(session, admin_client, token, content_ids):
    wheels_response = await admin_client.post("/api/v1/admin/wheels", json={"name": "Test Wheel"}, headers={"Authorization": f"Bearer {token}"})
    wheel_id = wheels_response.json()["id"]

    for pos, cid in enumerate(content_ids):
        await admin_client.post(
            f"/api/v1/admin/wheels/{wheel_id}/segments",
            json={"content_item_id": cid, "label": f"Prize {pos}", "weight": 1, "position": pos},
            headers={"Authorization": f"Bearer {token}"},
        )
    return wheel_id


async def test_add_segment_preserves_others(concurrent_client, concurrent_engine):
    client = concurrent_client
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session = async_sessionmaker(concurrent_engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        admin_token = await _create_admin_user(client, session, concurrent_engine)
        cid1 = await _create_content(session, "Card 1")
        cid2 = await _create_content(session, "Card 2")
        await session.commit()

        wheel_id = await _create_wheel_with_segments(session, client, admin_token, [cid1])

        r = await client.post(
            f"/api/v1/admin/wheels/{wheel_id}/segments",
            json={"content_item_id": cid2, "label": "Prize 1", "weight": 1, "position": 1},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 200

        result = await session.execute(
            select(WheelSegment).where(WheelSegment.wheel_id == wheel_id)
        )
        segments = result.scalars().all()
        assert len(segments) == 2
        assert all(s.is_active for s in segments)


async def test_delivery_status_values():
    assert DeliveryStatus.PENDING.value == "pending"
    assert DeliveryStatus.PROCESSING.value == "processing"
    assert DeliveryStatus.SENT.value == "sent"
    assert DeliveryStatus.FAILED.value == "failed"


async def test_media_roles_on_upload(concurrent_client, concurrent_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    async_session = async_sessionmaker(concurrent_engine, class_=AsyncSession, expire_on_commit=False)
    from unittest.mock import AsyncMock, patch, MagicMock
    import io
    from PIL import Image
    from httpx import AsyncClient, ASGITransport
    from app.main import app

    async with async_session() as session:
        admin_token = await _create_admin_user(concurrent_client, session, concurrent_engine)
        cid = await _create_content(session, "Media Card")
        await session.commit()

        img = Image.new("RGB", (100, 100), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        img_bytes = buf.getvalue()

        with patch("aiogram.Bot") as mock_bot_cls:
            mock_bot = AsyncMock()
            mock_bot.session = AsyncMock()
            mock_bot_cls.return_value = mock_bot

            mock_doc = MagicMock()
            mock_doc.file_id = "doc_file_id"
            mock_doc.file_unique_id = "doc_unique_id"
            mock_msg = MagicMock()
            mock_msg.document = mock_doc
            mock_bot.send_document = AsyncMock(return_value=mock_msg)

            mock_photo = MagicMock()
            mock_photo.file_id = "photo_file_id"
            mock_photo.file_unique_id = "photo_unique_id"
            mock_photo_msg = MagicMock()
            mock_photo_msg.photo = [mock_photo]
            mock_bot.send_photo = AsyncMock(return_value=mock_photo_msg)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as c:
                r = await c.post(
                    "/api/v1/admin/media/upload",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    files={"file": ("test.jpg", img_bytes, "image/jpeg")},
                    data={"content_item_id": str(cid), "role": "preview"},
                )
                assert r.status_code == 200

        result = await session.execute(
            select(ContentItemMedia).where(ContentItemMedia.content_item_id == cid)
        )
        links = result.scalars().all()
        roles = {link.role for link in links}
        assert FileRole.ORIGINAL in roles
        assert FileRole.PREVIEW in roles
