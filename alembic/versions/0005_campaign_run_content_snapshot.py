"""Snapshot campaign content for each execution run."""

from alembic import op
import sqlalchemy as sa

revision = "0005_run_content_snapshot"
down_revision = "0004_delivery_skipped_count"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "campaign_runs",
        sa.Column("subject_snapshot", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "campaign_runs",
        sa.Column("body_html_snapshot", sa.Text(), nullable=True),
    )
    # Existing runs cannot be reconstructed after edits with certainty. Backfill
    # current campaign content as the best safe compatibility fallback; all new
    # runs store their content at queue time.
    op.execute(
        sa.text(
            "UPDATE campaign_runs "
            "SET subject_snapshot = campaigns.subject, "
            "body_html_snapshot = campaigns.body_html "
            "FROM campaigns WHERE campaigns.id = campaign_runs.campaign_id"
        )
    )


def downgrade():
    op.drop_column("campaign_runs", "body_html_snapshot")
    op.drop_column("campaign_runs", "subject_snapshot")
