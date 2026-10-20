from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from html import escape, unescape
import re
import smtplib
import ssl
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
TEMPLATE_FIELD_RE = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")

def queue_campaign(db: Session, campaign: Campaign) -> CampaignRun:
    retry_failed = campaign.status in {"failed", "partial"}
    claimed = db.execute(
        update(Campaign)
        .where(
            Campaign.id == campaign.id,
            Campaign.status.in_(("draft", "scheduled", "failed", "partial", "completed")),
        )
        .values(status="queued")
    ).rowcount

    if claimed != 1:
        db.rollback()
        raise ValueError("Campaign is already queued or sent")

    latest_run = db.scalars(
        select(CampaignRun)
        .where(CampaignRun.campaign_id == campaign.id)
        .order_by(CampaignRun.started_at.desc())
    ).first()

    if latest_run and retry_failed:
        contacts = db.scalars(
            select(Contact)
            .join(Delivery, Delivery.contact_id == Contact.id)
            .where(
                Delivery.run_id == latest_run.id,
                Delivery.status == "failed",
                Contact.unsubscribed_at.is_(None),
            )
            .order_by(Contact.created_at)
        ).unique().all()
    else:
        contacts = db.scalars(
            select(Contact)
            .where(
                Contact.audience_id == campaign.audience_id,
                Contact.unsubscribed_at.is_(None),
            )
            .order_by(Contact.created_at)
        ).all()

    run = CampaignRun(
        id=str(uuid4()),
        campaign_id=campaign.id,
        total_recipients=len(contacts),
    )
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

        if not contacts:
            run.status = "completed"
            run.finished_at = datetime.now(timezone.utc)
            campaign.status = "completed"

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(run)
    return run

def extract_http_links(body_html: str) -> list[str]:
    """Return distinct absolute HTTP(S) href targets in their document order."""
    return list(dict.fromkeys(
        unescape(match.group(3)) for match in LINK_RE.finditer(body_html)
    ))


def _rewrite_links(body_html: str, tracking_token: str) -> str:
    base = get_settings().public_base_url.rstrip("/")

    def replace(match: re.Match) -> str:
        target = unescape(match.group(3))
        if f"/track/{tracking_token}/" in target:
            return match.group(0)
        tracked = f"{base}/track/{tracking_token}/click?url={quote(target, safe='')}"
        return f"{match.group(1)}{match.group(2)}{escape(tracked, quote=True)}{match.group(4)}"

    return LINK_RE.sub(replace, body_html)

def build_tracked_html(campaign: Campaign, delivery: Delivery, body_html: str | None = None) -> str:
    base = get_settings().public_base_url.rstrip("/")
    tracked_body = _rewrite_links(body_html if body_html is not None else campaign.body_html, delivery.tracking_token)
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

def build_tracked_plain_text(body_html: str, delivery: Delivery) -> str:
    """Build a plain-text alternative with tracked destinations and unsubscribe."""
    plain_body = _plain_text(body_html) or "Campaign message"
    base = get_settings().public_base_url.rstrip("/")
    links = extract_http_links(body_html)
    if links:
        tracked_links = [
            f"{base}/track/{delivery.tracking_token}/click?url={quote(target, safe='')}"
            for target in links
        ]
        plain_body += "\n\nLinks:\n" + "\n".join(tracked_links)

    unsubscribe_url = f"{base}/track/{delivery.tracking_token}/unsubscribe"
    plain_body += f"\n\nUnsubscribe: {unsubscribe_url}"
    return plain_body

def render_personalized_content(subject: str, body_html: str, contact: Contact) -> tuple[str, str]:
    """Merge supported contact fields into a campaign subject and HTML body.

    HTML replacement values are escaped for safe interpolation into email markup.
    Unknown placeholders remain unchanged so unsupported fields are not silently
    replaced with incorrect data.
    """
    first_name = contact.first_name or ""
    last_name = contact.last_name or ""
    full_name = " ".join(part for part in (first_name, last_name) if part).strip()
    raw_values = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "email": contact.email,
    }

    def replace_subject(match: re.Match) -> str:
        key = match.group(1).lower()
        if key not in raw_values:
            return match.group(0)
        # RFC message headers must not contain caller-controlled newline bytes.
        return re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", raw_values[key]).strip()

    def replace_html(match: re.Match) -> str:
        key = match.group(1).lower()
        if key not in raw_values:
            return match.group(0)
        return escape(raw_values[key], quote=True)

    personalized_subject = TEMPLATE_FIELD_RE.sub(replace_subject, subject)
    personalized_subject = re.sub(r"[\r\n\x00-\x1f\x7f]+", " ", personalized_subject)
    personalized_subject = " ".join(personalized_subject.split()).strip()
    personalized_body = TEMPLATE_FIELD_RE.sub(replace_html, body_html)
    return personalized_subject, personalized_body


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

def smtp_is_configured(settings=None) -> bool:
    """Return whether the minimum SMTP settings needed to send mail are present."""
    settings = settings or get_settings()
    return bool(settings.smtp_host and settings.smtp_from_email)


def deliver_queued_run(db: Session, run: CampaignRun) -> CampaignRun:
    settings = get_settings()
    if not smtp_is_configured(settings):
        return run

    server = None
    db.rollback()

    try:
        if getattr(settings, "smtp_use_ssl", False):
            server = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=20,
                context=ssl.create_default_context(),
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
            if settings.smtp_use_tls:
                server.starttls(context=ssl.create_default_context())
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

                personalized_subject, personalized_body = render_personalized_content(
                    run.campaign.subject,
                    run.campaign.body_html,
                    delivery.contact,
                )
                message = EmailMessage(policy=policy.SMTP)
                message["Subject"] = personalized_subject or "Campaign message"
                message["From"] = settings.smtp_from_email
                message["To"] = delivery.contact.email
                message["List-Unsubscribe"] = (
                    f"<{settings.public_base_url.rstrip('/')}/track/"
                    f"{delivery.tracking_token}/unsubscribe>"
                )
                message["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
                message.set_content(build_tracked_plain_text(personalized_body, delivery))
                message.add_alternative(
                    build_tracked_html(run.campaign, delivery, body_html=personalized_body),
                    subtype="html",
                )

                try:
                    refused_recipients = server.send_message(message)
                    if refused_recipients:
                        refusal_details = "; ".join(
                            f"{recipient}: {details!r}"
                            for recipient, details in refused_recipients.items()
                        )
                        delivery.status = "failed"
                        delivery.error_message = ("SMTP refused recipient: " + refusal_details)[:500]
                    else:
                        delivery.status = "sent"
                        delivery.sent_at = datetime.now(timezone.utc)
                except Exception as exc:
                    delivery.status = "failed"
                    delivery.error_message = str(exc)[:500]

        with db.begin():
            _finalize_run(db, run.id)

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
