import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from .db import SessionLocal
from .models import Campaign, CampaignRun
from .services.campaigns import deliver_queued_run, queue_campaign

logger = logging.getLogger(__name__)

def process_due_campaigns() -> int:
    processed = 0
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
                run = queue_campaign(db, campaign)
            except ValueError:
                db.rollback()
                continue
            deliver_queued_run(db, run)
            processed += 1

        queued_runs = db.scalars(
            select(CampaignRun)
            .where(CampaignRun.status == "queued")
            .order_by(CampaignRun.started_at)
        ).all()
        for run in queued_runs:
            deliver_queued_run(db, run)
            processed += 1

    return processed

def main():
    while True:
        try:
            process_due_campaigns()
        except Exception:
            logger.exception("Campaign scheduler iteration failed")
        time.sleep(15)

if __name__ == "__main__":
    main()
