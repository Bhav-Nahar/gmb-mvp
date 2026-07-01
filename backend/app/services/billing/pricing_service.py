from typing import Dict
from fastapi import HTTPException
from app.core import plan_config


class PricingService:
    """Computes per-location pricing and entitlements. Server is the single
    source of truth for all prices — never trust amounts sent by the client."""

    @staticmethod
    def validate_location_count(location_count: int) -> int:
        if not isinstance(location_count, int):
            raise HTTPException(status_code=400, detail="location_count must be an integer")
        if location_count < plan_config.MIN_LOCATIONS or location_count > plan_config.MAX_LOCATIONS:
            raise HTTPException(
                status_code=400,
                detail=f"location_count must be between {plan_config.MIN_LOCATIONS} and {plan_config.MAX_LOCATIONS}",
            )
        return location_count

    @staticmethod
    def compute_monthly_price_paise(location_count: int, plan_tier: str = "basic",
                                    custom_per_location_paise: int | None = None) -> int:
        """Monthly total. With a negotiated per-location rate (enterprise custom pricing)
        it's a flat `count * rate`; otherwise the standard graduated tiers apply, where
        each location is priced at the band it falls into."""
        PricingService.validate_location_count(location_count)
        if custom_per_location_paise is not None:
            return location_count * custom_per_location_paise
        total = 0
        prev_bound = 0
        for upper, price in plan_config.get_plan(plan_tier)["price_tiers"]:
            band_top = location_count if upper is None else min(location_count, upper)
            slots_in_band = max(0, band_top - prev_bound)
            total += slots_in_band * price
            prev_bound = upper if upper is not None else prev_bound
            if upper is not None and location_count <= upper:
                break
        return total

    @staticmethod
    def compute_price_paise(location_count: int, interval: str = "monthly", plan_tier: str = "basic",
                            custom_per_location_paise: int | None = None) -> int:
        monthly = PricingService.compute_monthly_price_paise(location_count, plan_tier, custom_per_location_paise)
        if interval == "annual":
            # Negotiated custom rates are final — the annual discount is NOT applied on top
            # (the rate you set IS the rate). Standard pricing keeps the 20% annual discount.
            if custom_per_location_paise is not None:
                return monthly * plan_config.ANNUAL_MONTHS
            annual = monthly * plan_config.ANNUAL_MONTHS
            return int(annual * (1 - plan_config.ANNUAL_DISCOUNT))
        return monthly

    @staticmethod
    def get_credits_for_locations(location_count: int, plan_tier: str = "basic",
                                  custom_credits_per_location: int | None = None) -> int:
        per = (custom_credits_per_location if custom_credits_per_location is not None
               else plan_config.get_plan(plan_tier)["credits_per_location"])
        return location_count * per

    @staticmethod
    def marginal_monthly_paise(current_quota: int, added: int, interval: str = "monthly", plan_tier: str = "basic",
                               custom_per_location_paise: int | None = None) -> int:
        """Cost of going from current_quota -> current_quota + added.

        Pricing is graduated, so the marginal cost is the DELTA of the two totals,
        not a flat per-location price (the added locations sit in whatever band they
        fall into). With a custom per-location rate it reduces to `added * rate`."""
        if added <= 0:
            return 0
        new_total = current_quota + added
        return PricingService.compute_price_paise(new_total, interval, plan_tier, custom_per_location_paise) \
            - PricingService.compute_price_paise(current_quota, interval, plan_tier, custom_per_location_paise)

    @staticmethod
    def prorated_addon_paise(
        current_quota: int,
        added: int,
        interval: str,
        days_left: int,
        days_in_cycle: int,
        plan_tier: str = "basic",
        custom_per_location_paise: int | None = None,
    ) -> int:
        """Prorate the marginal monthly/annual cost for the remainder of the current
        billing cycle. Clamped to [0, full marginal]."""
        marginal = PricingService.marginal_monthly_paise(current_quota, added, interval, plan_tier,
                                                          custom_per_location_paise)
        if marginal <= 0:
            return 0
        if days_in_cycle <= 0:
            return marginal
        days_left = max(0, min(days_left, days_in_cycle))
        return max(0, min(marginal, round(marginal * days_left / days_in_cycle)))

    @staticmethod
    def get_topup_pack(pack_key: str) -> Dict[str, int]:
        pack = plan_config.AI_TOPUP_PACKS.get(pack_key)
        if not pack:
            raise HTTPException(status_code=400, detail=f"Unknown top-up pack: {pack_key}")
        return pack
