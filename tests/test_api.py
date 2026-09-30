def register(client,email,name="User"):
    r=client.post("/api/v1/auth/register",json={"email":email,"name":name,"password":"strong-password-123"}); assert r.status_code==201,r.text

def test_health(client):
    assert client.get("/health").json()=={"status":"ok"}

def test_auth_flow(client):
    register(client,"auth@example.com")
    assert client.get("/api/v1/auth/me").status_code==200
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code==401
    assert client.post("/api/v1/auth/login",json={"email":"auth@example.com","password":"strong-password-123"}).status_code==200

def test_campaign_flow_tracking_click_and_unsubscribe(client):
    register(client,"campaign@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Launch List"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"person@example.com"})
    c=client.post("/api/v1/campaigns",json={
        "name":"Launch",
        "audience_id":a["id"],
        "subject":"Hello",
        "body_html":'<a href="https://example.com/path?q=1">Hello</a>',
    }).json()
    r=client.post(f"/api/v1/campaigns/{c['id']}/execute")
    assert r.status_code==202 and r.json()["summary"]["queued"]==1

    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import Contact, Delivery
    with Session(engine) as db:
        delivery=db.scalar(select(Delivery))
        token=delivery.tracking_token

    assert client.get(f"/track/{token}/open").status_code==200
    assert client.get(f"/track/{token}/click",params={"url":"https://example.com/path"},follow_redirects=False).status_code==307
    from app.services.campaigns import build_tracked_html
    with Session(engine) as db:
        delivery=db.scalar(select(Delivery))
        campaign_row=db.get(__import__("app.models",fromlist=["Campaign"]).Campaign,c["id"])
        tracked_html=build_tracked_html(campaign_row,delivery)
    assert "/track/"+token+"/click?url=https%3A%2F%2Fexample.com%2Fpath%3Fq%3D1" in tracked_html
    assert "/track/"+token+"/unsubscribe" in tracked_html
    assert "/track/"+token+"/open" in tracked_html
    assert client.get(f"/track/{token}/click",params={"url":"javascript:alert(1)"},follow_redirects=False).status_code==400
    assert client.post(f"/track/{token}/click").status_code==204
    assert client.post(f"/track/{token}/unsubscribe",content="List-Unsubscribe=One-Click",headers={"Content-Type":"application/x-www-form-urlencoded"}).status_code==200
    assert client.get(f"/track/{token}/unsubscribe").status_code==200
    with Session(engine) as db:
        contact=db.scalar(select(Contact).where(Contact.email=="person@example.com"))
        assert contact.unsubscribed_at is not None
    assert client.post(f"/track/{token}/unsubscribe").status_code==200
    assert client.get(f"/track/{token}/open").status_code==200

    report=client.get(f"/api/v1/campaigns/{c['id']}/report").json()
    assert report["summary"]["opened"]==1 and report["summary"]["clicked"]==1
    with Session(engine) as db:
        contact=db.scalar(select(Contact).where(Contact.email=="person@example.com"))
        assert contact.unsubscribed_at is not None

def test_unsubscribe_is_excluded(client):
    register(client,"unsubscribe@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Prefs"}).json()
    skip=client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"skip@example.com"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts/{skip['id']}/unsubscribe")
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"keep@example.com"})
    camp=client.post("/api/v1/campaigns",json={"name":"Prefs","audience_id":a["id"],"subject":"x","body_html":"x"}).json()
    assert client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()["summary"]["total"]==1

def test_empty_audience_run_completes(client):
    register(client,"empty@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Empty"}).json()
    camp=client.post("/api/v1/campaigns",json={"name":"Empty","audience_id":a["id"],"subject":"x","body_html":"x"}).json()
    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["summary"]["total"]==0 and report["latest_run_status"]=="completed"


def test_naive_schedule_is_normalized(client):
    register(client,"schedule@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Schedule"}).json()
    camp=client.post("/api/v1/campaigns",json={
        "name":"Scheduled","audience_id":a["id"],"subject":"x","body_html":"x",
        "scheduled_at":"2030-01-01T12:00:00",
    }).json()
    assert camp["status"]=="scheduled"
    assert camp["scheduled_at"].endswith("+00:00")

