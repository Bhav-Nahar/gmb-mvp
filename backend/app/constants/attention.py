class AttentionThresholds:
    NEGATIVE_SENTIMENT_SPIKE_THRESHOLD = 0.40  # 40% of reviews are negative
    RESPONSE_RATE_THRESHOLD = 50.0             # Response rate < 50%
    NO_REVIEWS_DAYS = 60                       # No reviews received in last 60 days
    CALL_DROP_PERCENTAGE = 30.0                # 30% drop Month-on-Month
    WEBSITE_CLICK_DROP_PERCENTAGE = 30.0       # 30% drop Month-on-Month
    EVALUATION_WINDOW_DAYS = 30                # Default window to aggregate (e.g. last 30 days)
