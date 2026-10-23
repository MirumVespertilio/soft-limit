"""Admin analytics aggregates.

Collects revenue (GEMS / Telegram Stars / USD), spin counts by type,
purchase conversion, duplicates and per-model breakdowns for /admin/stats.
"""
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.model import Model
from app.models.spin import Spin, SpinType
from app.models.spin_result import SpinResult, Rarity
from app.models.purchases import SpinPurchase
from app.models.wallet import GemPurchase

from app.config import settings
from app.services.rate import get_ton_usd_rate

logger = logging.getLogger(__name__)

PERIOD_STARTS = {
    "day": timedelta(days=1),
    "week": timedelta(days=7),
    "month": timedelta(days=30),
    "all": None,
}

DAILY_WINDOW_DAYS = 30


def _cutoff(stage: str) -> datetime | None:
    delta = PERIOD_STARTS.get(stage)
    if delta is None:
        return None
    return datetime.now(timezone.utc) - delta


def _spins_by_type_dict(rows) -> dict[str, int]:
    counts = {t.value: 0 for t in SpinType}
    for row in rows:
        spin_type, count = row[0], row[1]
        counts[spin_type.value if hasattr(spin_type, "value") else str(spin_type)] = count
    return counts


def _empty_type_dict() -> dict[str, int]:
    return {t.value: 0 for t in SpinType}


async def _spin_totals(session, cutoff, model_id):
    query = select(
        Spin.spin_type,
        func.count().label("spins"),
        func.coalesce(func.sum(Spin.cost_gems), 0).label("gems"),
        func.coalesce(func.sum(Spin.cost_stars), 0).label("stars"),
    ).group_by(Spin.spin_type)
    if cutoff is not None:
        query = query.where(Spin.created_at >= cutoff)
    if model_id is not None:
        query = query.where(Spin.model_id == model_id)
    result = await session.execute(query)
    return result.all()


async def _purchase_totals(session, cutoff, model_id):
    spin_q = select(
        func.count().label("cnt"),
        func.coalesce(func.sum(SpinPurchase.price_gems), 0),
    )
    gem_q = select(
        func.count().label("cnt"),
        func.coalesce(func.sum(GemPurchase.price_stars), 0),
    )
    if cutoff is not None:
        spin_q = spin_q.where(SpinPurchase.created_at >= cutoff)
        gem_q = gem_q.where(GemPurchase.created_at >= cutoff)
    if model_id is not None:
        spin_q = spin_q.where(SpinPurchase.model_id == model_id)
    spin_row = (await session.execute(spin_q)).one()
    gem_row = (await session.execute(gem_q)).one()
    return {
        "spin_purchases": spin_row[0],
        "spin_purchase_gems": spin_row[1],
        "gem_purchases": gem_row[0],
        "gem_purchase_stars": gem_row[1],
    }


async def _buyer_count(session, cutoff, model_id):
    """Distinct users who made at least one purchase (spins or GEMS) in period."""
    spin_q = select(SpinPurchase.user_id, SpinPurchase.created_at)
    gem_q = select(GemPurchase.user_id, GemPurchase.created_at)
    if model_id is not None:
        spin_q = spin_q.where(SpinPurchase.model_id == model_id)
    spin_ids = await session.execute(spin_q)
    gem_ids = await session.execute(gem_q)
    entries = [
        (uid, created or datetime.now(timezone.utc))
        for uid, created in spin_ids.all()
    ] + [
        (uid, created or datetime.now(timezone.utc))
        for uid, created in gem_ids.all()
    ]
    if cutoff is not None:
        entries = [e for e in entries if e[1] and e[1] >= cutoff]
    return len({uid for uid, _ in entries})


async def _user_counts(session, cutoff):
    total = await session.scalar(select(func.count()).select_from(User))
    if cutoff is not None:
        new_users = await session.scalar(
            select(func.count()).select_from(User).where(User.registered_at >= cutoff)
        )
    else:
        new_users = total
    return {"total": total or 0, "new": new_users or 0}


async def _result_totals(session, cutoff, model_id):
    query = (
        select(
            func.count().label("results"),
            func.sum(case((SpinResult.is_duplicate == True, 1), else_=0)).label("duplicates"),
            func.coalesce(func.sum(SpinResult.reward_gems), 0).label("refunds"),
        )
        .select_from(SpinResult)
        .join(Spin, Spin.id == SpinResult.spin_id)
    )
    rarity_q = (
        select(SpinResult.rarity, func.count())
        .select_from(SpinResult)
        .join(Spin, Spin.id == SpinResult.spin_id)
        .group_by(SpinResult.rarity)
    )
    if cutoff is not None:
        query = query.where(Spin.created_at >= cutoff)
        rarity_q = rarity_q.where(Spin.created_at >= cutoff)
    if model_id is not None:
        query = query.where(Spin.model_id == model_id)
        rarity_q = rarity_q.where(Spin.model_id == model_id)
    row = (await session.execute(query)).one()
    rarity_rows = (await session.execute(rarity_q)).all()
    counts = {r.value: 0 for r in Rarity}
    for rarity, count in rarity_rows:
        counts[rarity.value if hasattr(rarity, "value") else str(rarity)] = count
    return {
        "results": row[0] or 0,
        "duplicates": row[1] or 0,
        "duplicate_refund_gems": row[2] or 0,
        "results_by_rarity": counts,
    }


