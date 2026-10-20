from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..dependencies import get_current_user
from ..models import Audience, Campaign, CampaignEvent, CampaignRun, Delivery
from ..schemas import CampaignCreate, CampaignReport, CampaignResponse, CampaignUpdate, DeliverySummary
from ..services.campaigns import queue_campaign

router=APIRouter(prefix="/api/v1/campaigns",tags=["campaigns"])

def get_campaign(db,campaign_id,user,*,for_update=False):
    statement=select(Campaign).where(Campaign.id==campaign_id,Campaign.owner_id==user.id)
    if for_update:
        statement=statement.with_for_update()
    campaign=db.scalar(statement)
    if not campaign: raise HTTPException(404,"Campaign not found")
    return campaign

def response(c):
    return CampaignResponse.model_validate(c).model_copy(update={"audience_name":c.audience.name})

def build_report(db,c,run=None):
    latest=run or db.scalar(
        select(CampaignRun)
        .where(CampaignRun.campaign_id==c.id)
        .order_by(CampaignRun.started_at.desc())
    )

    # Aggregate in PostgreSQL instead of loading every delivery into Python.
    # This keeps campaign-wide reporting efficient for large audiences.
    state_rows=db.execute(
        select(Delivery.status,func.count(Delivery.id))
        .join(CampaignRun,Delivery.run_id==CampaignRun.id)
        .where(CampaignRun.campaign_id==c.id)
        .group_by(Delivery.status)
    ).all()
    state_counts=dict(state_rows)

    event_rows=db.execute(
        select(CampaignEvent.event_type,func.count(func.distinct(CampaignEvent.delivery_id)))
        .join(Delivery,CampaignEvent.delivery_id==Delivery.id)
        .join(CampaignRun,Delivery.run_id==CampaignRun.id)
        .where(
            CampaignRun.campaign_id==c.id,
            CampaignEvent.event_type.in_(("open","click")),
        )
        .group_by(CampaignEvent.event_type)
    ).all()
    event_counts=dict(event_rows)

    return CampaignReport(
        campaign=response(c),
        latest_run_status=latest.status if latest else None,
        summary=DeliverySummary(
            total=sum(state_counts.values()),
            queued=state_counts.get("queued",0),
            sent=state_counts.get("sent",0),
            failed=state_counts.get("failed",0),
            skipped=state_counts.get("skipped",0),
            opened=event_counts.get("open",0),
            clicked=event_counts.get("click",0),
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
    # Serialize edits against execute/worker state transitions in PostgreSQL.
    campaign=get_campaign(db,campaign_id,user,for_update=True)
    if campaign.status in {"queued","sent"}:
        raise HTTPException(409,"Queued or sent campaigns cannot be edited")
    previous_status = campaign.status
    previous_audience_id = campaign.audience_id
    data=payload.model_dump(exclude_unset=True)
    if "audience_id" in data:
        audience=db.scalar(select(Audience.id).where(Audience.id==data["audience_id"],Audience.owner_id==user.id))
        if not audience: raise HTTPException(404,"Audience not found")
    for key,value in data.items():
        setattr(campaign,key,value)
    if campaign.scheduled_at and campaign.scheduled_at>datetime.now(timezone.utc):
        campaign.status="scheduled"
    elif previous_status in {"failed", "partial"} and campaign.audience_id == previous_audience_id:
        # Preserve retry semantics only while the audience remains the same.
        # Changing the audience starts a new draft instead of retrying old contacts.
        campaign.status=previous_status
    else:
        campaign.status="draft"
    db.commit()
    db.refresh(campaign)
    return response(campaign)

@router.post("/{campaign_id}/execute",response_model=CampaignReport,status_code=202)
def execute(campaign_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    # Serialize execute against edits so a single committed campaign version
    # determines both its recipient audience and the content sent by the worker.
    campaign=get_campaign(db,campaign_id,user,for_update=True)
    if campaign.status in {"sent","queued"}:
        raise HTTPException(409,"Campaign is already queued or sent")
    try:
        run=queue_campaign(db,campaign)
    except ValueError:
        raise HTTPException(409,"Campaign is already queued or sent")
    # The API persists durable work; the worker owns SMTP delivery.
    return build_report(db,campaign,run)

@router.get("/{campaign_id}/report",response_model=CampaignReport)
def report(campaign_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    return build_report(db,get_campaign(db,campaign_id,user))
