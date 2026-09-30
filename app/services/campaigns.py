from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from html import escape, unescape
import re
import smtplib
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..core.config import get_settings
from ..models import Campaign, CampaignRun, Contact, Delivery

LINK_RE = re.compile(
    r'(<a\b[^>]*?\bhref\s*=\s*)(["\'])(https?://[^"\']+)(\2)',
    re.IGNORECASE,
)

def queue_campaign(db: Session, campaign: Campaign) -> CampaignRun:
    was_retry = campaign.status in {"failed", "partial"}

    claimed = db.execute(
        update(Campaign)
        .where(
            Campaign.id == campaign.id,
            Campaign.status.in_(("draft", "scheduled", "failed", "partial")),
        )
        .values(status="queued")
    ).rowcount

    if claimed != 1:
        db.rollback()
        raise ValueError("Campaign is already queued or sent")

    sent_contact_ids = select(Delivery.contact_id).join(CampaignRun).where(
        CampaignRun.campaign_id == campaign.id,
        Delivery.status == "sent",
    )
    contacts_query = select(Contact).where(
        Contact.audience_id == campaign.audience_id,
        Contact.unsubscribed_at.is_(None),
    )
    if was_retry:
        contacts_query = contacts_query.where(~Contact.id.in_(sent_contact_ids))
    contacts = db.scalars(contacts_query.order_by(Contact.created_at)).all()

    run = CampaignRun(
        id=str(uuid4()),
        campaign_id=campaign.id,
        total_recipients=len(contacts),
    )
    if not contacts:
        run.status = "completed"
        run.finished_at = datetime.now(timezone.utc)
        campaign.status = "completed"
    db.add(run)

    try:
        for contact in contacts:
            db.add(
                Delivery(
                    id=str(uuid4()),
                    run_id=run.id,
                    contact_id=contact.id,
                    tracking_token=uuid4().hex,
                    status="queued",
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(run)
    return run

def _rewrite_links(body_html: str, tracking_token: str) -> str:
    base = get_settings().public_base_url.rstrip("/")

    def replace(match: re.Match) -> str:
        target = unescape(match.group(3))
        if f"/track/{tracking_token}/" in target:
            return match.group(0)
        tracked = f"{base}/track/{tracking_token}/click?url={quote(target, safe='')}"
        return f"{match.group(1)}{match.group(2)}{escape(tracked, quote=True)}{match.group(4)}"

    return LINK_RE.sub(replace, body_html)

def build_tracked_html(campaign: Campaign, delivery: Delivery) -> str:
    base = get_settings().public_base_url.rstrip("/")
    tracked_body = _rewrite_links(campaign.body_html, delivery.tracking_token)
    unsubscribe_url = f"{base}/track/{delivery.tracking_token}/unsubscribe"
    pixel_url = f"{base}/track/{delivery.tracking_token}/open"
    unsubscribe = (
        '<p style="margin-top:24px;font-size:12px;color:#666">'
        f'<a href="{escape(unsubscribe_url, quote=True)}">Unsubscribe</a>'
        '</p>'
    )
    pixel = (
        f'<img src="{escape(pixel_url, quote=True)}" width="1" height="1" '
        'alt="" style="display:none" />'
    )
    return tracked_body + unsubscribe + pixel

def _plain_text(html_body: str) -> str:
    return unescape(re.sub(r"<[^>]+>", " ", html_body)).strip()

def _finalize_run(db: Session, run_id: str) -> CampaignRun | None:
    run = db.get(CampaignRun, run_id)
    if not run:
        return None

    queued = db.scalar(
        select(func.count(Delivery.id)).where(
            Delivery.run_id == run.id,
            Delivery.status == "queued",
        )
    ) or 0
    if queued:
        return run

    sent = db.scalar(
        select(func.count(Delivery.id)).where(
            Delivery.run_id == run.id,
            Delivery.status == "sent",
        )
    ) or 0
    failed = db.scalar(
        select(func.count(Delivery.id)).where(
            Delivery.run_id == run.id,
            Delivery.status == "failed",
        )
    ) or 0

    run.sent_count = sent
    run.failed_count = failed
    if run.total_recipients == 0:
        run.status = "completed"
    else:
        run.status = "sent" if failed == 0 else ("failed" if sent == 0 else "partial")
    run.finished_at = datetime.now(timezone.utc)
    run.campaign.status = run.status
    return run

def _mark_all_queued_failed(db: Session, run_id: str, reason: str) -> None:
    deliveries = db.scalars(
        select(Delivery).where(
            Delivery.run_id == run_id,
            Delivery.status == "queued",
        )
    ).all()
    for delivery in deliveries:
        delivery.status = "failed"
        delivery.error_message = reason[:500]

def deliver_queued_run(db: Session, run: CampaignRun) -> CampaignRun:
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        return run

    server = None
    db.rollback()

    try:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")

        while True:
            with db.begin():
                delivery = db.scalars(
                    select(Delivery)
                    .where(
                        Delivery.run_id == run.id,
                        Delivery.status == "queued",
                    )
                    .with_for_update(skip_locked=True)
                    .limit(1)
                ).first()

                if delivery is None:
                    break

                message = EmailMessage(policy=policy.SMTP)
                message["Subject"] = run.campaign.subject
                message["Message-ID"] = f"<delivery-{delivery.id}@campaign.local>"
                message["From"] = settings.smtp_from_email
                message["To"] = delivery.contact.email
                unsubscribe_url = (
                    f"{settings.public_base_url.rstrip('/')}/track/"
                    f"{delivery.tracking_token}/unsubscribe"
                )
                message["List-Unsubscribe"] = f"<{unsubscribe_url}>"
                message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
                plain_text = _plain_text(run.campaign.body_html) or "Campaign message"
                message.set_content(
                    plain_text + f"\n\nUnsubscribe: {unsubscribe_url}"
                )
                message.add_alternative(
                    build_tracked_html(run.campaign, delivery),
                    subtype="html",
                )

                try:
                    server.send_message(message)
                    delivery.status = "sent"
                    delivery.sent_at = datetime.now(timezone.utc)
                except Exception as exc:
                    delivery.status = "failed"
                    delivery.error_message = str(exc)[:500]

            _finalize_run(db, run.id)
            db.commit()

        _finalize_run(db, run.id)
        db.commit()

    except Exception as exc:
        db.rollback()
        with db.begin():
            _mark_all_queued_failed(db, run.id, str(exc))
            _finalize_run(db, run.id)
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass

    db.refresh(run)
    return run
