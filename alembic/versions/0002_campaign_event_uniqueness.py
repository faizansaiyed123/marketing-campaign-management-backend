from alembic import op
import sqlalchemy as sa
revision="0002_campaign_event_uniqueness"
down_revision="0001_initial"
branch_labels=None
depends_on=None
def upgrade():
    op.create_unique_constraint("uq_campaign_event_delivery_type","campaign_events",["delivery_id","event_type"])
def downgrade():
    op.drop_constraint("uq_campaign_event_delivery_type","campaign_events",type_="unique")
