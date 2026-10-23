"""Telegram Stars payment verification.

Server-side verification of Stars payments:
1. Any Stars invoice creation records a `Order` (status=CREATED) and returns a
   payload of `order:<order_id>:<idempotency_key>` for the Telegram invoice.
2. The model bot webhook answers pre_checkout_query and, on successful_payment,
   parses the payload and marks the Order PAID + stores a PaymentAttempt with
   the telegram_payment_charge_id (idempotent by that charge id).
3. The complete endpoints do not trust the client: they look up the idempotent
   PaymentAttempt (via idempotency_key) belonging to the user, check amount/currency
   and only then credit anything. If the webhook has not arrived yet (race),
   the endpoints return 409 so the frontend can retry.
"""

import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order import Order, OrderStatus, PaymentAttempt, PaymentProvider

logger = logging.getLogger(__name__)


def build_invoice_payload(order_id: int, idempotency_key: str) -> str:
    return f"order:{order_id}:{idempotency_key}"


def parse_invoice_payload(payload: str) -> tuple[int, str] | None:
    """Return (order_id, idempotency_key) or None for malformed payloads."""
    parts = payload.split(":")
    if len(parts) != 3 or parts[0] != "order":
        return None
    try:
        order_id = int(parts[1])
    except ValueError:
        return None
    return order_id, parts[2]


async def create_order(
    session: AsyncSession,
    user_id: int,
    product_type: str,
    product_id: int | None,
    amount: int,
    currency: str = "XTR",
) -> Order:
    order = Order(
        user_id=user_id,
        product_type=product_type,
        product_id=product_id,
        quantity=1,
        amount=amount,
        currency=currency,
        status=OrderStatus.CREATED,
    )
    session.add(order)
    await session.commit()
    return order


async def record_successful_payment(
    session: AsyncSession,
    payload: str,
    telegram_payment_charge_id: str,
    amount: int,
    currency: str = "XTR",
) -> Order | None:
    """Webhook side: mark order PAID and record the PaymentAttempt (idempotent)."""
    parsed = parse_invoice_payload(payload)
    if parsed is None:
        logger.warning("Malformed invoice payload: %r", payload)
        return None
    order_id, idempotency_key = parsed

    order = await session.get(Order, order_id)
    if not order:
        logger.warning("Payment for unknown order %s (payload=%r)", order_id, payload)
        return None

    if order.status == OrderStatus.PAID:
        return order

    if order.currency != currency or order.amount != amount:
        logger.warning(
            "Payment amount/currency mismatch for order %s: expected %s/%s got %s/%s",
            order.id,
            order.amount,
            order.currency,
            amount,
            currency,
        )
        return None

    existing_attempt = await session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.external_id == telegram_payment_charge_id)
    )
    if existing_attempt:
        return order

    order.status = OrderStatus.PAID
    session.add(
        PaymentAttempt(
            order_id=order.id,
            provider=PaymentProvider.TELEGRAM_STARS,
            external_id=telegram_payment_charge_id,
            status="completed",
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
        )
    )
    await session.commit()
    return order


async def get_verified_payment(
    session: AsyncSession,
    user_id: int,
    idempotency_key: str,
    expected_amount: int | None = None,
) -> PaymentAttempt:
    """Fetch a payment record verified for this user's idempotency key.

    Raises 409 HTTPException if the payment has not been confirmed yet (race),
    so the frontend can retry after a delay.
    """
    query = (
        select(PaymentAttempt, Order)
        .join(Order, PaymentAttempt.order_id == Order.id)
        .where(
            PaymentAttempt.idempotency_key == idempotency_key,
            Order.user_id == user_id,
            Order.status == OrderStatus.PAID,
        )
        .order_by(PaymentAttempt.id.desc())
        .limit(1)
    )
    row = (await session.execute(query)).first()
    if row is None:
        raise HTTPException(
            status_code=409,
            detail="Payment is not confirmed yet, try again in a few seconds",
        )
    attempt, order = row
    if expected_amount is not None and attempt.amount != expected_amount:
        logger.warning(
            "Verified amount mismatch for order %s: attempt %s vs expected %s",
            order.id,
            attempt.amount,
            expected_amount,
        )
        raise HTTPException(status_code=400, detail="Payment amount mismatch")
    return attempt
