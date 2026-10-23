from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.types import LabeledPrice

from app.api.deps import get_current_user, get_current_user_id, CurrentUser
from app.db import get_session
from app.models.purchases import SpinPackage, SpinPurchase
from app.models.wallet import GemPackage, GemPurchase, TransactionResource, TransactionReason
from app.services.wallet import adjust_balance, InsufficientBalanceError
from app.telegram import create_telegram_bot

router = APIRouter(prefix="/api/v1", tags=["purchases"])


# ==============================================================================
# Покупка спинов за GEMS (внутренняя валюта)
# ==============================================================================

@router.get("/spin-packages")
async def list_spin_packages(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    query = select(SpinPackage).where(SpinPackage.is_active == True)
    if current_user.model_id is not None:
        query = query.where(
            (SpinPackage.model_id == None) | (SpinPackage.model_id == current_user.model_id)
        )
    result = await session.execute(query.order_by(SpinPackage.position))
    packages = result.scalars().all()
    return {
        "packages": [
            {
                "id": p.id,
                "name": p.name,
                "spins_count": p.spins_count,
                "price_gems": p.price_gems,
                "model_id": p.model_id,
            }
            for p in packages
        ]
    }


class SpinPurchaseRequest(BaseModel):
    package_id: int
    idempotency_key: str


class SpinPurchaseResponse(BaseModel):
    purchase_id: int
    spins_added: int
    price_gems: int


@router.post("/spin-purchases", response_model=SpinPurchaseResponse)
async def purchase_spin_package(
    request: SpinPurchaseRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    user_id = current_user.id
    idem_key = request.idempotency_key

    existing = await session.execute(
        select(SpinPurchase).where(
            SpinPurchase.user_id == user_id,
            SpinPurchase.idempotency_key == idem_key,
        )
    )
    existing_purchase = existing.scalar_one_or_none()
    if existing_purchase:
        return SpinPurchaseResponse(
            purchase_id=existing_purchase.id,
            spins_added=existing_purchase.spins_added,
            price_gems=existing_purchase.price_gems,
        )

    package = await session.get(SpinPackage, request.package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Package not found")
    if package.model_id is not None and package.model_id != current_user.model_id:
        raise HTTPException(status_code=404, detail="Package not found")

    try:
        await adjust_balance(
            session=session,
            user_id=user_id,
            resource=TransactionResource.GEMS,
            amount=-package.price_gems,
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
        raise HTTPException(status_code=400, detail="Insufficient gems")

    purchase = SpinPurchase(
        user_id=user_id,
        package_id=package.id,
        price_gems=package.price_gems,
        spins_added=package.spins_count,
        model_id=package.model_id,
        idempotency_key=idem_key,
    )
    session.add(purchase)
    await session.commit()

    return SpinPurchaseResponse(
        purchase_id=purchase.id,
        spins_added=package.spins_count,
        price_gems=package.price_gems,
    )


# ==============================================================================
# Покупка GEMS за реальные Telegram Stars (Payments API)
# ==============================================================================

@router.get("/gem-packages")
async def list_gem_packages(
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(GemPackage).where(GemPackage.is_active == True).order_by(GemPackage.position)
    )
    packages = result.scalars().all()
    return {
        "packages": [
            {
                "id": p.id,
                "name": p.name,
                "gems_amount": p.gems_amount,
                "price_stars": p.price_stars,
            }
            for p in packages
        ]
    }


class CreateInvoiceLinkRequest(BaseModel):
    package_id: int


class CreateInvoiceLinkResponse(BaseModel):
    invoice_link: str
    package_id: int
    gems_amount: int
    price_stars: int


@router.post("/gem-purchases/invoice-link", response_model=CreateInvoiceLinkResponse)
async def create_gem_invoice_link(
    request: CreateInvoiceLinkRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Создает invoice link Telegram Stars для открытия встроенного окна оплаты Telegram."""
    package = await session.get(GemPackage, request.package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Gem package not found")

    payload = f"gems_{user_id}_{package.id}"
    bot = create_telegram_bot()
    try:
        invoice_link = await bot.create_invoice_link(
            title=f"{package.gems_amount} Gems",
            description=f"Покупка {package.gems_amount} гемов для использования в приложении",
            payload=payload,
            currency="XTR",  # Telegram Stars currency code
            prices=[LabeledPrice(label=f"{package.gems_amount} Gems", amount=package.price_stars)],
        )
    finally:
        await bot.session.close()

    return CreateInvoiceLinkResponse(
        invoice_link=invoice_link,
        package_id=package.id,
        gems_amount=package.gems_amount,
        price_stars=package.price_stars,
    )


class CompleteGemPurchaseRequest(BaseModel):
    package_id: int
    idempotency_key: str
    telegram_payment_charge_id: str | None = None


class CompleteGemPurchaseResponse(BaseModel):
    purchase_id: int
    gems_added: int
    price_stars: int


@router.post("/gem-purchases/complete", response_model=CompleteGemPurchaseResponse)
async def complete_gem_purchase(
    request: CompleteGemPurchaseRequest,
    user_id: int = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    """Начисляет GEMS пользователю после подтверждения платежа Telegram Stars (идемпотентно)."""
    idem_key = request.idempotency_key

    existing = await session.execute(
        select(GemPurchase).where(
            GemPurchase.user_id == user_id,
            GemPurchase.idempotency_key == idem_key,
        )
    )
    existing_purchase = existing.scalar_one_or_none()
    if existing_purchase:
        return CompleteGemPurchaseResponse(
            purchase_id=existing_purchase.id,
            gems_added=existing_purchase.gems_added,
            price_stars=existing_purchase.price_stars,
        )

    package = await session.get(GemPackage, request.package_id)
    if not package or not package.is_active:
        raise HTTPException(status_code=404, detail="Gem package not found")

    # Начисляем GEMS на баланс пользователя
    await adjust_balance(
        session=session,
        user_id=user_id,
        resource=TransactionResource.GEMS,
        amount=package.gems_amount,
        reason=TransactionReason.TELEGRAM_STARS_PURCHASE,
        reference_id=str(package.id),
        note=request.telegram_payment_charge_id,
    )

    purchase = GemPurchase(
        user_id=user_id,
        package_id=package.id,
        gems_added=package.gems_amount,
        price_stars=package.price_stars,
        telegram_payment_charge_id=request.telegram_payment_charge_id,
        idempotency_key=idem_key,
    )
    session.add(purchase)
    await session.commit()

    return CompleteGemPurchaseResponse(
        purchase_id=purchase.id,
        gems_added=package.gems_amount,
        price_stars=package.price_stars,
    )
