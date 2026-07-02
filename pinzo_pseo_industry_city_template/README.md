# Pinzo pSEO Template: Industry × City Landing Pages

This package contains a scalable but quality-controlled template for Pinzo's programmatic SEO page type:

`/google-business-profile-management-for-{industry}-in-{city}/`

The template is designed for SEO + AIO/GEO/AEO visibility while avoiding thin doorway pages. Each page must solve a real industry + city intent and connect naturally to Pinzo's product/service use cases.

## Files

1. `TEMPLATE.md` — Master content template with all modules, copy logic, and section rules.
2. `variable_schema.json` — Required input fields for every generated page.
3. `cms_output_schema.json` — Recommended CMS-ready output structure.
4. `qa_checklist.md` — Quality scoring system before publishing.
5. `schema_markup_guide.md` — Full JSON-LD implementation guide and schema QA rules.
6. `json_ld_templates.json` — Reusable schema templates for mass production.
7. `example_doctors_mumbai_brief.md` — Example page brief for `/google-business-profile-management-for-doctors-clinics-in-mumbai/`.

## Publishing rule

Do not generate pages directly from only `{industry}` and `{city}`.

Each page needs unique inputs for:
- Industry pain points
- City/local buyer behavior
- GBP categories and services
- Review themes
- Google Posts ideas
- Photo/video requirements
- Competitor/local SERP observations
- Pinzo product use cases
- CTA and lead magnet

Minimum publish score: 80/100.


## Required schema stack

Every live page should output one combined JSON-LD graph with:

- `WebPage`
- `BreadcrumbList`
- `Service`
- `Organization`
- `SoftwareApplication`

Optional schema can be added only when the visible page content supports it:

- `FAQPage`
- `ItemList`
- `Offer`
- `VideoObject`
- `ImageObject`

Do not use `LocalBusiness`, `Review`, or `AggregateRating` by default. These are allowed only when the claim is truthful, visible on the page, and compliant.
