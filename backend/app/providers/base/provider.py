from abc import ABC, abstractmethod
from typing import List, ClassVar, Dict, Any
import datetime
from datetime import date
from .models import LocationModel, ReviewModel, ReviewReplyModel, PostModel, DailyInsightMetric, KeywordInsightMetric

class BaseProvider(ABC):
    provider_name: ClassVar[str]

    @classmethod
    def get_oauth_url(cls, state: str) -> str:
        """Generate the OAuth login URL for the provider."""
        raise NotImplementedError()

    @classmethod
    def exchange_code_for_tokens(cls, code: str) -> Dict[str, Any]:
        """Exchange auth code for access tokens."""
        raise NotImplementedError()

    @abstractmethod
    async def get_locations(self) -> List[LocationModel]:
        """Fetch all locations for the authenticated context."""
        ...

    @abstractmethod
    async def get_reviews(self, location_id: str, safe_cutoff_time: datetime.datetime = None) -> List[ReviewModel]:
        """Fetch all reviews for a specific location."""
        ...

    @abstractmethod
    async def reply_review(self, review_id: str, reply_text: str) -> ReviewReplyModel:
        """Reply to a specific review."""
        ...

    @abstractmethod
    async def create_post(self, location_id: str, payload: Dict[str, Any]) -> PostModel:
        """
        Create a new post for a specific location.
        
        Note: Phase 3 workers may invoke provider publishing synchronously (e.g. using asyncio.run) 
        for operational simplicity. However, provider implementations must remain async-capable 
        internally, and future providers may use async execution patterns. Do NOT tightly couple 
        the architecture to sync-only assumptions.
        """
        ...

    @abstractmethod
    async def get_insights(self, location_id: str, start_date: date, end_date: date) -> List[DailyInsightMetric]:
        """Fetch performance insights for a location for a date range."""
        ...

    @abstractmethod
    async def get_search_keyword_insights(self, location_id: str, start_date: date, end_date: date) -> List["KeywordInsightMetric"]:
        """Fetch monthly search keyword impressions for a location for a date range."""
        ...