def test_invalid_password_hash_is_rejected(client):
    register(client,"corrupt@example.com")
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import User
    with Session(engine) as db:
        user=db.query(User).filter(User.email=="corrupt@example.com").one()
        user.password_hash="not-a-valid-argon2-hash"
        db.commit()
    assert client.post("/api/v1/auth/login",json={"email":"corrupt@example.com","password":"strong-password-123"}).status_code==401

def test_production_security_defaults_are_rejected():
    from pydantic import ValidationError
    from app.core.config import Settings
    try:
        Settings(environment="production",jwt_secret_key="change-me-in-development",cookie_secure=False)
        assert False, "unsafe production defaults were accepted"
    except ValidationError:
        pass

def test_blank_names_are_rejected(client):
    register(client,"blank@example.com")
    assert client.post("/api/v1/audiences",json={"name":"   "}).status_code==422

def test_smtp_success_sends_and_tracks(client,monkeypatch):
    register(client,"smtp-success@example.com")
    a=client.post("/api/v1/audiences",json={"name":"SMTP Success"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"smtp-target@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"SMTP Success",
        "audience_id":a["id"],
        "subject":"Tracked",
        "body_html":'<a href="https://example.com/welcome">Welcome</a>',
    }).json()

    from types import SimpleNamespace
    import app.services.campaigns as service

    sent=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs): pass
        def starttls(self): pass
        def login(self,*args,**kwargs): pass
        def send_message(self,message): sent.append(message)
        def quit(self): pass

    monkeypatch.setattr(service,"smtplib",SimpleNamespace(SMTP=FakeSMTP))
    monkeypatch.setattr(service,"get_settings",lambda:SimpleNamespace(
        smtp_host="smtp.example",smtp_port=587,smtp_username="user",smtp_password="pass",
        smtp_from_email="sender@example.com",smtp_use_tls=True,public_base_url="http://localhost:8000",
    ))

    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["latest_run_status"]=="sent"
    assert report["summary"]["sent"]==1
    assert report["campaign"]["status"]=="sent"
    assert len(sent)==1
    html=sent[0].get_body(preferencelist=("html",)).get_content()
    assert "/click?url=https%3A%2F%2Fexample.com%2Fwelcome" in html
    assert "/unsubscribe" in html

def test_smtp_sends_multiple_recipients(client,monkeypatch):
    register(client,"smtp-success@example.com")
    a=client.post("/api/v1/audiences",json={"name":"SMTP Success"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"first@example.com"})
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"second@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"SMTP Success","audience_id":a["id"],"subject":"x",
        "body_html":'<a href="https://example.com">x</a>',
    }).json()

    from types import SimpleNamespace
    import app.services.campaigns as service
    sent=[]
    class FakeSMTP:
        def __init__(self,*args,**kwargs): pass
        def starttls(self): pass
        def login(self,*args,**kwargs): pass
        def send_message(self,message): sent.append(message)
        def quit(self): pass
    monkeypatch.setattr(service,"smtplib",SimpleNamespace(SMTP=FakeSMTP))
    monkeypatch.setattr(service,"get_settings",lambda:SimpleNamespace(
        smtp_host="smtp.example",smtp_port=587,smtp_username=None,smtp_password=None,
        smtp_from_email="sender@example.com",smtp_use_tls=True,public_base_url="http://localhost:8000",
    ))

    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["summary"]["sent"]==2
    assert report["latest_run_status"]=="sent"
    assert len(sent)==2
    assert all("List-Unsubscribe" in msg and "List-Unsubscribe-Post" in msg for msg in sent)
    assert all("/track/" in msg.as_string() for msg in sent)

