from sqlalchemy import Column, String

from app.db.session import Base


class AppSetting(Base):
    """Global runtime key-value settings — feature flags a super-admin can flip live
    from the admin panel, without an env change + redeploy. One row per key; an
    absent key means "use the env default"."""
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
