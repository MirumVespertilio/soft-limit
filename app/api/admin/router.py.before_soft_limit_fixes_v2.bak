from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db import get_session
from app.models.user import User
from app.models.wallet import UserWallet, TransactionResource, TransactionReason
from app.models.spin import Spin
from app.models.purchases import SpinPurchase
from app.models.content import ContentItem, ContentStatus
from app.models.wheel import Wheel, WheelSegment
from app.models.welcome import WelcomeRewardItem
from app.models.purchases import SpinPackage
from app.models.inventory import UserInventory
from app.models.order import Order
from app.services.wallet import adjust_balance, get_wallet_by_user_id

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/dashboard")
async def dashboard(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    users_count = await session.scalar(select(func.count()).select_from(User))
    spins_count = await session.scalar(select(func.count()).select_from(Spin))
    purchases_count = await session.scalar(select(func.count()).select_from(SpinPurchase))
    inventory_count = await session.scalar(select(func.count()).select_from(UserInventory))

    return {
        "users": users_count or 0,
        "spins": spins_count or 0,
        "purchases": purchases_count or 0,
        "inventory_items": inventory_count or 0,
    }


@router.get("/users")
async def list_users(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
    search: str | None = None,
):
    query = select(User, UserWallet).join(UserWallet, isouter=True)
    if search:
        query = query.where(
            User.telegram_id == int(search) if search.isdigit() else User.username.ilike(f"%{search}%")
        )
    result = await session.execute(query)
    users = result.all()
    return {
        "users": [
            {
                "id": u.id,
                "telegram_id": u.telegram_id,
                "username": u.username,
                "first_name": u.first_name,
                "test_stars": w.test_stars_balance if w else 0,
                "spins": w.spins_balance if w else 0,
                "registered_at": u.registered_at.isoformat() if u.registered_at else None,
            }
            for u, w in users
        ]
    }


@router.get("/users/{user_id}")
async def get_user(
    user_id: int,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(User, UserWallet).join(UserWallet, isouter=True).where(User.id == user_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    user, wallet = row
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "test_stars": wallet.test_stars_balance if wallet else 0,
        "spins": wallet.spins_balance if wallet else 0,
        "welcome_spin_granted": user.welcome_spin_granted_at is not None,
        "welcome_spin_used": user.welcome_spin_used_at is not None,
    }


class BalanceAdjustmentRequest(BaseModel):
    resource: TransactionResource
    amount: int
    note: str


@router.post("/users/{user_id}/balance-adjustments")
async def adjust_user_balance(
    user_id: int,
    request: BalanceAdjustmentRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        tx = await adjust_balance(
            session=session,
            user_id=user_id,
            resource=request.resource,
            amount=request.amount,
            reason=TransactionReason.ADMIN_ADJUSTMENT,
            performed_by=admin_id,
            note=request.note,
        )
    except ValueError:
        raise HTTPException(status_code=404, detail="User not found")

    await session.commit()
    return {"transaction_id": tx.id, "amount": request.amount, "resource": request.resource.value}


@router.get("/analytics/revenue")
async def revenue_analytics(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    total_test_stars_spent = await session.scalar(
        select(func.coalesce(func.sum(SpinPurchase.price_test_stars), 0))
    )
    total_purchases = await session.scalar(select(func.count()).select_from(SpinPurchase))

    return {
        "real_revenue": 0,
        "test_stars_spent": total_test_stars_spent or 0,
        "total_purchases": total_purchases or 0,
        "note": "test data, not revenue",
    }


@router.get("/spin-packages")
async def list_admin_packages(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(SpinPackage).order_by(SpinPackage.position))
    packages = result.scalars().all()
    return {
        "packages": [
            {
                "id": p.id,
                "name": p.name,
                "spins_count": p.spins_count,
                "price_test_stars": p.price_test_stars,
                "is_active": p.is_active,
                "position": p.position,
            }
            for p in packages
        ]
    }


class PackageCreateRequest(BaseModel):
    name: str
    spins_count: int
    price_test_stars: int
    is_active: bool = True
    position: int = 0


@router.post("/spin-packages")
async def create_package(
    request: PackageCreateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    package = SpinPackage(**request.model_dump())
    session.add(package)
    await session.commit()
    return {"id": package.id}


class PackageUpdateRequest(BaseModel):
    name: str | None = None
    spins_count: int | None = None
    price_test_stars: int | None = None
    is_active: bool | None = None
    position: int | None = None


@router.patch("/spin-packages/{package_id}")
async def update_package(
    package_id: int,
    request: PackageUpdateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    package = await session.get(SpinPackage, package_id)
    if not package:
        raise HTTPException(status_code=404, detail="Package not found")
    for key, value in request.model_dump(exclude_unset=True).items():
        setattr(package, key, value)
    await session.commit()
    return {"id": package.id}


@router.get("/welcome-pool")
async def get_welcome_pool(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(WelcomeRewardItem, ContentItem)
        .join(ContentItem, WelcomeRewardItem.content_item_id == ContentItem.id)
        .order_by(WelcomeRewardItem.position)
    )
    items = result.all()
    return {
        "items": [
            {
                "id": wri.id,
                "content_item_id": ci.id,
                "title": ci.title,
                "status": ci.status.value,
            }
            for wri, ci in items
        ]
    }


class WelcomePoolUpdateRequest(BaseModel):
    content_item_ids: list[int]


@router.put("/welcome-pool")
async def update_welcome_pool(
    request: WelcomePoolUpdateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    wheel_result = await session.execute(
        select(Wheel).where(Wheel.status == "active").limit(1)
    )
    wheel = wheel_result.scalars().first()
    if not wheel:
        raise HTTPException(status_code=400, detail="No active wheel")

    valid_items_result = await session.execute(
        select(WheelSegment.content_item_id)
        .join(ContentItem, WheelSegment.content_item_id == ContentItem.id)
        .where(
            WheelSegment.wheel_id == wheel.id,
            WheelSegment.is_active == True,
            ContentItem.status == ContentStatus.PUBLISHED,
        )
        .distinct()
    )
    valid_item_ids = {row[0] for row in valid_items_result.all()}

    for item_id in request.content_item_ids:
        if item_id not in valid_item_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Content item {item_id} is not a published card in active wheel",
            )

    await session.execute(WelcomeRewardItem.__table__.delete())

    for position, item_id in enumerate(request.content_item_ids):
        session.add(WelcomeRewardItem(content_item_id=item_id, position=position))

    await session.commit()
    return {"updated": True}


@router.get("/wheels")
async def list_wheels(
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(Wheel))
    wheels = result.scalars().all()
    return {
        "wheels": [
            {"id": w.id, "name": w.name, "status": w.status.value}
            for w in wheels
        ]
    }


class WheelCreateRequest(BaseModel):
    name: str


@router.post("/wheels")
async def create_wheel(
    request: WheelCreateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        update(Wheel).where(Wheel.status == "active").values(status="inactive")
    )
    wheel = Wheel(name=request.name, status="active")
    session.add(wheel)
    await session.commit()
    return {"id": wheel.id}


class SegmentUpdateRequest(BaseModel):
    segments: list[dict]


class SegmentAddRequest(BaseModel):
    content_item_id: int
    label: str
    weight: int
    position: int


@router.post("/wheels/{wheel_id}/segments")
async def add_wheel_segment(
    wheel_id: int,
    request: SegmentAddRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    wheel = await session.get(Wheel, wheel_id)
    if not wheel:
        raise HTTPException(status_code=404, detail="Wheel not found")

    if request.weight <= 0:
        raise HTTPException(status_code=400, detail="Weight must be positive")

    content_item = await session.get(ContentItem, request.content_item_id)
    if not content_item:
        raise HTTPException(status_code=400, detail="Content item not found")

    existing_result = await session.execute(
        select(WheelSegment.position).where(WheelSegment.wheel_id == wheel_id)
    )
    existing_positions = {row[0] for row in existing_result.all()}

    if request.position in existing_positions:
        raise HTTPException(status_code=400, detail="Position already taken")

    segment = WheelSegment(
        wheel_id=wheel_id,
        content_item_id=request.content_item_id,
        label=request.label,
        weight=request.weight,
        is_active=True,
        position=request.position,
    )
    session.add(segment)
    await session.commit()
    return {"id": segment.id}


@router.put("/wheels/{wheel_id}/segments")
async def update_wheel_segments(
    wheel_id: int,
    request: SegmentUpdateRequest,
    admin_id: int = Depends(get_current_admin),
    session: AsyncSession = Depends(get_session),
):
    wheel = await session.get(Wheel, wheel_id)
    if not wheel:
        raise HTTPException(status_code=404, detail="Wheel not found")

    positions = [s["position"] for s in request.segments]
    if len(positions) != len(set(positions)):
        raise HTTPException(status_code=400, detail="Duplicate positions in segments")

    for seg_data in request.segments:
        if seg_data.get("weight", 0) <= 0:
            raise HTTPException(status_code=400, detail="Weight must be positive")

        content_item = await session.get(ContentItem, seg_data["content_item_id"])
        if not content_item:
            raise HTTPException(status_code=400, detail="Content item not found")

    existing_result = await session.execute(
        select(WheelSegment).where(WheelSegment.wheel_id == wheel_id)
    )
    existing_segments = {s.id: s for s in existing_result.scalars().all()}

    used_result = await session.execute(
        select(WheelSegment.id)
        .join(Spin, Spin.segment_id == WheelSegment.id)
        .where(WheelSegment.wheel_id == wheel_id)
        .distinct()
    )
    used_segment_ids = {row[0] for row in used_result.all()}

    new_segment_ids = set()
    for seg_data in request.segments:
        seg_id = seg_data.get("segment_id")
        if seg_id is not None:
            if seg_id not in existing_segments or existing_segments[seg_id].wheel_id != wheel_id:
                raise HTTPException(status_code=400, detail=f"Segment {seg_id} does not belong to wheel {wheel_id}")
            new_segment_ids.add(seg_id)

    for seg_id, seg in existing_segments.items():
        if seg_id not in new_segment_ids:
            if seg_id in used_segment_ids:
                await session.execute(
                    update(WheelSegment).where(WheelSegment.id == seg_id).values(is_active=False)
                )
            else:
                await session.execute(
                    WheelSegment.__table__.delete().where(WheelSegment.id == seg_id)
                )

    for seg_data in request.segments:
        seg_id = seg_data.get("segment_id")
        if seg_id is not None:
            seg = existing_segments.get(seg_id)
            if seg and seg.id in used_segment_ids:
                continue
            await session.execute(
                update(WheelSegment).where(WheelSegment.id == seg_id).values(
                    label=seg_data["label"],
                    weight=seg_data["weight"],
                    is_active=seg_data.get("is_active", True),
                    position=seg_data["position"],
                )
            )
        else:
            segment = WheelSegment(
                wheel_id=wheel_id,
                content_item_id=seg_data["content_item_id"],
                label=seg_data["label"],
                weight=seg_data["weight"],
                is_active=seg_data.get("is_active", True),
                position=seg_data["position"],
            )
            session.add(segment)

    await session.commit()
    return {"updated": True}