def test_smtp_failure_marks_run_failed(client,monkeypatch):
    register(client,"smtp@example.com")
    a=client.post("/api/v1/audiences",json={"name":"SMTP"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"smtp-target@example.com"})
    camp=client.post("/api/v1/campaigns",json={"name":"SMTP","audience_id":a["id"],"subject":"x","body_html":"x"}).json()

    from types import SimpleNamespace
    import app.services.campaigns as service
    class BrokenSMTP:
        def __init__(self,*args,**kwargs):
            raise OSError("smtp unavailable")
    monkeypatch.setattr(service,"smtplib",SimpleNamespace(SMTP=BrokenSMTP))
    monkeypatch.setattr(service,"get_settings",lambda:SimpleNamespace(
        smtp_host="smtp.example",smtp_port=587,smtp_username=None,smtp_password=None,
        smtp_from_email="sender@example.com",smtp_use_tls=True,public_base_url="http://localhost:8000",
    ))

    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["summary"]["failed"]==1 and report["latest_run_status"]=="failed"

def test_retry_partial_campaign_does_not_resend_successful_contacts(client,monkeypatch):
    register(client,"retry@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Retry"}).json()
    first=client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"first@example.com"}).json()
    second=client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"second@example.com"}).json()
    camp=client.post("/api/v1/campaigns",json={"name":"Retry","audience_id":a["id"],"subject":"Retry","body_html":"Hello"}).json()

    from types import SimpleNamespace
    import app.services.campaigns as service
    sent=[]
    state={"attempt":0}

    class FakeSMTP:
        def __init__(self,*args,**kwargs): pass
        def starttls(self): pass
        def login(self,*args,**kwargs): pass
        def send_message(self,message):
            sent.append(message["To"])
            if state["attempt"]==0 and message["To"]=="second@example.com":
                raise OSError("temporary failure")
        def quit(self): pass

    monkeypatch.setattr(service,"smtplib",SimpleNamespace(SMTP=FakeSMTP))
    monkeypatch.setattr(service,"get_settings",lambda:SimpleNamespace(
        smtp_host="smtp.example",smtp_port=587,smtp_username=None,smtp_password=None,
        smtp_from_email="sender@example.com",smtp_use_tls=False,public_base_url="http://localhost:8000"
    ))

    first_report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert first_report["summary"]["sent"]==1
    assert first_report["summary"]["failed"]==1
    assert first_report["latest_run_status"]=="partial"

    state["attempt"]=1
    second_report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert second_report["summary"]["sent"]==2
    assert second_report["summary"]["failed"]==1
    assert second_report["latest_run_status"]=="sent"
    assert sent.count("first@example.com")==1
    assert sent.count("second@example.com")==2

def test_malformed_password_hash_is_auth_failure(client):
    register(client,"malformed@example.com")
    from tests.conftest import engine
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from app.models import User
    with Session(engine) as db:
        user=db.scalar(select(User).where(User.email=="malformed@example.com"))
        user.password_hash="not-a-valid-argon2-hash"
        db.commit()
    assert client.post("/api/v1/auth/login",json={"email":"malformed@example.com","password":"strong-password-123"}).status_code==401

def test_cross_user_isolation(client):
    register(client,"one@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Private"}).json()
    c=client.post("/api/v1/campaigns",json={"name":"Private","audience_id":a["id"],"subject":"x","body_html":"x"}).json()
    client.post("/api/v1/auth/logout")
    register(client,"two@example.com")
    assert client.get(f"/api/v1/audiences/{a['id']}/contacts").status_code==404
    assert client.get(f"/api/v1/campaigns/{c['id']}/report").status_code==404

def test_dashboard_summary(client):
    register(client,"dash@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Dash"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"dash-contact@example.com"})
    data=client.get("/api/v1/dashboard/summary").json()
    assert data["audience_contacts"]==1 and data["audiences"]==1

def test_execution_is_single_use_while_queued(client):
    register(client,"queued@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Queued"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"queued-contact@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"Queued","audience_id":a["id"],"subject":"x","body_html":"x"
    }).json()
    first=client.post(f"/api/v1/campaigns/{camp['id']}/execute")
    assert first.status_code==202
    second=client.post(f"/api/v1/campaigns/{camp['id']}/execute")
    assert second.status_code==409

