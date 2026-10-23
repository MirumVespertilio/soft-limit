import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test_token_for_tests")
os.environ.setdefault("SECRET_KEY", "test_secret_key_for_tests")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "999999")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import (
    ContentItem,
    ContentStatus,
    MediaType,
    ContentItemMedia,
    MediaAsset,
    FileRole,
)
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


async def _create_content(session, title="Test Card", status=ContentStatus.PUBLISHED):
    item = ContentItem(title=title, status=status, media_type=MediaType.PHOTO)
    session.add(item)
    await session.flush()
    return item.id


async def _create_wheel_with_segments(session, admin_client, token, content_ids):
    wheels_response = await admin_client.post(
        "/api/v1/admin/wheels",
        json={"name": "Test Wheel"},
        headers={"Authorization": f"Bearer {token}"},
    )
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

    async_session = async_sessionmaker(
        concurrent_engine, class_=AsyncSession, expire_on_commit=False
    )

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

        wheel_response = await client.get(
            "/api/v1/wheel",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert wheel_response.status_code == 200
        wheel_data = wheel_response.json()
        assert sorted(s["position"] for s in wheel_data["segments"]) == [0, 1]


async def test_delivery_status_values():
    assert DeliveryStatus.PENDING.value == "pending"
    assert DeliveryStatus.PROCESSING.value == "processing"
    assert DeliveryStatus.SENT.value == "sent"
    assert DeliveryStatus.FAILED.value == "failed"


async def test_media_roles_on_upload(concurrent_client, concurrent_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async_session = async_sessionmaker(
        concurrent_engine, class_=AsyncSession, expire_on_commit=False
    )
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

        with patch("app.telegram.Bot") as mock_bot_cls:
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
                old_preview_asset_id = r.json()["media_asset_id"]

                # Simulate legacy data produced by v2/v3: the same preview asset
                # also had an ORIGINAL relation. Replacing the preview must clean it.
                session.add(
                    ContentItemMedia(
                        content_item_id=cid,
                        media_asset_id=old_preview_asset_id,
                        role=FileRole.ORIGINAL,
                    )
                )
                await session.commit()

                r_replacement = await c.post(
                    "/api/v1/admin/media/upload",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    files={"file": ("test-preview-replacement.jpg", img_bytes, "image/jpeg")},
                    data={"content_item_id": str(cid), "role": "preview"},
                )
                assert r_replacement.status_code == 200
                preview_asset_id = r_replacement.json()["media_asset_id"]

                r_main = await c.post(
                    "/api/v1/admin/media/upload",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    files={"file": ("test-main.jpg", img_bytes, "image/jpeg")},
                    data={"content_item_id": str(cid), "role": "main"},
                )
                assert r_main.status_code == 200
                main_asset_id = r_main.json()["media_asset_id"]

        result = await session.execute(
            select(ContentItemMedia).where(ContentItemMedia.content_item_id == cid)
        )
        links = result.scalars().all()
        roles = {link.role for link in links}
        assert FileRole.ORIGINAL in roles
        assert FileRole.PREVIEW in roles
        assert FileRole.MAIN in roles

        roles_by_asset = {}
        for link in links:
            roles_by_asset.setdefault(link.media_asset_id, set()).add(link.role)
        assert FileRole.PREVIEW in roles_by_asset[preview_asset_id]
        assert FileRole.ORIGINAL not in roles_by_asset[preview_asset_id]
        assert FileRole.ORIGINAL not in roles_by_asset.get(old_preview_asset_id, set())
        assert FileRole.PREVIEW not in roles_by_asset.get(old_preview_asset_id, set())
        assert FileRole.MAIN in roles_by_asset[main_asset_id]
        assert FileRole.ORIGINAL in roles_by_asset[main_asset_id]

        # Delivery must choose the explicit MAIN asset, not the preview.
        from app.models.user import User
        from app.models.inventory import UserInventory, InventorySource
        from app.services.delivery import request_delivery

        owner = await session.scalar(select(User).where(User.telegram_id == 999999))
        assert owner is not None
        inventory = UserInventory(
            user_id=owner.id,
            content_item_id=cid,
            source=InventorySource.ADMIN_GRANT,
            reference_id=None,
        )
        session.add(inventory)
        await session.commit()
        await session.refresh(inventory)
        delivery = await request_delivery(session, owner.id, inventory.id)
        assert delivery.media_asset_id == main_asset_id


async def test_wheel_rejects_unpublished_cards(concurrent_client, concurrent_engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async_session = async_sessionmaker(
        concurrent_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        client = concurrent_client
        admin_token = await _create_admin_user(client, session, concurrent_engine)
        draft_id = await _create_content(session, "Draft Card", status=ContentStatus.DRAFT)
        disabled_id = await _create_content(session, "Disabled Card", status=ContentStatus.DISABLED)
        published_id = await _create_content(session, "Published Card")
        await session.commit()

        wheel_id = await _create_wheel_with_segments(session, client, admin_token, [published_id])
        headers = {"Authorization": f"Bearer {admin_token}"}

        for content_id in (draft_id, disabled_id):
            response = await client.post(
                f"/api/v1/admin/wheels/{wheel_id}/segments",
                json={"content_item_id": content_id, "label": "Invalid", "weight": 1},
                headers=headers,
            )
            assert response.status_code == 400
            assert "published" in response.json()["detail"].lower()

            response = await client.put(
                f"/api/v1/admin/wheels/{wheel_id}/segments",
                json={
                    "segments": [
                        {
                            "content_item_id": content_id,
                            "label": "Invalid",
                            "weight": 1,
                            "position": 2,
                        }
                    ]
                },
                headers=headers,
            )
            assert response.status_code == 400
            assert "published" in response.json()["detail"].lower()


async def test_publish_card_before_adding_to_wheel(concurrent_client, concurrent_engine):
    """A card can be published first, then linked to a wheel segment."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    client = concurrent_client
    async_session = async_sessionmaker(
        concurrent_engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        admin_token = await _create_admin_user(client, session, concurrent_engine)
        draft_id = await _create_content(
            session,
            "Publish before wheel",
            status=ContentStatus.DRAFT,
        )
        await session.commit()
        headers = {"Authorization": f"Bearer {admin_token}"}

        wheel_response = await client.post(
            "/api/v1/admin/wheels",
            json={"name": "Publish Flow Wheel"},
            headers=headers,
        )
        assert wheel_response.status_code == 200, wheel_response.text
        wheel_id = wheel_response.json()["id"]

        publish_response = await client.patch(
            f"/api/v1/admin/content/{draft_id}",
            json={"status": "published"},
            headers=headers,
        )
        assert publish_response.status_code == 200, publish_response.text

        segment_response = await client.post(
            f"/api/v1/admin/wheels/{wheel_id}/segments",
            json={
                "content_item_id": draft_id,
                "label": "New prize",
                "weight": 1,
                "position": 0,
            },
            headers=headers,
        )
        assert segment_response.status_code == 200, segment_response.text

        wheel_response = await client.get("/api/v1/wheel", headers=headers)
        assert wheel_response.status_code == 200, wheel_response.text
        visible_ids = {segment["content_item_id"] for segment in wheel_response.json()["segments"]}
        assert draft_id in visible_ids
