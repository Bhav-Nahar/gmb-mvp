from enum import Enum

class CampaignStatus(str, Enum):
    DRAFT = "Draft"
    QUEUED = "Queued"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"
    PARTIALLY_COMPLETED = "PartiallyCompleted"
    PAUSED = "Paused"
    CANCELLED = "Cancelled"

class PostType(str, Enum):
    UPDATE = "UPDATE"
    EVENT = "EVENT"
    OFFER = "OFFER"

class PostStatus(str, Enum):
    DRAFT = "Draft"
    PENDING_APPROVAL = "PendingApproval"
    APPROVED = "Approved"
    SCHEDULED = "Scheduled"
    PUBLISHING = "Publishing"
    PUBLISHED = "Published"
    FAILED = "Failed"
    REJECTED = "Rejected"
    SHADOW_BANNED = "ShadowBanned"
    DELETED_EXTERNALLY = "DeletedExternally"

class PublishJobStatus(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    SUCCESS = "Success"
    FAILED = "Failed"
    RETRYING = "Retrying"
    REJECTED = "Rejected"
    SHADOW_BANNED = "ShadowBanned"
    PAUSED = "Paused"
    CANCELLED = "Cancelled"

class CallToActionType(str, Enum):
    BOOK = "BOOK"
    ORDER = "ORDER"
    SHOP = "SHOP"
    LEARN_MORE = "LEARN_MORE"
    SIGN_UP = "SIGN_UP"
    CALL = "CALL"

class MediaType(str, Enum):
    PHOTO = "PHOTO"
    VIDEO = "VIDEO"