async def _per_model(session, cutoff):
    """Aggregates grouped by model_id (spins + purchases). Models with data only."""
    spin_q = (
        select(
            Spin.model_id,
            Spin.spin_type,
            func.count().label("spins"),
            func.coalesce(func.sum(Spin.cost_gems), 0).label("gems"),
            func.coalesce(func.sum(Spin.cost_stars), 0).label("stars"),
        )
        .where(Spin.model_id != None)
        .group_by(Spin.model_id, Spin.spin_type)
    )
    spin_purchase_q = (
        select(
            SpinPurchase.model_id,
            func.count(),
            func.coalesce(func.sum(SpinPurchase.price_gems), 0),
        )
        .where(SpinPurchase.model_id != None)
        .group_by(SpinPurchase.model_id)
    )
    if cutoff is not None:
        spin_q = spin_q.where(Spin.created_at >= cutoff)
        spin_purchase_q = spin_purchase_q.where(SpinPurchase.created_at >= cutoff)

    spin_rows = (await session.execute(spin_q)).all()
    purchase_rows = (await session.execute(spin_purchase_q)).all()

    models_result = await session.execute(select(Model.id, Model.name))
    names = {m_id: m_name for m_id, m_name in models_result.all()}

    per_model: dict[int, dict] = {}
    for model_id, spin_type, count, gems, stars in spin_rows:
        entry = per_model.setdefault(model_id, {
            "model_id": model_id,
            "model_name": names.get(model_id, f"Model #{model_id}"),
            "spins": 0,
            "spins_by_type": _empty_type_dict(),
            "revenue_gems_spent": 0,
            "revenue_stars": 0,
            "spin_purchases": 0,
        })
        entry["spins"] += count
        entry["spins_by_type"][
            spin_type.value if hasattr(spin_type, "value") else str(spin_type)
        ] += count
        entry["revenue_gems_spent"] += gems
        entry["revenue_stars"] += stars
    for model_id, count, gems in purchase_rows:
        entry = per_model.setdefault(model_id, {
            "model_id": model_id,
            "model_name": names.get(model_id, f"Model #{model_id}"),
            "spins": 0,
            "spins_by_type": _empty_type_dict(),
            "revenue_gems_spent": 0,
            "revenue_stars": 0,
            "spin_purchases": 0,
        })
        entry["spin_purchases"] += count
        entry["revenue_gems_spent"] += gems

    return sorted(per_model.values(), key=lambda e: e["spins"] + e["spin_purchases"], reverse=True)