def test_scheduled_campaign_is_queued_by_worker(client):
    register(client,"worker@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Worker"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"worker-contact@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"Worker","audience_id":a["id"],"subject":"x","body_html":"x",
        "scheduled_at":"2999-01-01T12:00:00Z",
    }).json()
    assert camp["status"]=="scheduled"
    from datetime import datetime, timezone
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import Campaign
    with Session(engine) as db:
        row=db.get(Campaign,camp["id"])
        row.scheduled_at=datetime.now(timezone.utc)
        db.commit()
    from app.worker import process_due_campaigns
    assert process_due_campaigns()>=1
    data=client.get(f"/api/v1/campaigns/{camp['id']}/report").json()
    assert data["campaign"]["status"]=="queued"
    assert data["latest_run_status"]=="queued"
    assert data["summary"]["queued"]==1

def test_tracking_is_idempotent_and_invalid_token_is_rejected(client):
    register(client,"tracking@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Tracking"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"tracking-contact@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"Tracking","audience_id":a["id"],"subject":"x","body_html":"x"
    }).json()
    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["summary"]["queued"]==1
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import Delivery,CampaignEvent
    with Session(engine) as db:
        delivery=db.scalar(select(Delivery))
        token=delivery.tracking_token
    assert client.get(f"/track/{token}/open").status_code==200
    assert client.get(f"/track/{token}/open").status_code==200
    assert client.get(f"/track/{token}/click",params={"url":"https://example.com"},follow_redirects=False).status_code==307
    assert client.get(f"/track/{token}/click",params={"url":"https://example.com"},follow_redirects=False).status_code==307
    with Session(engine) as db:
        assert db.scalar(select(__import__("sqlalchemy").func.count(CampaignEvent.id)).where(
            CampaignEvent.delivery_id==delivery.id
        ))==2
    assert client.get("/track/not-a-real-token/open").status_code==404

def test_cross_user_campaign_creation_is_forbidden(client):
    register(client,"owner@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Owner"}).json()
    client.post("/api/v1/auth/logout")
    register(client,"other@example.com")
    assert client.post("/api/v1/campaigns",json={
        "name":"Forbidden","audience_id":a["id"],"subject":"x","body_html":"x"
    }).status_code==404

def test_contact_with_campaign_history_cannot_be_deleted(client):
    register(client,"history@example.com")
    a=client.post("/api/v1/audiences",json={"name":"History"}).json()
    c=client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"history-contact@example.com"}).json()
    camp=client.post("/api/v1/campaigns",json={
        "name":"History","audience_id":a["id"],"subject":"x","body_html":"x"
    }).json()
    assert client.post(f"/api/v1/campaigns/{camp['id']}/execute").status_code==202
    assert client.delete(f"/api/v1/audiences/{a['id']}/contacts/{c['id']}").status_code==409

def test_campaign_editing_respects_execution_state(client):
    register(client,"edit@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Edit"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"edit-contact@example.com"})
    camp=client.post("/api/v1/campaigns",json={
        "name":"Edit","audience_id":a["id"],"subject":"x","body_html":"x"
    }).json()
    assert client.post(f"/api/v1/campaigns/{camp['id']}/execute").status_code==202
    assert client.patch(f"/api/v1/campaigns/{camp['id']}",json={"subject":"changed"}).status_code==409


def test_logout_sets_security_headers(client):
    register(client, "logout-headers@example.com")
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["clear-site-data"] == '"cache", "cookies", "storage"'
    assert client.get("/api/v1/auth/me").status_code == 401


