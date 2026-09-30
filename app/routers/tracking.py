from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import CampaignEvent, Delivery

router=APIRouter(prefix="/track",tags=["tracking"])
PIXEL=b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;"

def record(tracking_token:str,event_type:str,db:Session):
    d=db.scalar(select(Delivery).where(Delivery.tracking_token==tracking_token))
    if not d: raise HTTPException(404,"Tracking token not found")
    exists=db.scalar(select(CampaignEvent.id).where(CampaignEvent.delivery_id==d.id,CampaignEvent.event_type==event_type))
    if not exists:
        db.add(CampaignEvent(id=str(uuid4()),delivery_id=d.id,event_type=event_type,occurred_at=datetime.now(timezone.utc)))
        db.commit()

@router.get("/{tracking_token}/open")
def open_track(tracking_token:str,db:Session=Depends(get_db)):
    record(tracking_token,"open",db); return Response(content=PIXEL,media_type="image/gif",headers={"Cache-Control":"no-store, max-age=0"})

@router.get("/{tracking_token}/{event_type}",status_code=204)
def get_event(tracking_token:str,event_type:str,db:Session=Depends(get_db)):
    if event_type not in {"open","click"}: raise HTTPException(404,"Unknown tracking event")
    record(tracking_token,event_type,db)

@router.post("/{tracking_token}/{event_type}",status_code=204)
def post_event(tracking_token:str,event_type:str,db:Session=Depends(get_db)):
    if event_type not in {"open","click"}: raise HTTPException(404,"Unknown tracking event")
    record(tracking_token,event_type,db)
