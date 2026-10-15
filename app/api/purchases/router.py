from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db import get_session
from app.models.purchases import SpinPackage, SpinPurchase
from app.models.wallet import TransactionResource, TransactionReason
from app.services.wallet import adjust_balance, InsufficientBalanceError

router = APIRouter(prefix="/api/v1", tags=["purchases"])


@router.get("/spin-packages")
async def list_packages(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(SpinPackage).where(SpinPackage.is_active == True).order_by(SpinPackage.position)
    )
    packages = result.scalars().all()
    return {
        "packages": [
            {
                "id": p.id,
                "name": p.name,
                "spins_count": p.spins_count,
                "price_test_stars": p.price_test_stars,
            }
            for p in packages
        ]
    }


class PurchaseRequest(BaseModel):
    package_id: int
    idempotency_key: str


class PurchaseResponse(BaseModel):
    purchase_id: int
    spins_added: int
    price_test_stars: int


@router.post("/spin-purchases", response_model=PurchaseResponse)
async def purchase_package(
    request: PurchaseRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    idem_key = request.idempotency_key

    existing = await session.execute(
        select(SpinPurchase).where(
            SpinPurchase.user_id == user_id,
            SpinPurchase.idempotency_key == idem_key,
        )
    )
    existing_purchase = existing.scalar_one_or_none()
    if existing_purchase:
        return PurchaseResponse(
            purchase_id=existing_purchase.id,
            spins_added=existing_purchase.spins_added,
            price_test_stars=existing_purchase.price_test_stars,
        )

    package = await session.get(SpinPackage, request.package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Package not found")

    try:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.TEST_STARS,
            amount=-package.price_test_stars,
            reason=TransactionReason.PURCHASE,
            reference_id=str(package.id),
        )
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.SPINS,
            amount=package.spins_count,
            reason=TransactionReason.PURCHASE,
            reference_id=str(package.id),
        )
    except InsufficientBalanceError:
        raise HTTPException(status_code=400, detail="Insufficient test stars")

    purchase = SpinPurchase(
        user_id=user_id,
        package_id=package.id,
        price_test_stars=package.price_test_stars,
        spins_added=package.spins_count,
        idempotency_key=idem_key,
    )
    session.add(purchase)
    await session.commit()

    return PurchaseResponse(
        purchase_id=purchase.id,
        spins_added=package.spins_count,
        price_test_stars=package.price_test_stars,
    )
