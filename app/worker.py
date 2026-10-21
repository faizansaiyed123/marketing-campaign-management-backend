import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .core.config import get_settings
from .db import SessionLocal
from .models import Campaign, CampaignRun
from .services.campaigns import deliver_queued_run, queue_campaign, smtp_is_configured

logger = logging.getLogger(__name__)


def process_due_campaigns() -> int:
    """Queue due campaigns and deliver queued runs when SMTP is configured."""
    processed = 0
    settings = get_settings()
    mail_enabled = smtp_is_configured(settings)

    with SessionLocal() as db:
        due = db.scalars(
            select(Campaign)
            .where(
                Campaign.status == "scheduled",
                Campaign.scheduled_at <= datetime.now(timezone.utc),
            )
            .order_by(Campaign.scheduled_at)
        ).all()

        for campaign in due:
            try:
                run = queue_campaign(db, campaign, require_due_schedule=True)
                processed += 1
            except ValueError:
                db.rollback()
                continue
            except Exception:
                db.rollback()
                logger.exception("Failed to queue scheduled campaign %s", campaign.id)
                continue

            if mail_enabled:
                try:
                    deliver_queued_run(db, run)
                except Exception:
                    db.rollback()
                    logger.exception("Failed to deliver scheduled campaign run %s", run.id)

        if mail_enabled:
            queued_runs = db.scalars(
                select(CampaignRun)
                .where(CampaignRun.status == "queued")
                .order_by(CampaignRun.started_at)
            ).all()

            for run in queued_runs:
                try:
                    deliver_queued_run(db, run)
                    processed += 1
                except Exception:
                    db.rollback()
                    logger.exception("Failed to process queued campaign run %s", run.id)

    return processed


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    while True:
        try:
            process_due_campaigns()
        except Exception:
            logger.exception("Scheduler iteration failed")
        time.sleep(15)


if __name__ == "__main__":
    main()
