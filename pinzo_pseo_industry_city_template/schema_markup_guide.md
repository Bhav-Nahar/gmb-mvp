# Pinzo pSEO Industry × City Schema Markup Guide

URL pattern:

```text
/google-business-profile-management-for-{industry_slug}-in-{city_slug}/
```

This schema guide is for Pinzo pSEO landing pages that target:

```text
Google Business Profile management for {industry_label} in {city_label}
```

The goal is to make each page machine-readable for Google Search, AI Overviews/AI Mode, and other answer engines without creating fake local-business signals or unsupported rich-result claims.

---

## 1. Required schema stack for every industry × city page

Every published page should include one JSON-LD graph containing these entities:

1. `WebPage`
2. `BreadcrumbList`
3. `Service`
4. `Organization`
5. `SoftwareApplication`

Recommended JSON-LD structure:

```html
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    { "@type": "Organization" },
    { "@type": "SoftwareApplication" },
    { "@type": "Service" },
    { "@type": "WebPage" },
    { "@type": "BreadcrumbList" }
  ]
}
</script>
```

Why this stack:

- `WebPage` defines the page topic and primary entity.
- `BreadcrumbList` helps search engines understand page hierarchy.
- `Service` describes the offer: GBP management for a specific industry in a specific city.
- `Organization` identifies Pinzo as the provider.
- `SoftwareApplication` identifies Pinzo as a software/product layer, especially where the page promotes audit, review replies, posts, reporting, and profile quality workflows.

---

## 2. Optional schema blocks

Use optional schema only when the visible page content supports it.

| Schema | Use when | Avoid when |
|---|---|---|
| `FAQPage` | The page has visible FAQ questions and answers | Do not expect FAQ rich results for most commercial sites |
| `Offer` | Pricing, demo, audit, or managed-service offer is clearly shown on the page | Pricing is vague or not visible |
| `ItemList` | The page shows a visible checklist, list of modules, service checklist, or post ideas | The list is hidden or generated only in schema |
| `VideoObject` | The page embeds a real Pinzo demo/video with thumbnail, upload date, and transcript/description | No actual video exists |
| `ImageObject` | The page uses original images or screenshots with meaningful alt text | Generic stock image only |
| `Review` / `AggregateRating` | Only when legitimate reviews for Pinzo are visible on the page and meet Google guidelines | Never use fake reviews, self-created ratings, or ratings about another business |

---

## 3. Do not use these by default

### `LocalBusiness`

Do **not** use `LocalBusiness` on every city page just because the page targets a city.

Use `LocalBusiness` only if Pinzo has a real local office, branch, or verified service-area presence that can be represented truthfully. For industry × city pSEO pages, `Service` with `areaServed` is safer.

### `HowTo`

Do not use `HowTo` as the default schema for this landing page pattern. These pages are commercial service pages, not pure step-by-step how-to documents.

### `Product` as the primary entity

Use `SoftwareApplication` for the Pinzo tool. Use `Service` for the managed GBP service. Do not force `Product` unless a product/pricing page specifically supports it.

---

## 4. Required entity relationships

Use stable `@id` values so entities connect cleanly.

Recommended IDs:

```text
https://pinzo.io/#organization
https://pinzo.io/#software
https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#webpage
https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#service
https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#breadcrumb
```

Relationship rules:

- `Service.provider` should reference `https://pinzo.io/#organization`.
- `Service.serviceOutput` should mention practical outputs such as audit report, optimized services, review reply workflow, Google Posts calendar, and monthly GBP report.
- `Service.areaServed` should be the target city.
- `Service.audience` should mention the target industry.
- `WebPage.mainEntity` should reference the page-specific `Service`.
- `WebPage.publisher` should reference Pinzo Organization.
- `SoftwareApplication.provider` should reference Pinzo Organization.
- `BreadcrumbList.itemListElement` should reflect the actual breadcrumb links shown on page.

---

## 5. Required JSON-LD variables

The content generation system must supply these values before schema generation:

```json
{
  "site_url": "https://pinzo.io",
  "brand_name": "Pinzo",
  "organization_id": "https://pinzo.io/#organization",
  "software_id": "https://pinzo.io/#software",
  "page_url": "https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/",
  "page_id": "https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#webpage",
  "service_id": "https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#service",
  "breadcrumb_id": "https://pinzo.io/google-business-profile-management-for-{industry_slug}-in-{city_slug}/#breadcrumb",
  "industry_label": "Doctors & Clinics",
  "industry_singular": "clinic",
  "industry_slug": "doctors-clinics",
  "city_label": "Mumbai",
  "city_slug": "mumbai",
  "primary_keyword": "Google Business Profile management for doctors in Mumbai",
  "meta_title": "Google Business Profile Management for Doctors in Mumbai | Pinzo",
  "meta_description": "Audit, optimize, and manage Google Business Profiles for clinics in Mumbai with Pinzo's GBP workflow, review replies, posts, services, and reports.",
  "page_summary": "Pinzo helps clinics in Mumbai audit, optimize, and manage their Google Business Profiles with services, categories, review replies, posts, photos, and monthly reporting.",
  "date_published": "YYYY-MM-DD",
  "date_modified": "YYYY-MM-DD",
  "industry_services": ["Dental implants", "Root canal", "Teeth whitening"],
  "pinzo_modules": ["GBP audit", "AI review replies", "Google Posts scheduler", "Profile quality score"],
  "faq_json": [
    {
      "question": "What is Google Business Profile management for clinics in Mumbai?",
      "answer": "It is the process of keeping a clinic's Google Business Profile complete, accurate, active, and conversion-ready across Search and Maps."
    }
  ]
}
```

