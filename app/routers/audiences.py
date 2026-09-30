from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from ..db import get_db
from ..dependencies import get_current_user
from ..models import Audience, Contact, Delivery
from ..schemas import AudienceCreate, AudienceResponse, ContactCreate, ContactResponse
router=APIRouter(prefix="/api/v1/audiences",tags=["audience"])

@router.get("",response_model=list[AudienceResponse])
def list_audiences(db:Session=Depends(get_db),user=Depends(get_current_user)):
    rows=db.execute(select(Audience,func.count(Contact.id)).outerjoin(Contact,Contact.audience_id==Audience.id).where(Audience.owner_id==user.id).group_by(Audience.id).order_by(Audience.created_at.desc())).all()
    return [AudienceResponse.model_validate(a).model_copy(update={"contact_count":n}) for a,n in rows]

@router.post("",response_model=AudienceResponse,status_code=201)
def create_audience(payload:AudienceCreate,db:Session=Depends(get_db),user=Depends(get_current_user)):
    a=Audience(id=str(uuid4()),owner_id=user.id,name=payload.name.strip()); db.add(a); db.commit(); db.refresh(a); return a

@router.get("/{audience_id}/contacts",response_model=list[ContactResponse])
def list_contacts(audience_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    if not db.scalar(select(Audience.id).where(Audience.id==audience_id,Audience.owner_id==user.id)): raise HTTPException(404,"Audience not found")
    return db.scalars(select(Contact).where(Contact.audience_id==audience_id).order_by(Contact.created_at.desc())).all()

@router.post("/{audience_id}/contacts",response_model=ContactResponse,status_code=201)
def create_contact(audience_id:str,payload:ContactCreate,db:Session=Depends(get_db),user=Depends(get_current_user)):
    if not db.scalar(select(Audience.id).where(Audience.id==audience_id,Audience.owner_id==user.id)): raise HTTPException(404,"Audience not found")
    email=payload.email.lower()
    if db.scalar(select(Contact.id).where(Contact.audience_id==audience_id,Contact.email==email)): raise HTTPException(409,"Contact already exists in this audience")
    c=Contact(id=str(uuid4()),audience_id=audience_id,email=email,first_name=payload.first_name,last_name=payload.last_name)
    db.add(c); db.commit(); db.refresh(c); return c

@router.post("/{audience_id}/contacts/{contact_id}/unsubscribe",response_model=ContactResponse)
def unsubscribe(audience_id:str,contact_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    c=db.scalar(select(Contact).join(Audience).where(Contact.id==contact_id,Contact.audience_id==audience_id,Audience.owner_id==user.id))
    if not c: raise HTTPException(404,"Contact not found")
    c.unsubscribed_at=datetime.now(timezone.utc); db.commit(); db.refresh(c); return c

@router.post("/{audience_id}/contacts/{contact_id}/subscribe",response_model=ContactResponse)
def subscribe(audience_id:str,contact_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    c=db.scalar(select(Contact).join(Audience).where(Contact.id==contact_id,Contact.audience_id==audience_id,Audience.owner_id==user.id))
    if not c: raise HTTPException(404,"Contact not found")
    c.unsubscribed_at=None; db.commit(); db.refresh(c); return c

@router.delete("/{audience_id}/contacts/{contact_id}",status_code=204)
def delete_contact(audience_id:str,contact_id:str,db:Session=Depends(get_db),user=Depends(get_current_user)):
    c=db.scalar(select(Contact).join(Audience).where(Contact.id==contact_id,Contact.audience_id==audience_id,Audience.owner_id==user.id))
    if not c: raise HTTPException(404,"Contact not found")
    if db.scalar(select(Delivery.id).where(Delivery.contact_id==contact_id)): raise HTTPException(409,"Contact has campaign history and cannot be deleted")
    db.delete(c); db.commit()
