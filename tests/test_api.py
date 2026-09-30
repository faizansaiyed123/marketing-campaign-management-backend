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
    assert client.post(f"/track/{token}/unsubscribe",data="List-Unsubscribe=One-Click",headers={"Content-Type":"application/x-www-form-urlencoded"}).status_code==200
    assert client.get(f"/track/{token}/unsubscribe").status_code==200
    with Session(engine) as db:
        contact=db.scalar(select(Contact).where(Contact.email=="person@example.com"))
        assert contact.unsubscribed_at is None
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


def test_empty_campaign_completes_without_smtp(client):
    register(client,"empty@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Empty"}).json()
    camp=client.post("/api/v1/campaigns",json={
        "name":"Empty campaign","audience_id":a["id"],"subject":"x","body_html":"x",
    }).json()
    report=client.post(f"/api/v1/campaigns/{camp['id']}/execute").json()
    assert report["summary"]["total"]==0
    assert report["latest_run_status"]=="completed"
    assert report["campaign"]["status"]=="completed"

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
