from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..dependencies import get_current_user
from ..models import CampaignTemplate
from ..schemas import (
    CampaignTemplateCreate,
    CampaignTemplateResponse,
    CampaignTemplateUpdate,
)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


def get_template(db: Session, template_id: str, user_id: str) -> CampaignTemplate:
    template = db.scalar(
        select(CampaignTemplate).where(
            CampaignTemplate.id == template_id,
            CampaignTemplate.owner_id == user_id,
        )
    )
    if template is None:
        raise HTTPException(404, "Template not found")
    return template


@router.get("", response_model=list[CampaignTemplateResponse])
def list_templates(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.scalars(
        select(CampaignTemplate)
        .where(CampaignTemplate.owner_id == user.id)
        .order_by(CampaignTemplate.updated_at.desc(), CampaignTemplate.created_at.desc())
    ).all()


@router.post("", response_model=CampaignTemplateResponse, status_code=201)
def create_template(
    payload: CampaignTemplateCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    template = CampaignTemplate(
        id=str(uuid4()),
        owner_id=user.id,
        name=payload.name,
        subject=payload.subject,
        body_html=payload.body_html,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


@router.patch("/{template_id}", response_model=CampaignTemplateResponse)
def update_template(
    template_id: str,
    payload: CampaignTemplateUpdate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    template = get_template(db, template_id, user.id)
    data = payload.model_dump(exclude_unset=True)
    if any(value is None for value in data.values()):
        raise HTTPException(422, "Template fields cannot be null")
    for key, value in data.items():
        setattr(template, key, value)
    db.commit()
    db.refresh(template)
    return template


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    template = get_template(db, template_id, user.id)
    db.delete(template)
    db.commit()
    return Response(status_code=204)
