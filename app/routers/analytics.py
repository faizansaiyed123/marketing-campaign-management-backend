from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..dependencies import get_current_user
from ..models import Campaign, CampaignEvent, CampaignRun, Delivery, User
router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

@router.get("/overview")
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    base = select(Delivery).join(CampaignRun).join(Campaign).where(Campaign.owner_id == user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    sent = db.scalar(select(func.count()).select_from(base.where(Delivery.status == "sent").subquery())) or 0
    failed = db.scalar(select(func.count()).select_from(base.where(Delivery.status == "failed").subquery())) or 0
    opens = db.scalar(
        select(func.count(func.distinct(CampaignEvent.delivery_id))).join(Delivery).join(CampaignRun).join(Campaign)
        .where(Campaign.owner_id == user.id, CampaignEvent.event_type == "open")
    ) or 0
    clicks = db.scalar(
        select(func.count(func.distinct(CampaignEvent.delivery_id))).join(Delivery).join(CampaignRun).join(Campaign)
        .where(Campaign.owner_id == user.id, CampaignEvent.event_type == "click")
    ) or 0
    return {"deliveries": total, "sent": sent, "failed": failed, "opened": opens, "clicked": clicks}