---

## 6. Final combined JSON-LD template

Use this as the default schema output for every page. Replace all `{{variables}}` with final page values.

```json
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "@id": "{{organization_id}}",
      "name": "Pinzo",
      "url": "{{site_url}}/",
      "logo": {
        "@type": "ImageObject",
        "url": "{{site_url}}/logo.png"
      },
      "sameAs": [
        "{{pinzo_linkedin_url}}",
        "{{pinzo_instagram_url}}",
        "{{pinzo_facebook_url}}"
      ],
      "description": "Pinzo helps businesses audit, optimize, and manage Google Business Profiles across reviews, posts, services, profile quality, and local reporting."
    },
    {
      "@type": "SoftwareApplication",
      "@id": "{{software_id}}",
      "name": "Pinzo",
      "url": "{{site_url}}/google-business-profile-management-tool/",
      "applicationCategory": "BusinessApplication",
      "operatingSystem": "Web",
      "provider": {
        "@id": "{{organization_id}}"
      },
      "description": "AI-powered Google Business Profile management software for audits, AI review replies, Google Posts, services, quality scoring, and reporting.",
      "offers": {
        "@type": "Offer",
        "url": "{{site_url}}/pricing/",
        "priceCurrency": "INR",
        "availability": "https://schema.org/InStock"
      }
    },
    {
      "@type": "Service",
      "@id": "{{service_id}}",
      "name": "Google Business Profile management for {{industry_label}} in {{city_label}}",
      "serviceType": "Google Business Profile management",
      "category": "Local SEO and Google Business Profile management",
      "provider": {
        "@id": "{{organization_id}}"
      },
      "areaServed": {
        "@type": "City",
        "name": "{{city_label}}"
      },
      "audience": {
        "@type": "BusinessAudience",
        "audienceType": "{{industry_label}}"
      },
      "description": "{{page_summary}}",
      "url": "{{page_url}}",
      "hasOfferCatalog": {
        "@type": "OfferCatalog",
        "name": "Pinzo GBP management modules for {{industry_label}}",
        "itemListElement": [
          {
            "@type": "Offer",
            "itemOffered": {
              "@type": "Service",
              "name": "Google Business Profile audit"
            }
          },
          {
            "@type": "Offer",
            "itemOffered": {
              "@type": "Service",
              "name": "Google review management and AI replies"
            }
          },
          {
            "@type": "Offer",
            "itemOffered": {
              "@type": "Service",
              "name": "Google Posts planning and scheduling"
            }
          },
          {
            "@type": "Offer",
            "itemOffered": {
              "@type": "Service",
              "name": "Google Business Profile services and category optimization"
            }
          },
          {
            "@type": "Offer",
            "itemOffered": {
              "@type": "Service",
              "name": "Monthly Google Business Profile reporting"
            }
          }
        ]
      },
      "serviceOutput": [
        "Google Business Profile audit report",
        "Industry-specific service and category recommendations",
        "Review reply workflow",
        "Google Posts calendar",
        "Profile quality score",
        "Monthly local visibility report"
      ]
    },
    {
      "@type": "WebPage",
      "@id": "{{page_id}}",
      "url": "{{page_url}}",
      "name": "{{meta_title}}",
      "headline": "Google Business Profile Management for {{industry_label}} in {{city_label}}",
      "description": "{{meta_description}}",
      "inLanguage": "en-IN",
      "isPartOf": {
        "@type": "WebSite",
        "@id": "{{site_url}}/#website",
        "url": "{{site_url}}/",
        "name": "Pinzo"
      },
      "publisher": {
        "@id": "{{organization_id}}"
      },
      "mainEntity": {
        "@id": "{{service_id}}"
      },
      "breadcrumb": {
        "@id": "{{breadcrumb_id}}"
      },
      "about": [
        {
          "@type": "Thing",
          "name": "Google Business Profile management"
        },
        {
          "@type": "Thing",
          "name": "Local SEO"
        },
        {
          "@type": "Thing",
          "name": "Google Maps visibility"
        }
      ],
      "mentions": [
        {
          "@type": "SoftwareApplication",
          "@id": "{{software_id}}"
        }
      ],
      "datePublished": "{{date_published}}",
      "dateModified": "{{date_modified}}"
    },
    {
      "@type": "BreadcrumbList",
      "@id": "{{breadcrumb_id}}",
      "itemListElement": [
        {
          "@type": "ListItem",
          "position": 1,
          "name": "Home",
          "item": "{{site_url}}/"
        },
        {
          "@type": "ListItem",
          "position": 2,
          "name": "Google Business Profile Management",
          "item": "{{site_url}}/google-business-profile-management-tool/"
        },
        {
          "@type": "ListItem",
          "position": 3,
          "name": "{{industry_label}} in {{city_label}}",
          "item": "{{page_url}}"
        }
      ]
    }
  ]
}
```

