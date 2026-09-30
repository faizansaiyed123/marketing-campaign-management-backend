from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def now_utc(): return datetime.now(timezone.utc)

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    email: Mapped[str]=mapped_column(String(320),unique=True,index=True)
    name: Mapped[str]=mapped_column(String(120))
    password_hash: Mapped[str]=mapped_column(String(512))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    audiences: Mapped[list["Audience"]]=relationship(back_populates="owner",cascade="all, delete-orphan")
    campaigns: Mapped[list["Campaign"]]=relationship(back_populates="owner",cascade="all, delete-orphan")

class Audience(Base):
    __tablename__="audiences"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    owner_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    name: Mapped[str]=mapped_column(String(120))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    owner: Mapped[User]=relationship(back_populates="audiences")
    contacts: Mapped[list["Contact"]]=relationship(back_populates="audience",cascade="all, delete-orphan")
    campaigns: Mapped[list["Campaign"]]=relationship(back_populates="audience")

class Contact(Base):
    __tablename__="contacts"
    __table_args__=(UniqueConstraint("audience_id","email",name="uq_contact_audience_email"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    audience_id: Mapped[str]=mapped_column(ForeignKey("audiences.id",ondelete="CASCADE"),index=True)
    email: Mapped[str]=mapped_column(String(320))
    first_name: Mapped[str|None]=mapped_column(String(80),nullable=True)
    last_name: Mapped[str|None]=mapped_column(String(80),nullable=True)
    unsubscribed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    audience: Mapped[Audience]=relationship(back_populates="contacts")
    deliveries: Mapped[list["Delivery"]]=relationship(back_populates="contact")
Index("ix_contacts_email",Contact.email)

class Campaign(Base):
    __tablename__="campaigns"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    owner_id: Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    audience_id: Mapped[str]=mapped_column(ForeignKey("audiences.id",ondelete="RESTRICT"),index=True)
    name: Mapped[str]=mapped_column(String(140))
    subject: Mapped[str]=mapped_column(String(200))
    body_html: Mapped[str]=mapped_column(Text)
    status: Mapped[str]=mapped_column(String(24),default="draft",index=True)
    scheduled_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc,onupdate=now_utc)
    owner: Mapped[User]=relationship(back_populates="campaigns")
    audience: Mapped[Audience]=relationship(back_populates="campaigns")
    runs: Mapped[list["CampaignRun"]]=relationship(back_populates="campaign",cascade="all, delete-orphan")

class CampaignRun(Base):
    __tablename__="campaign_runs"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    campaign_id: Mapped[str]=mapped_column(ForeignKey("campaigns.id",ondelete="CASCADE"),index=True)
    status: Mapped[str]=mapped_column(String(24),default="queued",index=True)
    total_recipients: Mapped[int]=mapped_column(Integer,default=0)
    sent_count: Mapped[int]=mapped_column(Integer,default=0)
    failed_count: Mapped[int]=mapped_column(Integer,default=0)
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    finished_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    campaign: Mapped[Campaign]=relationship(back_populates="runs")
    deliveries: Mapped[list["Delivery"]]=relationship(back_populates="run",cascade="all, delete-orphan")

class Delivery(Base):
    __tablename__="deliveries"
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    run_id: Mapped[str]=mapped_column(ForeignKey("campaign_runs.id",ondelete="CASCADE"),index=True)
    contact_id: Mapped[str]=mapped_column(ForeignKey("contacts.id",ondelete="RESTRICT"),index=True)
    tracking_token: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    status: Mapped[str]=mapped_column(String(24),default="queued",index=True)
    provider_message_id: Mapped[str|None]=mapped_column(String(255),nullable=True)
    error_message: Mapped[str|None]=mapped_column(String(500),nullable=True)
    sent_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    run: Mapped[CampaignRun]=relationship(back_populates="deliveries")
    contact: Mapped[Contact]=relationship(back_populates="deliveries")
    events: Mapped[list["CampaignEvent"]]=relationship(back_populates="delivery",cascade="all, delete-orphan")

class CampaignEvent(Base):
    __tablename__="campaign_events"
    __table_args__=(Index("ix_events_delivery_type","delivery_id","event_type"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True)
    delivery_id: Mapped[str]=mapped_column(ForeignKey("deliveries.id",ondelete="CASCADE"),index=True)
    event_type: Mapped[str]=mapped_column(String(24),index=True)
    occurred_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now_utc)
    delivery: Mapped[Delivery]=relationship(back_populates="events")
