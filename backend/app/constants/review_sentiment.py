# SINGLE SOURCE OF TRUTH for all sentiment and category labels.
# Every other file — service, API validation, schemas, frontend types — imports from here.
# Never hardcode these strings anywhere else in the codebase.

# Sentiment labels
ALLOWED_SENTIMENTS: set[str] = {
    "Positive",
    "Neutral",
    "Negative",
    "Angry",
}

# Issue category labels
ALLOWED_ISSUE_CATEGORIES: set[str] = {
    "Staff Praise",
    "Service Issue",
    "Pricing Concern",
    "Cleanliness",
    "Delivery Issue",
    "Wait Time",
    "Product Quality",
    "General Feedback",
}

# Convenience lists for ordered use (dropdowns, API docs)
SENTIMENT_LIST: list[str] = sorted(ALLOWED_SENTIMENTS)
ISSUE_CATEGORY_LIST: list[str] = sorted(ALLOWED_ISSUE_CATEGORIES)
