import time
from datetime import datetime, timezone
from sqlalchemy import select
from .db import SessionLocal
from .models import Campaign
from .services.campaigns import deliver_queued_run, queue_campaign

def process_due_campaigns() -> int:
    processed = 0
    with SessionLocal() as db:
        due = db.scalars(select(Campaign).where(
            Campaign.status == "scheduled",
            Campaign.scheduled_at <= datetime.now(timezone.utc)
        ).order_by(Campaign.scheduled_at)).all()
        for campaign in due:
            run = queue_campaign(db, campaign)
            deliver_queued_run(db, run)
            processed += 1
    return processed

def main():
    while True:
        process_due_campaigns()
        time.sleep(15)

if __name__ == "__main__":
    main()