def test_cors_preflight_allows_configured_frontend_origin(client):
    response = client.options(
        "/api/v1/auth/me",
        headers={
            "Origin": "http://testserver",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_duplicate_contact_and_delete_before_history(client):
    register(client, "contacts-lifecycle@example.com")
    audience = client.post("/api/v1/audiences", json={"name": "Contacts"}).json()
    contact = client.post(
        f"/api/v1/audiences/{audience['id']}/contacts",
        json={"email": "lifecycle@example.com"},
    ).json()

    duplicate = client.post(
        f"/api/v1/audiences/{audience['id']}/contacts",
        json={"email": "LIFECYCLE@example.com"},
    )
    assert duplicate.status_code == 409

    deleted = client.delete(
        f"/api/v1/audiences/{audience['id']}/contacts/{contact['id']}"
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/audiences/{audience['id']}/contacts").json() == []


def test_campaign_update_and_schedule_lifecycle(client):
    register(client, "campaign-lifecycle@example.com")
    audience = client.post("/api/v1/audiences", json={"name": "Lifecycle"}).json()
    client.post(
        f"/api/v1/audiences/{audience['id']}/contacts",
        json={"email": "lifecycle-target@example.com"},
    )
    campaign = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Lifecycle",
            "audience_id": audience["id"],
            "subject": "Original",
            "body_html": "<p>Original</p>",
        },
    ).json()
    assert campaign["status"] == "draft"

    updated = client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        json={"subject": "Updated"},
    )
    assert updated.status_code == 200
    assert updated.json()["subject"] == "Updated"

    scheduled = client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        json={"scheduled_at": "2999-01-01T12:00:00Z"},
    )
    assert scheduled.status_code == 200
    assert scheduled.json()["status"] == "scheduled"

    returned_to_draft = client.patch(
        f"/api/v1/campaigns/{campaign['id']}",
        json={"scheduled_at": None},
    )
    assert returned_to_draft.status_code == 200
    assert returned_to_draft.json()["status"] == "draft"

    executed = client.post(f"/api/v1/campaigns/{campaign['id']}/execute")
    assert executed.status_code == 202
    assert executed.json()["latest_run_status"] == "queued"


def test_unsubscribe_get_only_shows_confirmation(client):
    register(client, "unsubscribe-confirm@example.com")
    audience = client.post("/api/v1/audiences", json={"name": "Confirm"}).json()
    client.post(
        f"/api/v1/audiences/{audience['id']}/contacts",
        json={"email": "confirm@example.com"},
    )
    campaign = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Confirm",
            "audience_id": audience["id"],
            "subject": "x",
            "body_html": "<p>x</p>",
        },
    ).json()
    client.post(f"/api/v1/campaigns/{campaign['id']}/execute")

    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import Contact, Delivery

    with Session(engine) as db:
        delivery = db.scalar(select(Delivery))
        contact = db.get(Contact, delivery.contact_id)
        token = delivery.tracking_token
        assert contact.unsubscribed_at is None

    page = client.get(f"/track/{token}/unsubscribe")
    assert page.status_code == 200
    assert "Confirm unsubscribe" in page.text

    with Session(engine) as db:
        contact = db.get(Contact, delivery.contact_id)
        assert contact.unsubscribed_at is None

    action = client.post(f"/track/{token}/unsubscribe")
    assert action.status_code == 200
    with Session(engine) as db:
        contact = db.get(Contact, delivery.contact_id)
        assert contact.unsubscribed_at is not None


def test_analytics_counts_unique_tracking_events(client):
    register(client, "analytics-events@example.com")
    audience = client.post("/api/v1/audiences", json={"name": "Analytics"}).json()
    client.post(
        f"/api/v1/audiences/{audience['id']}/contacts",
        json={"email": "analytics@example.com"},
    )
    campaign = client.post(
        "/api/v1/campaigns",
        json={
            "name": "Analytics",
            "audience_id": audience["id"],
            "subject": "x",
            "body_html": "<a href='https://example.com/report'>x</a>",
        },
    ).json()
    report = client.post(f"/api/v1/campaigns/{campaign['id']}/execute").json()

    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from tests.conftest import engine
    from app.models import Delivery

    with Session(engine) as db:
        delivery = db.scalar(select(Delivery))
        token = delivery.tracking_token

    client.get(f"/track/{token}/open")
    client.get(f"/track/{token}/open")
    client.get(
        f"/track/{token}/click",
        params={"url": "https://example.com/report"},
        follow_redirects=False,
    )
    client.get(
        f"/track/{token}/click",
        params={"url": "https://example.com/report"},
        follow_redirects=False,
    )

    data = client.get("/api/v1/analytics/overview").json()
    assert report["summary"]["total"] == 1
    assert data == {
        "deliveries": 1,
        "sent": 0,
        "failed": 0,
        "opened": 1,
        "clicked": 1,
    }


def test_unknown_tracking_event_is_rejected(client):
    register(client, "tracking-event@example.com")
    assert client.get("/track/not-a-token/video").status_code == 404
    assert client.post("/track/not-a-token/video").status_code == 404
