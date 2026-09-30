from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..dependencies import get_current_user
from ..models import Audience, Campaign, CampaignRun, Contact, Delivery, User
from ..schemas import DashboardSummary
router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

@router.get("/summary", response_model=DashboardSummary)
def summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    audience_ids = select(Audience.id).where(Audience.owner_id == user.id)
    contact_count = db.scalar(select(func.count(Contact.id)).where(Contact.audience_id.in_(audience_ids))) or 0
    audiences = db.scalar(select(func.count(Audience.id)).where(Audience.owner_id == user.id)) or 0
    active = db.scalar(select(func.count(Campaign.id)).where(Campaign.owner_id == user.id, Campaign.status.in_(("queued", "scheduled")))) or 0
    scheduled = db.scalar(select(func.count(Campaign.id)).where(Campaign.owner_id == user.id, Campaign.status == "scheduled")) or 0
    sent = db.scalar(
        select(func.count(Delivery.id))
        .join(CampaignRun, Delivery.run_id == CampaignRun.id)
        .join(Campaign, CampaignRun.campaign_id == Campaign.id)
        .where(Campaign.owner_id == user.id, Delivery.status == "sent")
    ) or 0
    return DashboardSummary(audience_contacts=contact_count, audiences=audiences, active_campaigns=active, scheduled_campaigns=scheduled, sent_deliveries=sent)
