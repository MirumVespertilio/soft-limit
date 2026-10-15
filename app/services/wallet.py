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

    if amount >= 0:
        if resource == TransactionResource.TEST_STARS:
            stmt = (
                update(UserWallet)
                .where(UserWallet.user_id == user_id)
                .values(test_stars_balance=UserWallet.test_stars_balance + amount)
            )
        else:
            stmt = (
                update(UserWallet)
                .where(UserWallet.user_id == user_id)
                .values(spins_balance=UserWallet.spins_balance + amount)
            )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Wallet not found")
    else:
        if resource == TransactionResource.TEST_STARS:
            stmt = (
                update(UserWallet)
                .where(
                    UserWallet.user_id == user_id,
                    UserWallet.test_stars_balance >= -amount,
                )
                .values(test_stars_balance=UserWallet.test_stars_balance + amount)
            )
        else:
            stmt = (
                update(UserWallet)
                .where(
                    UserWallet.user_id == user_id,
                    UserWallet.spins_balance >= -amount,
                )
                .values(spins_balance=UserWallet.spins_balance + amount)
            )
        result = await session.execute(stmt)
        if result.rowcount == 0:
            raise InsufficientBalanceError(f"Insufficient {resource.value}")

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
    return tx
