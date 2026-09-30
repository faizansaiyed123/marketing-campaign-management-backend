from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CampaignEvent, Delivery

router = APIRouter(prefix="/track", tags=["tracking"])
PIXEL = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00"
    b"\x00\x00\x00\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,"
    b"\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;"
)

def _delivery(tracking_token: str, db: Session) -> Delivery:
    delivery = db.scalar(
        select(Delivery).where(Delivery.tracking_token == tracking_token)
    )
    if not delivery:
        raise HTTPException(404, "Tracking token not found")
    return delivery

def record(tracking_token: str, event_type: str, db: Session) -> Delivery:
    delivery = _delivery(tracking_token, db)
    if db.scalar(
        select(CampaignEvent.id).where(
            CampaignEvent.delivery_id == delivery.id,
            CampaignEvent.event_type == event_type,
        )
    ):
        return delivery

    try:
        with db.begin_nested():
            db.add(
                CampaignEvent(
                    id=str(uuid4()),
                    delivery_id=delivery.id,
                    event_type=event_type,
                    occurred_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
    except IntegrityError:
        db.rollback()
    return delivery

def _unsubscribe_contact(delivery: Delivery, db: Session) -> None:
    if delivery.contact.unsubscribed_at is None:
        delivery.contact.unsubscribed_at = datetime.now(timezone.utc)
        db.commit()

@router.get("/{tracking_token}/open")
def open_track(tracking_token: str, db: Session = Depends(get_db)):
    record(tracking_token, "open", db)
    return Response(
        content=PIXEL,
        media_type="image/gif",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

@router.get("/{tracking_token}/click")
def click_track(
    tracking_token: str,
    url: str = Query(..., min_length=1, max_length=8192),
    db: Session = Depends(get_db),
):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(400, "Only absolute HTTP(S) links can be tracked")
    record(tracking_token, "click", db)
    return RedirectResponse(url=url, status_code=307)

@router.get("/{tracking_token}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_confirmation(tracking_token: str, db: Session = Depends(get_db)):
    delivery = _delivery(tracking_token, db)
    action = f"/track/{tracking_token}/unsubscribe"
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='referrer' content='no-referrer'>"
        "<title>Unsubscribe</title></head>"
        "<body style='font-family:system-ui;padding:48px;max-width:620px;margin:auto'>"
        "<h1>Unsubscribe</h1>"
        "<p>Confirm that you no longer want to receive campaigns from this audience.</p>"
        f"<form method='post' action='{action}'>"
        "<button type='submit' style='padding:10px 16px'>Confirm unsubscribe</button>"
        "</form></body></html>",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

@router.post("/{tracking_token}/unsubscribe", response_class=HTMLResponse)
def unsubscribe_action(tracking_token: str, db: Session = Depends(get_db)):
    delivery = _delivery(tracking_token, db)
    _unsubscribe_contact(delivery, db)
    return HTMLResponse(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<meta name='referrer' content='no-referrer'>"
        "<title>Unsubscribed</title></head>"
        "<body style='font-family:system-ui;padding:48px;max-width:620px;margin:auto'>"
        "<h1>You have been unsubscribed</h1>"
        "<p>You will no longer receive campaigns from this audience.</p>"
        "<p>You can close this window.</p></body></html>",
        headers={"Cache-Control": "no-store, max-age=0"},
    )

@router.get("/{tracking_token}/{event_type}", status_code=204)
def get_event(tracking_token: str, event_type: str, db: Session = Depends(get_db)):
    if event_type not in {"open", "click"}:
        raise HTTPException(404, "Unknown tracking event")
    record(tracking_token, event_type, db)

@router.post("/{tracking_token}/{event_type}", status_code=204)
def post_event(tracking_token: str, event_type: str, db: Session = Depends(get_db)):
    if event_type not in {"open", "click"}:
        raise HTTPException(404, "Unknown tracking event")
    record(tracking_token, event_type, db)