async def _daily_series(session, model_id):
    """Last N days: spins by type + revenue (GEMS + Stars->USD) per day."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=DAILY_WINDOW_DAYS)
    spin_q = (
        select(
            func.date(Spin.created_at).label("day"),
            Spin.spin_type,
            func.count(),
            func.coalesce(func.sum(Spin.cost_gems), 0),
            func.coalesce(func.sum(Spin.cost_stars), 0),
        )
        .where(Spin.created_at >= cutoff)
        .group_by("day", Spin.spin_type)
        .order_by("day")
    )
    spin_purchase_q = (
        select(
            func.date(SpinPurchase.created_at).label("day"),
            func.count(),
            func.coalesce(func.sum(SpinPurchase.price_gems), 0),
        )
        .where(SpinPurchase.created_at >= cutoff)
        .group_by("day")
    )
    gem_purchase_q = (
        select(
            func.date(GemPurchase.created_at).label("day"),
            func.coalesce(func.sum(GemPurchase.price_stars), 0),
        )
        .where(GemPurchase.created_at >= cutoff)
        .group_by("day")
    )
    if model_id is not None:
        spin_q = spin_q.where(Spin.model_id == model_id)
        spin_purchase_q = spin_purchase_q.where(SpinPurchase.model_id == model_id)

    spin_rows = (await session.execute(spin_q)).all()
    sp_rows = (await session.execute(spin_purchase_q)).all()
    gp_rows = (await session.execute(gem_purchase_q)).all()

    stars_to_usd_factor = await _stars_usd_factor()

    series: dict[str, dict] = {}
    today = datetime.now(timezone.utc).date()
    for offset in range(DAILY_WINDOW_DAYS):
        d = today - timedelta(days=DAILY_WINDOW_DAYS - 1 - offset)
        series[d.isoformat()] = {
            "date": d.isoformat(),
            "spins": 0,
            "spins_by_type": _empty_type_dict(),
            "revenue_gems_spent": 0,
            "revenue_stars": 0,
            "revenue_usd": 0.0,
        }
    rnd3 = lambda v: round(v, 3)

    for day, spin_type, count, gems, stars in spin_rows:
        key = str(day)
        if key not in series:
            continue
        entry = series[key]
        entry["spins"] += count
        entry["spins_by_type"][
            spin_type.value if hasattr(spin_type, "value") else str(spin_type)
        ] += count
        entry["revenue_gems_spent"] += gems
        entry["revenue_stars"] += stars
        entry["revenue_usd"] = rnd3(entry["revenue_usd"] + stars * stars_to_usd_factor)
    for day, count, gems in sp_rows:
        entry = series.get(str(day))
        if entry is None:
            continue
        entry["revenue_gems_spent"] += gems
    for day, stars in gp_rows:
        entry = series.get(str(day))
        if entry is None:
            continue
        entry["revenue_stars"] += stars
        entry["revenue_usd"] = rnd3(entry["revenue_usd"] + stars * stars_to_usd_factor)

    return list(series.values())


async def collect_admin_stats(
    session: AsyncSession,
    period: str = "all",
    model_id: int | None = None,
) -> dict:
    cutoff = _cutoff(period if period in PERIOD_STARTS else "all")

    spin_rows = await _spin_totals(session, cutoff, model_id)
    purchase_totals = await _purchase_totals(session, cutoff, model_id)
    user_counts = await _user_counts(session, cutoff)
    users_total = user_counts["total"]
    users_new = user_counts["new"]
    buyers = await _buyer_count(session, cutoff, model_id)
    results = await _result_totals(session, cutoff, model_id)
    spin_tot = _spins_by_type_dict(spin_rows)

    gems_spent = sum(row[2] for row in spin_rows)
    stars_total = sum(row[3] for row in spin_rows)
    stars_total += purchase_totals["gem_purchase_stars"]
    gems_spent += purchase_totals["spin_purchase_gems"]

    usd_rate = await _stars_usd_factor()
    stars_to_usd_factor = usd_rate
    revenue_usd = round(stars_total * stars_to_usd_factor, 3)

    purchases_total = purchase_totals["spin_purchases"] + purchase_totals["gem_purchases"]
    conversion_rate = round(buyers / users_new, 4) if users_new else 0.0

    per_model = await _per_model(session, cutoff)
    for entry in per_model:
        entry["revenue_usd"] = round(entry["revenue_stars"] * stars_to_usd_factor, 3)

    daily = await _daily_series(session, model_id)

    return {
        "period": period,
        "model_id": model_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "usd_rate": {
            "stars_per_usd_implied": round(1.0 / stars_to_usd_factor, 6) if stars_to_usd_factor else None,
            "ton_usd": round(usd_rate / _stars_per_ton(), 6) if _stars_per_ton() else None,
        },
        "totals": {
            "revenue_gems_spent": gems_spent,
            "revenue_stars": stars_total,
            "revenue_usd": revenue_usd,
            "users_total": users_total,
            "users_new": users_new,
            "buyers": buyers,
            "purchases_total": purchases_total,
            "purchases_by_type": {
                "spin_packages": purchase_totals["spin_purchases"],
                "gem_packages": purchase_totals["gem_purchases"],
            },
            "revenue_by_type": {
                "spin_packages_gems": purchase_totals["spin_purchase_gems"],
                "media_spins_gems": sum(row[2] for row in spin_rows),
                "gem_packages_stars": purchase_totals["gem_purchase_stars"],
                "media_spins_stars": sum(row[3] for row in spin_rows),
            },
            "spins_total": sum(spin_tot.values()),
            "spins_by_type": spin_tot,
            "conversion_rate": conversion_rate,
            "results_total": results["results"],
            "duplicates": results["duplicates"],
            "duplicate_refund_gems": results["duplicate_refund_gems"],
            "results_by_rarity": results["results_by_rarity"],
        },
        "per_model": per_model,
        "daily": daily,
    }


def _stars_per_ton() -> float:
    return settings.STARS_TO_TON_RATE


async def _stars_usd_factor() -> float:
    """USD per 1 Star = (TON per Star) * (USD per TON), live fetch or fallback."""
    ton_usd = await get_ton_usd_rate()
    return settings.STARS_TO_TON_RATE * ton_usd