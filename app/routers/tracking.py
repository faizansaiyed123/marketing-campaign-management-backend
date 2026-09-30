from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import CampaignEvent, Delivery
router=APIRouter(prefix="/track",tags=["tracking"])
@router.post("/{tracking_token}/{event_type}",status_code=204)
def track(tracking_token:str,event_type:str,db:Session=Depends(get_db)):
    if event_type not in {"open","click"}: raise HTTPException(404,"Unknown tracking event")
    delivery=db.scalar(select(Delivery).where(Delivery.tracking_token==tracking_token))
    if not delivery: raise HTTPException(404,"Tracking token not found")
    exists=db.scalar(select(CampaignEvent.id).where(CampaignEvent.delivery_id==delivery.id,CampaignEvent.event_type==event_type))
    if not exists:
        db.add(CampaignEvent(id=str(uuid4()),delivery_id=delivery.id,event_type=event_type,occurred_at=datetime.now(timezone.utc))); db.commit()
