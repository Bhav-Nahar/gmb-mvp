from enum import Enum

class IneligibilityReason(str, Enum):
    INSUFFICIENT_REVIEWS = "insufficient_reviews"
    INSUFFICIENT_SYNC_HISTORY = "insufficient_sync_history"
    INSUFFICIENT_REVIEWS_AND_SYNC_HISTORY = "insufficient_reviews_and_sync_history"
