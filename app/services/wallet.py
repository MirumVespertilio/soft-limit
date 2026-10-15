from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wallet import UserWallet, WalletTransaction, TransactionResource, TransactionReason
from app.models.user import User


class InsufficientBalanceError(Exception):
    pass


async def get_wallet_by_user_id(session: AsyncSession, user_id: int) -> UserWallet:
    result = await session.execute(select(UserWallet).where(UserWallet.user_id == user_id))
    wallet = result.scalar_one_or_none()
    if wallet is None:
        raise ValueError("Wallet not found")
    return wallet


async def adjust_balance(
    session: AsyncSession,
    user_id: int,
    resource: TransactionResource,
    amount: int,
    reason: TransactionReason,
    performed_by: int | None = None,
    reference_id: str | None = None,
    note: str | None = None,
) -> WalletTransaction:
    wallet = await get_wallet_by_user_id(session, user_id)

    if resource == TransactionResource.TEST_STARS:
        new_balance = wallet.test_stars_balance + amount
        if new_balance < 0:
            raise InsufficientBalanceError("Insufficient test stars")
        wallet.test_stars_balance = new_balance
    elif resource == TransactionResource.SPINS:
        new_balance = wallet.spins_balance + amount
        if new_balance < 0:
            raise InsufficientBalanceError("Insufficient spins")
        wallet.spins_balance = new_balance

    tx = WalletTransaction(
        wallet_id=wallet.id,
        resource=resource,
        amount=amount,
        reason=reason,
        performed_by=performed_by,
        reference_id=reference_id,
        note=note,
    )
    session.add(tx)
    await session.flush()
    return tx
