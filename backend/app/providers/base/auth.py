from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class AuthContext:
    organization_id: int
    access_token: str
    refresh_token: Optional[str]
    expires_at: datetime
