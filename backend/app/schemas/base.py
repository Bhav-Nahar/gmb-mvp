from pydantic import BaseModel, ConfigDict


class ORMBase(BaseModel):
    """Base for schemas read from ORM objects (from_attributes=True)."""
    model_config = ConfigDict(from_attributes=True)
