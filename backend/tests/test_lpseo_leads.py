"""Covers the lpSEO lead capture path: the enquiry must survive a failed
notification email, because the form shows the visitor a success screen either way.
Email sending is stubbed so nothing hits the network.
"""
from app.api import lpseo as lpseo_api
from app.api.lpseo import LpseoLeadIn, create_lead, admin_list_leads, admin_delete_lead
from app.models.lpseo_lead import LpseoLead


def _payload(**kw):
    base = dict(name="Dr Anita Rao", clinic="Smile Dental", phone="+919999999999",
                goal="More calls and enquiries", page="/en-in/local-seo-services/dentists-in-mumbai",
                utm_source="google", utm_medium="cpc", gclid="Cj0KTest")
    base.update(kw)
    return LpseoLeadIn(**base)


def _stub_email(monkeypatch, sent: bool):
    monkeypatch.setattr(lpseo_api, "send_email", lambda *a, **k: sent)
    monkeypatch.setattr(lpseo_api.settings, "SUPERADMIN_EMAILS", "ops@pinzo.io")


def test_lead_is_stored_even_when_the_email_fails(db, monkeypatch):
    # The regression this table exists for: Resend down / key missing used to mean
    # the lead vanished while the visitor saw "Request received".
    _stub_email(monkeypatch, sent=False)
    result = create_lead(payload=_payload(), db=db)

    lead = db.query(LpseoLead).one()
    assert result == {"ok": True, "id": lead.id}
    assert lead.name == "Dr Anita Rao" and lead.phone == "+919999999999"
    assert lead.gclid == "Cj0KTest" and lead.utm_source == "google"
    assert lead.emailed is False  # flagged for the admin banner


def test_lead_marked_emailed_on_success(db, monkeypatch):
    _stub_email(monkeypatch, sent=True)
    create_lead(payload=_payload(), db=db)
    assert db.query(LpseoLead).one().emailed is True


def test_lead_survives_an_email_exception(db, monkeypatch):
    monkeypatch.setattr(lpseo_api.settings, "SUPERADMIN_EMAILS", "ops@pinzo.io")
    monkeypatch.setattr(lpseo_api, "send_email", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    create_lead(payload=_payload(), db=db)
    assert db.query(LpseoLead).one().emailed is False


def test_honeypot_submission_is_not_stored(db, monkeypatch):
    _stub_email(monkeypatch, sent=True)
    # Same 201 shape as a real submit so the bot cannot tell it was dropped.
    assert create_lead(payload=_payload(company="spam-co"), db=db) == {"ok": True}
    assert db.query(LpseoLead).count() == 0


def test_admin_list_searches_and_reports_unemailed(db, monkeypatch):
    _stub_email(monkeypatch, sent=False)
    create_lead(payload=_payload(name="Dr Anita Rao"), db=db)
    _stub_email(monkeypatch, sent=True)
    create_lead(payload=_payload(name="Ravi Kumar", clinic="Kumar Dental"), db=db)

    everything = admin_list_leads(db=db, _=None)
    assert everything["total"] == 2 and everything["not_emailed"] == 1

    hit = admin_list_leads(q="kumar", db=db, _=None)
    assert hit["total"] == 1 and hit["leads"][0]["name"] == "Ravi Kumar"


def test_admin_delete_lead(db, monkeypatch):
    _stub_email(monkeypatch, sent=True)
    lead_id = create_lead(payload=_payload(), db=db)["id"]
    assert admin_delete_lead(lead_id, db=db, _=None) == {"deleted": True}
    assert db.query(LpseoLead).count() == 0
