"""Guards the pSEO/lpSEO revalidation payload — the heart of the cost fix.

The invariant that matters: a revalidation NEVER emits a bare global tag
('pseo' / 'lpseo'). Only per-slug tags + the shared list tag. If that regresses,
one admin edit invalidates every page's cache again (Vercel + backend + Redis
cost blowup), so this test exists to fail loudly if someone reintroduces it.
"""
from app.services.revalidation_service import _seo_revalidation_payload


def test_no_global_tag_only_per_slug_and_list():
    p = _seo_revalidation_payload(
        [{"slug": "dentists-in-mumbai", "country": "in", "industry_slug": "dentists"}],
        "local-seo-services", "lpseo",
    )
    assert "lpseo" not in p["tags"]          # the bug: global tag would hit every page
    assert "lpseo-list" in p["tags"]         # hubs/sitemap refresh
    assert "lpseo:dentists-in-mumbai" in p["tags"]
    assert "/en-in/local-seo-services" in p["paths"]                    # root hub
    assert "/en-in/local-seo-services/dentists" in p["paths"]           # industry hub
    assert "/en-in/local-seo-services/dentists-in-mumbai" in p["paths"] # leaf


def test_batch_tags_scale_with_slugs_not_globally():
    entries = [{"slug": f"s{i}", "country": "us", "industry_slug": "plumbers"} for i in range(50)]
    p = _seo_revalidation_payload(entries, "gbp-management", "pseo")
    assert "pseo" not in p["tags"]
    slug_tags = [t for t in p["tags"] if t.startswith("pseo:")]
    assert len(slug_tags) == 50               # exactly the touched pages, nothing more
    assert p["tags"].count("pseo-list") == 1


def test_missing_slug_and_industry_are_skipped():
    p = _seo_revalidation_payload(
        [{"slug": None}, {"slug": "x-in-y", "country": "gb"}],  # no industry_slug -> no hub path
        "local-seo-services", "lpseo",
    )
    assert p["tags"] == ["lpseo-list", "lpseo:x-in-y"]
    assert "/en-gb/local-seo-services/x-in-y" in p["paths"]
    assert not any(pth.endswith("/None") for pth in p["paths"])


if __name__ == "__main__":
    test_no_global_tag_only_per_slug_and_list()
    test_batch_tags_scale_with_slugs_not_globally()
    test_missing_slug_and_industry_are_skipped()
    print("ok")