---

## 7. FAQPage add-on template

Use this only if the FAQ section is visible on the page and the schema answers exactly match the visible answers.

Important: FAQ markup can still describe page content, but FAQ rich results are heavily restricted and should not be treated as a traffic-growth guarantee.

```json
{
  "@type": "FAQPage",
  "@id": "{{page_url}}#faq",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "{{faq_question_1}}",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "{{faq_answer_1}}"
      }
    },
    {
      "@type": "Question",
      "name": "{{faq_question_2}}",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "{{faq_answer_2}}"
      }
    }
  ]
}
```

Implementation rule:

- Add the FAQPage object inside the same `@graph`.
- Use all visible FAQs, not just 2.
- Do not include FAQs that are not visible on the page.
- Do not stuff keywords in FAQ questions.

---

## 8. ItemList add-on template for checklist modules

Use this if the page includes a visible checklist such as “Google Business Profile checklist for dentists in Pune.”

```json
{
  "@type": "ItemList",
  "@id": "{{page_url}}#gbp-checklist",
  "name": "Google Business Profile checklist for {{industry_label}} in {{city_label}}",
  "itemListOrder": "https://schema.org/ItemListOrderAscending",
  "numberOfItems": {{checklist_count}},
  "itemListElement": [
    {
      "@type": "ListItem",
      "position": 1,
      "name": "Add accurate primary and secondary categories"
    },
    {
      "@type": "ListItem",
      "position": 2,
      "name": "Add important services with clear descriptions"
    },
    {
      "@type": "ListItem",
      "position": 3,
      "name": "Reply to new reviews with useful, non-robotic responses"
    }
  ]
}
```

---

## 9. Offer add-on template

Use this only when the page visibly promotes a specific audit, consultation, demo, package, or managed service.

```json
{
  "@type": "Offer",
  "@id": "{{page_url}}#offer",
  "name": "{{lead_magnet}} for {{industry_label}} in {{city_label}}",
  "url": "{{page_url}}",
  "priceCurrency": "INR",
  "availability": "https://schema.org/InStock",
  "itemOffered": {
    "@id": "{{service_id}}"
  },
  "eligibleRegion": {
    "@type": "City",
    "name": "{{city_label}}"
  }
}
```

If the lead magnet is free, add:

```json
"price": "0"
```

Only do this if the page clearly says the audit/checklist/demo is free.

---

## 10. Schema QA rules

Before publishing, validate every page against this checklist:

1. JSON-LD is valid JSON.
2. Schema is placed in the rendered HTML, not blocked behind client-side delays.
3. Structured data content matches visible page content.
4. Page is indexable if schema is intended for Search.
5. Page URL, canonical URL, and schema URL match.
6. `Service.areaServed.name` matches the target city.
7. `Service.audience.audienceType` matches the target industry.
8. `WebPage.mainEntity` points to the page-specific `Service`.
9. `BreadcrumbList` matches visible breadcrumb/navigation.
10. `FAQPage` is used only when FAQ content is visible.
11. No fake reviews, fake ratings, fake pricing, or fake local address.
12. No guaranteed ranking or guaranteed review-removal claims.
13. No `LocalBusiness` unless Pinzo has truthful local presence data.
14. Test with Google Rich Results Test and Schema Markup Validator before publishing.

---

## 11. Recommended CMS fields for schema

Add these fields to the CMS so schema can be generated programmatically:

```json
{
  "schema_enabled": true,
  "schema_type_stack": ["WebPage", "BreadcrumbList", "Service", "Organization", "SoftwareApplication"],
  "include_faq_schema": true,
  "include_itemlist_schema": true,
  "include_offer_schema": true,
  "include_localbusiness_schema": false,
  "schema_jsonld": {},
  "schema_validation_status": "not_tested | passed | failed",
  "schema_validation_notes": "string"
}
```

---

## 12. Developer implementation note for Bhav

Generate schema from the same final CMS fields used to render visible page content. Do not maintain a separate manual schema database unless absolutely necessary.

Best implementation:

1. CMS saves final page variables.
2. Frontend renders visible content.
3. Schema generator reads the same CMS variables.
4. JSON-LD is injected server-side or during static generation.
5. QA validates rendered HTML output.

This prevents mismatch between visible content and structured data.
