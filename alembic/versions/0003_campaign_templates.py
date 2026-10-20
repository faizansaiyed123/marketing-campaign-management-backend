"""Add reusable campaign templates."""

from alembic import op
import sqlalchemy as sa

revision = "0003_campaign_templates"
down_revision = "0002_campaign_event_uniqueness"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "campaign_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_campaign_templates_owner_id",
        "campaign_templates",
        ["owner_id"],
    )


def downgrade():
    op.drop_index("ix_campaign_templates_owner_id", table_name="campaign_templates")
    op.drop_table("campaign_templates")
