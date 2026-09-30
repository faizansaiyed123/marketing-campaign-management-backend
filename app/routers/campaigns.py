from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..dependencies import get_current_user
from ..models import Audience, Campaign, CampaignEvent, CampaignRun, Delivery
from ..schemas import CampaignCreate, CampaignReport, CampaignResponse, CampaignUpdate, DeliverySummary
from ..services.campaigns import deliver_queued_run, queue_campaign

router=APIRouter(prefix="/api/v1/campaigns",tags=["campaigns"])

def get_campaign(db,campaign_id,user):
    campaign=db.scalar(select(Campaign).where(Campaign.id==campaign_id,Campaign.owner_id==user.id))
    if not campaign: raise HTTPException(404,"Campaign not found")
    return campaign

def response(c):
    return CampaignResponse.model_validate(c).model_copy(update={"audience_name":c.audience.name})

def build_report(db,c,run=None):
    latest=run or db.scalar(select(CampaignRun).where(CampaignRun.campaign_id==c.id).order_by(CampaignRun.started_at.desc()))
    deliveries=db.scalars(select(Delivery).join(CampaignRun).where(CampaignRun.campaign_id==c.id)).all()
    counts={"open":0,"click":0}
    if deliveries:
        rows=db.execute(
            select(CampaignEvent.event_type,func.count(func.distinct(CampaignEvent.delivery_id)))
            .where(
                CampaignEvent.delivery_id.in_([d.id for d in deliveries]),
                CampaignEvent.event_type.in_(("open","click")),
            )
            .group_by(CampaignEvent.event_type)
        ).all()
        counts.update(dict(rows))
    return CampaignReport(
        campaign=response(c),
        latest_run_status=latest.status if latest else None,
        summary=DeliverySummary(
            total=len(deliveries),
            queued=sum(d.status=="queued" for d in deliveries),
            sent=sum(d.status=="sent" for d in deliveries),
            failed=sum(d.status=="failed" for d in deliveries),
            opened=counts["open"],
            clicked=counts["click"],
        ),
    )

@router.get("",response_model=list[CampaignResponse])
def list_campaigns(db:Session=Depends(get_db),user=Depends(get_current_user)):
    return [response(c) for c in db.scalars(
        select(Campaign).where(Campaign.owner_id==user.id).order_by(Campaign.created_at.desc())
    ).all()]

@router.post("",response_model=CampaignResponse,status_code=201)
def create_campaign(payload:CampaignCreate,db:Session=Depends(get_db),user=Depends(get_current_user)):
    audience=db.scalar(select(Audience).where(Audience.id==payload.audience_id,Audience.owner_id==user.id))
    if not audience: raise HTTPException(404,"Audience not found")
    scheduled=payload.scheduled_at and payload.scheduled_at>datetime.now(timezone.utc)
    campaign=Campaign(
        id=str(uuid4()),
        owner_id=user.id,
        audience_id=audience.id,
        name=payload.name,
        subject=payload.subject,
        body_html=payload.body_html,
        status="scheduled" if scheduled else "draft",
        scheduled_at=payload.scheduled_at,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return response(campaign)

@router.patch("/{campaign_id}",response_model=CampaignResponse)
def update_campaign(campaign_id:str,payload:CampaignUpdate,db:Session=Depends(get_db),user=Depends(get_current_user)):
    campaign=get_campaign(db,campaign_id,user)
    if campaign.status in {"queued","sent"}:
        raise HTTPException(409,"Queued or sent campaigns cannot be edited")
    data=payload.model_dump(exclude_unset=True)
    if "audience_id" in data:
        audience=db.scalar(select(Audience.id).where(Audience.id==data["audience_id"],Audience.owner_id==user.id))
        if not audience: raise HTTPException(404,"Audience not found")
    for key,value in data.items():
        setattr(campaign,key,value)
    campaign.status="scheduled" if campaign.scheduled_at and campaign.scheduled_at>datetime.now(timezone.utc) else "draft"
    db.commit()
    db.refresh(campaign)
    return response(campaign)

@router.post("/{campaign_id}/execute",response_model=CampaignReport,status_code=202)
def execute(campaign_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    campaign=get_campaign(db,campaign_id,user)
    if campaign.status in {"sent","queued"}:
        raise HTTPException(409,"Campaign is already queued or sent")
    try:
        run=queue_campaign(db,campaign)
    except ValueError:
        raise HTTPException(409,"Campaign is already queued or sent")
    run=deliver_queued_run(db,run)
    return build_report(db,campaign,run)

@router.get("/{campaign_id}/report",response_model=CampaignReport)
def report(campaign_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    return build_report(db,get_campaign(db,campaign_id,user))
