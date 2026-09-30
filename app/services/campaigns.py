from datetime import datetime, timezone
from email.message import EmailMessage
import smtplib
from uuid import uuid4
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..core.config import get_settings
from ..models import Campaign, CampaignRun, Contact, Delivery

def queue_campaign(db:Session,campaign:Campaign)->CampaignRun:
    contacts=db.scalars(select(Contact).where(Contact.audience_id==campaign.audience_id,Contact.unsubscribed_at.is_(None)).order_by(Contact.created_at)).all()
    run=CampaignRun(id=str(uuid4()),campaign_id=campaign.id,total_recipients=len(contacts))
    db.add(run); db.flush()
    for contact in contacts:
        db.add(Delivery(id=str(uuid4()),run_id=run.id,contact_id=contact.id,tracking_token=uuid4().hex,status="queued"))
    campaign.status="queued"; db.commit(); db.refresh(run); return run

def build_tracked_html(campaign:Campaign, delivery:Delivery)->str:
    s=get_settings()
    pixel=f'<img src="{s.public_base_url.rstrip("/")}/track/{delivery.tracking_token}/open" width="1" height="1" alt="" style="display:none" />'
    return campaign.body_html + pixel

def deliver_queued_run(db:Session,run:CampaignRun)->CampaignRun:
    s=get_settings()
    if not s.smtp_host or not s.smtp_from_email: return run
    campaign=run.campaign
    server=smtplib.SMTP(s.smtp_host,s.smtp_port,timeout=20)
    try:
        if s.smtp_use_tls: server.starttls()
        if s.smtp_username: server.login(s.smtp_username,s.smtp_password or "")
        for delivery in run.deliveries:
            if delivery.status!="queued": continue
            message=EmailMessage()
            message["Subject"]=campaign.subject; message["From"]=s.smtp_from_email; message["To"]=delivery.contact.email
            message.set_content(campaign.body_html)
            message.add_alternative(build_tracked_html(campaign,delivery),subtype="html")
            try:
                server.send_message(message); delivery.status="sent"; delivery.sent_at=datetime.now(timezone.utc); run.sent_count+=1
            except Exception as exc:
                delivery.status="failed"; delivery.error_message=str(exc)[:500]; run.failed_count+=1
    finally: server.quit()
    run.status="sent" if run.failed_count==0 else ("failed" if run.sent_count==0 else "partial")
    run.finished_at=datetime.now(timezone.utc)
    if run.status=="sent": campaign.status="sent"
    db.commit(); db.refresh(run); return run
