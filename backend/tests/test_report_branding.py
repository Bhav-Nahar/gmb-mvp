"""Whose logo ends up on an exported report.

The failure this guards against is silent and only visible to an agency's own
client: a non-agency org that happens to have brand fields set (left over from a
downgrade, or seeded by mistake) must still export as Pinzo.
"""
from types import SimpleNamespace

from app.services.branding import PINZO, report_branding


def _org(**kw):
    base = dict(name="Acme Retail", is_agency=False, brand_name=None,
                brand_logo_url=None, brand_website_url=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_plain_org_gets_pinzo():
    assert report_branding(_org()) == PINZO


def test_brand_fields_ignored_until_super_admin_enables_agency():
    org = _org(brand_name="RankWise", brand_logo_url="https://rankwise.in/logo.png",
               brand_website_url="https://rankwise.in")
    assert report_branding(org) == PINZO


def test_agency_branding_replaces_pinzo():
    org = _org(is_agency=True, brand_name="RankWise",
               brand_logo_url="https://rankwise.in/logo.png",
               brand_website_url="https://rankwise.in")
    assert report_branding(org) == {
        "name": "RankWise",
        "logo_url": "https://rankwise.in/logo.png",
        "website_url": "https://rankwise.in",
    }


def test_partial_agency_config_falls_back_per_field():
    # Logo uploaded, website never filled in — keep the logo, borrow Pinzo's URL.
    org = _org(is_agency=True, brand_logo_url="https://rankwise.in/logo.png")
    out = report_branding(org)
    assert out["logo_url"] == "https://rankwise.in/logo.png"
    assert out["website_url"] == PINZO["website_url"]
    assert out["name"] == "Acme Retail"  # no brand_name set → org's own name


def test_missing_org_does_not_explode():
    assert report_branding(None) == PINZO


# --- the email body must not be injectable through the brand fields ----------

def test_brand_fields_cannot_inject_html_into_the_weekly_email():
    """brand_* is user input and lands in src/href/alt. The URL validator only checks
    the http(s) prefix, so a quote inside the URL would break out of the attribute."""
    from types import SimpleNamespace
    from app.tasks_reports import _render_html, _KPI_COLS

    org = _org(is_agency=True,
               brand_name='RankWise"><script>alert(1)</script>',
               brand_logo_url='https://x.test/l.png" onerror="alert(2)',
               brand_website_url='https://x.test')
    cur = SimpleNamespace(**{k: 5 for k, _ in _KPI_COLS})
    html = _render_html(report_branding(org), 'Acme <b>Ltd</b>', 'Aug 01 - Aug 07',
                        cur, cur, 4.5, 2, 1, 'https://app.test')

    assert "<script>" not in html
    assert 'onerror="alert(2)"' not in html
    assert "<b>Ltd</b>" not in html          # org name is escaped too
    assert "&lt;script&gt;" in html          # ...and still shown, just inert
    assert "&quot;" in html                  # the attribute-breaking quote is neutralised
