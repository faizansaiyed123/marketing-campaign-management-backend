"""Track skipped deliveries in campaign runs."""

from alembic import op
import sqlalchemy as sa

revision = "0004_delivery_skipped_count"
down_revision = "0003_campaign_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "campaign_runs",
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade():
    op.drop_column("campaign_runs", "skipped_count")
