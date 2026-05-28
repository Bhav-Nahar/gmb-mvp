# SLA tier thresholds in hours
SLA_BEST_HOURS: int    = 12
SLA_GOOD_HOURS: int    = 24
SLA_AVERAGE_HOURS: int = 72

# Tier label strings
SLA_TIER_BEST    = "Best"
SLA_TIER_GOOD    = "Good"
SLA_TIER_AVERAGE = "Average"
SLA_TIER_POOR    = "Poor"

SLA_TIER_LIST: list[str] = [SLA_TIER_BEST, SLA_TIER_GOOD, SLA_TIER_AVERAGE, SLA_TIER_POOR]

def get_sla_tier(response_hours: float) -> str:
    if response_hours <= SLA_BEST_HOURS:
        return SLA_TIER_BEST
    elif response_hours <= SLA_GOOD_HOURS:
        return SLA_TIER_GOOD
    elif response_hours <= SLA_AVERAGE_HOURS:
        return SLA_TIER_AVERAGE
    else:
        return SLA_TIER_POOR
