def register(client,email,name="User"):
    r=client.post("/api/v1/auth/register",json={"email":email,"name":name,"password":"strong-password-123"}); assert r.status_code==201,r.text
def test_health(client):
    assert client.get("/health").json()=={"status":"ok"}
def test_auth_flow(client):
    register(client,"auth@example.com"); assert client.get("/api/v1/auth/me").status_code==200; client.post("/api/v1/auth/logout"); assert client.get("/api/v1/auth/me").status_code==401; assert client.post("/api/v1/auth/login",json={"email":"auth@example.com","password":"strong-password-123"}).status_code==200
def test_campaign_flow_and_tracking(client):
    register(client,"campaign@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Launch List"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"person@example.com"})
    c=client.post("/api/v1/campaigns",json={"name":"Launch","audience_id":a["id"],"subject":"Hello","body_html":"<h1>Hello</h1>"}).json()
    r=client.post(f"/api/v1/campaigns/{c['id']}/execute"); assert r.status_code==202; assert r.json()["summary"]["queued"]==1
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models import Delivery
    with SessionLocal() as db: token=db.scalar(select(Delivery.tracking_token))
    assert client.post(f"/track/{token}/open").status_code==204
    assert client.post(f"/track/{token}/open").status_code==204
    assert client.get(f"/api/v1/campaigns/{c['id']}/report").json()["summary"]["opened"]==1
def test_cross_user_isolation(client):
    register(client,"one@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Private"}).json()
    c=client.post("/api/v1/campaigns",json={"name":"Private","audience_id":a["id"],"subject":"x","body_html":"x"}).json()
    client.post("/api/v1/auth/logout"); register(client,"two@example.com")
    assert client.get(f"/api/v1/audiences/{a['id']}/contacts").status_code==404
    assert client.get(f"/api/v1/campaigns/{c['id']}/report").status_code==404
def test_dashboard_summary(client):
    register(client,"dash@example.com")
    a=client.post("/api/v1/audiences",json={"name":"Dash"}).json()
    client.post(f"/api/v1/audiences/{a['id']}/contacts",json={"email":"dash@example.com"})
    client.post("/api/v1/campaigns",json={"name":"Dash Campaign","audience_id":a["id"],"subject":"x","body_html":"x"})
    data=client.get("/api/v1/dashboard/summary").json()
    assert data["audience_contacts"]==1 and data["audiences"]==1
