from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from app.models.campaign import CampaignStatus


class CampaignCreate(BaseModel):
    organization_id: UUID
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = []
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CampaignUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CampaignStatus] = None
    tags: Optional[List[str]] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class CampaignOut(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str]
    status: CampaignStatus
    tags: List[str]
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
