# Pinzo Local SEO Industry x City Template and Content Guardrails

## 1. Purpose

This document defines the reusable page system for:

`Local SEO Services for {Industry Plural} in {City}`

The completed reference page is:

`Local SEO Services for Dentists in Mumbai`

Reference route:

`/en-in/local-seo-services/dentists-in-mumbai`

The template is designed for commercial Local SEO pages that combine:

- One real industry
- One real city or city-region
- A clear service proposition
- Genuine industry search behaviour
- Genuine city and catchment logic
- Single-location and multi-location use cases
- Google Maps, website SEO, reviews, local authority, conversion tracking and AI search visibility

This is not a name-swap template. Every generated page must earn its right to be indexed.

## 2. Deliverables in this package

1. `pinzo-local-seo-dentists-mumbai.html`
   - Complete responsive HTML page
   - Populated with Dentists and Mumbai
   - Includes CSS, JavaScript, lead form, tracking fields and JSON-LD

2. `pinzo-local-seo-industry-city-import-ready.csv`
   - One complete Dentists in Mumbai row
   - Opens with the same 50-column structure as the approved GBP management import
     files, then appends the recovered columns described in section 10
   - Uses pipe separators inside repeatable fields
   - Uses double-colon separators between labels and values

3. `pinzo-local-seo-industry-city-template-and-guardrails.md`
   - Template logic
   - Content rules
   - Technical requirements
   - QA and indexation controls

## 3. Page identity

| Item | Rule |
| --- | --- |
| Page family | Industry x City Local SEO landing page |
| Search intent | Commercial investigation and lead generation |
| Primary keyword pattern | local SEO services for {industry plural} in {city} |
| URL pattern | `/{locale}/local-seo-services/{industry-slug}-in-{city-slug}` |
| Parent country pillar | `/{locale}/local-seo-services/` |
| Parent industry pillar | `/{locale}/local-seo-services/{industry-slug}/` |
| Related GBP page | `/{locale}/gbp-management/{industry-slug}-in-{city-slug}` |
| Initial robots state | `noindex,nofollow` during QA |
| Eligible robots state | `index,follow` only after every launch gate passes |
| Schema baseline | Organization, WebSite, WebPage, Service, BreadcrumbList, FAQPage |

## 4. Core variables

The generator must support the following variables. A variable can only be used when its source has been reviewed.

| Variable | Example | Source |
| --- | --- | --- |
| `{locale}` | en-in | Country master |
| `{country}` | India | Country master |
| `{country_code}` | IN | Country master |
| `{region}` | Maharashtra | City master |
| `{city}` | Mumbai | City master |
| `{city_slug}` | mumbai | City master |
| `{industry_singular}` | dentist | Industry master |
| `{industry_plural}` | dentists | Industry master |
| `{industry_slug}` | dentists | Industry master |
| `{business_label}` | dental clinic | Industry master |
| `{customer_label}` | patient | Industry master |
| `{conversion_label}` | appointment | Industry master |
| `{primary_keyword}` | local SEO services for dentists in Mumbai | Keyword map |
| `{primary_cta}` | Get a Free Dental SEO Audit | CTA library |
| `{secondary_cta}` | Start Free Trial | CTA library |
| `{canonical_url}` | Full self-canonical URL | URL generator |
| `{last_updated}` | 2026-07-25 | Publishing workflow |

## 5. Non-negotiable content rules

### 5.1 No Unicode en or em dash

The characters below are prohibited in all generated content:

- Unicode code point 2013, commonly used for the en dash
- Unicode code point 2014, commonly used for the em dash
- Named HTML entities that render either character
- Numeric HTML entities that render either character
- Escaped JSON values that render either character

Do not replace every prohibited dash with a normal hyphen. Choose punctuation according to meaning:

| Intended relationship | Preferred replacement |
| --- | --- |
| New thought | Full stop |
| Explanation | Colon |
| Short interruption | Comma |
| Optional detail | Parentheses |
| Range | `to` |
| Contrast | `but`, `while` or a new sentence |

Examples:

Bad:

`Local SEO is not only about rankings, it is about visibility, trust and conversion.`

Better:

`Local SEO covers more than rankings. It should improve visibility, trust and enquiries.`

Bad:

`The first 90 days focus on three areas: foundations, content and measurement.`

Better:

`During the first 90 days, we fix the basics, strengthen priority pages and set up reliable measurement.`

### 5.2 Human editorial standard

Every page must sound as if a Local SEO strategist studied the industry and city before writing it.

Required:

- Use direct sentences.
- Mix short and medium sentence lengths.
- Name real customer decisions, services, operational constraints and conversion actions.
- Explain why a point matters to the specific industry.
- Use local details only when they change search behaviour or conversion.
- Write for a business owner first and a search engine second.
- Use plain language before technical terminology.
- State uncertainty where proximity, competition, regulations or platform behaviour can change the outcome.

Avoid:

- Generic motivational introductions
- Empty superlatives
- Repeating the same three-part sentence pattern
- Excessive use of `whether`, `from X to Y`, `not only`, `unlock`, `leverage`, `seamless`, `robust`, `holistic`, `dynamic`, `digital landscape` or `game changer`
- Repeating the industry and city in every paragraph
- Artificially formal phrases such as `within one accountable service framework`
- Claims that Pinzo controls Google, ChatGPT, Gemini, Perplexity or another third-party platform
- Claims that visibility, rankings, leads or revenue are guaranteed
- Invented reviews, rankings, customer names, awards, partnerships, statistics or case-study results

### 5.3 No doorway content

A city page must not imply that Pinzo has an office in the city unless that office is real and verifiable.

An industry x city page must not:

- Publish a list of neighbourhood names without explaining their relevance.
- Claim visibility across every locality.
- create near-identical suburb pages for places where the business has no location or genuine service relationship.
- Use `LocalBusiness` schema for Pinzo unless the page represents a real Pinzo location.
- Copy city paragraphs from another market and replace place names.

### 5.4 Evidence standard

Allowed proof:

- Real Pinzo screenshots
- Approved customer work
- Verified public client information
- Labelled sample reports
- Labelled illustrative dashboards
- Auditable workflow examples

Not allowed:

- Fabricated performance figures
- Anonymous testimonials presented as real
- Sample data presented as customer performance
- Unverified platform integrations
- Unsupported claims about AI recommendations

Every sample must include the word `Sample`, `Example` or `Illustrative` close to the asset.

## 6. Page structure

### 6.1 Head metadata

Required:

- UTF-8 charset
- Responsive viewport
- Unique title
- Unique meta description
- Robots directive
- Self-canonical
- Open Graph title, description, type, URL and approved image
- Twitter card metadata
- Theme colour

Title pattern:

`Local SEO Services for {Industry Plural} in {City} | Pinzo`

Target title length:

45 to 65 characters. Review manually when the city or industry name is long.

Meta description pattern:

`Help more {customer label plural} find your {business label} on Google Maps, local search and AI search with Pinzo's Local SEO services for {industry plural} in {city}.`

Target description length:

130 to 160 characters. Do not cut a sentence to force the limit.

### 6.2 Header and navigation

Required links:

- Services
- Industry strategy
- AI search
- Process
- FAQ
- Explore Platform
- Start Free Trial
- Get Free Audit

Mobile behaviour:

- Menu button must expose `aria-expanded`.
- Menu must close after a navigation link is selected.
- The audit CTA may remain sticky on small screens.
- The sticky CTA must hide when the audit form enters the viewport.

### 6.3 Breadcrumb

Required hierarchy:

1. Home
2. Local SEO Services country pillar
3. Industry pillar
4. Current city

Do not link an unpublished parent page. If a required parent is not live, keep the page on `noindex` and publish the parent first.

### 6.4 Hero

Required content:

- Eyebrow with the managed Local SEO and AI visibility proposition
- One H1
- Two-sentence hero copy
- Primary audit CTA
- Secondary free-trial CTA
- Three concise capability points
- Labelled dashboard preview

Hero copy must answer:

- Who the service is for
- Where the service applies
- Which discovery surfaces are included
- What makes Pinzo different

Do not open with:

- A definition of SEO
- A generic statement about competition
- An unsupported market statistic
- A fear-based claim

### 6.5 Dashboard preview

The preview may show:

- Local SEO opportunity score
- Geo-grid ranking pattern
- GBP health
- Service or treatment page gaps
- AI prompt coverage

Rules:

- Use `Sample view`, `Illustrative` or an equivalent label.
- Do not imply that sample scores belong to a customer.
- Use text labels such as `Needs improvement`, not fabricated commercial outcomes.

### 6.6 Proof strip

Use four short value areas:

1. Google Maps visibility
2. Industry website SEO
3. Reviews and reputation
4. AI search visibility

Each description should be one sentence and specific to the page.

### 6.7 Direct answer

Heading:

`What are Local SEO services for {industry plural} in {city}?`

Answer requirements:

- 45 to 90 words
- First sentence answers the question directly
- Mentions Google Maps and local organic search
- Explains the wider scope beyond GBP management
- Includes industry-specific website or service content
- Includes tracking and conversion measurement
- Mentions AI search support without making a promise

### 6.8 Industry search behaviour

Minimum four search journeys:

1. Location or near-me search
2. Product, service or treatment search
3. Urgency, availability or convenience search
4. Trust, comparison or proof search

Each card must name real queries or decision factors. Do not use the same four cards for every industry.

Dental example:

- Locality and near-me searches
- Treatment-led searches
- Urgency and availability
- Trust and convenience

### 6.9 Customer journey diagram

Default stages:

1. Search
2. Compare
3. Evaluate
4. Contact
5. Book or buy

The final stage must match the industry conversion. Examples include book, visit, enquire, call, order or request a quote.

### 6.10 Complete service matrix

The table must cover all ten areas:

1. Google Maps and GBP
2. Website SEO
3. Product, service or treatment page SEO
4. Reviews and reputation
5. Citations and data consistency
6. Local authority and links
7. Technical SEO
8. Geo-grid and local rank tracking
9. Conversion tracking
10. AI search visibility

Each row requires:

- What Pinzo manages
- Why it matters to the industry

Do not let this page collapse into a GBP-only page.

### 6.11 Industry strategy

Create three useful groups based on demand or customer decision-making.

Dental example:

- High-value planned treatments
- Urgent and pain-led treatments
- Repeat-visit and family treatments

The accompanying entity list must only contain services genuinely relevant to the industry.

### 6.12 City and catchment strategy

The city section must explain:

- How far customers are likely to travel
- When proximity becomes more important
- How transport, access, parking, hours or landmarks affect conversion
- How multi-location accuracy changes by branch
- Why real location pages are different from doorway pages

Minimum local evidence:

- Five useful local references, or
- Three references plus a well-supported catchment explanation

Place names must have context. A locality list alone does not count as unique city content.

### 6.13 Single-location and multi-location models

Single-location section:

- One main GBP
- One realistic catchment
- Accurate services and capacity
- Review, photo and conversion workflow
- Calls, forms and visibility reporting

Multi-location section:

- Central governance
- Unique branch pages
- Branch-level services and staff availability
- Local reviews and competitors
- Location dashboards and performance comparison

### 6.14 AI search visibility

Required principles:

- AI search does not replace Local SEO.
- Keep business, staff, service and location details consistent.
- Answer real customer questions clearly.
- Build sources that search systems can crawl and verify.
- Track prompts, mentions, citations, factual accuracy and assisted visits.
- Do not guarantee a mention or recommendation.
- Do not invent an `AI schema`.

The section should explain the work in plain language before using terms such as entity, citation or structured data.

### 6.15 Monthly deliverables

Required monthly outputs:

- Action plan
- GBP work
- Website and technical SEO
- Reviews and reputation
- Local rank tracking
- AI visibility checks
- Conversion tracking
- Monthly report
- Strategy review

Every deliverable must state what is reviewed or completed. Avoid vague promises such as `ongoing optimisation`.

### 6.16 First 90 days

Default phases:

1. Audit and prioritise
2. Build the foundation
3. Expand and measure

Rules:

- Do not promise rankings by a specific day.
- Name actual work.
- Connect each phase to a measurable baseline or output.
- Adapt the work to the industry and city.

### 6.17 Comparison table

Compare:

- Agency only
- Software only
- Pinzo managed model

Required comparison dimensions:

- Strategy
- Execution
- Location-level visibility
- Multi-location governance
- AI search monitoring
- Reporting transparency

Keep the comparison fair. A competing model can be a good fit when the buyer has the right internal capability.

### 6.18 Engagement models

Required cards:

1. Pinzo Platform
2. Pinzo Managed Local SEO
3. Pinzo for multi-location groups

Each card must explain:

- Best-fit buyer
- What is included
- Who executes
- Next step

Do not display made-up discounts or pricing. Link to the live pricing page when current prices are not embedded.

### 6.19 Proof and reports

Minimum proof area:

- Sample monthly visibility report
- Sample Local SEO audit
- Example geo-grid analysis
- Sample review-theme analysis
- Platform walkthrough

Before indexation, replace illustrative blocks with approved assets where possible.

### 6.20 FAQs

Required count:

8 to 14.

Mandatory topics:

- Definition
- Local SEO versus GBP management
- Realistic city coverage
- Priority services or products
- Expected timeline
- AI search
- Multi-location support
- Measurement
- Page strategy
- Pricing factors

Visible questions and answers must match FAQ schema exactly.

### 6.21 Lead form

Required fields:

- Name
- Business or group name
- Phone or WhatsApp number
- Number of locations
- Website or Google Maps link
- Primary goal
- Consent
- UTM source
- UTM medium
- UTM campaign
- GCLID
- Landing-page URL

Form rules:

- Use server-side validation in production.
- Keep the honeypot or replace it with approved spam protection.
- Disable the submit button while the request is in progress.
- Show success only after the lead endpoint confirms a successful response.
- Keep entered data when submission fails.
- Never send phone, email or form content into the analytics event payload.
- Record location count, lead type and landing-page URL only when approved by the analytics policy.

The reference HTML currently posts to FormSubmit. Replace this with the approved Pinzo CRM or API endpoint before long-term production use.

### 6.22 Related links

An Industry x City page should link to:

- Country Local SEO pillar
- City pillar
- Industry pillar
- Matching GBP management page
- Relevant specialist service
- Local rank tracker
- Pricing or free trial
- Relevant healthcare or industry pages

Target at least 15 contextual internal links across the page. Do not create a footer-only link wall.

Only link to live URLs. Keep the page on `noindex` when required parent or child pages are not yet published.

## 7. Schema rules

### Organization

Use Pinzo's real organization details only.

Do not use:

- A fake local office
- A city address that Pinzo does not occupy
- `LocalBusiness` solely because the service page targets a city

### WebSite and WebPage

Required:

- Matching URL
- Matching title
- Matching description
- Correct `inLanguage`
- `isPartOf` relationship
- Breadcrumb relationship where implemented

### Service

Required:

- Accurate service name
- Provider set to Pinzo
- `areaServed` set to the real commercial service area
- Audience or service output that matches visible content
- No ranking guarantee

### BreadcrumbList

Breadcrumb schema and visible breadcrumbs must use the same hierarchy and URLs.

### FAQPage

FAQ schema must be generated from the final visible FAQ copy. Do not maintain a separate question source that can drift.

## 8. HTML and accessibility requirements

Required:

- One H1
- Logical H2 and H3 hierarchy
- Semantic `header`, `main`, `section`, `article`, `nav`, `form` and `footer`
- Label for every form control
- Descriptive `aria-label` on illustrative UI blocks
- `aria-expanded` on menu and FAQ controls
- Keyboard-accessible buttons
- Visible focus state
- Respect for `prefers-reduced-motion`
- Responsive tables
- No horizontal overflow
- Minimum 44-pixel touch target for primary interactive controls
- Safe `rel="noopener"` on new-tab links

## 9. Performance requirements

- Keep the page usable without a JavaScript framework.
- Minimise external dependencies.
- Compress and size all production images.
- Set width and height on images when known.
- Avoid large autoplay video.
- Lazy-load below-the-fold production images.
- Keep critical layout CSS in the page only when this matches the deployment system.
- Move shared CSS and JavaScript to versioned assets when this page becomes part of a larger production system.

## 10. CSV serialization rules

The import file opens with the 50-column structure used by the GBP management
category. Those 50 columns keep their original names, order and values.

The GBP header has no column for several sections this template renders, and its
`solutions` column is only two parts wide where the service matrix is three. Rather
than overload a GBP column, the file appends 15 canonical columns after column 50:

`answer_heading`, `search_intents`, `journey_stages`, `proof_points`, `services`,
`strategy_heading`, `strategy_body`, `value_props`, `city_factors`, `deliverables`,
`workflow_phases`, `comparison`, `plans`, `lead_heading`, `lead_sub`

A canonical column always wins over the GBP column the importer would otherwise
alias onto it, so `services` supersedes `solutions` and `search_intents` supersedes
`why_matters_points`. Total: 65 columns.

Field shapes for the appended columns:

| Column | Shape |
| --- | --- |
| `services` | `SEO area::what Pinzo manages::why it matters` |
| `comparison` | `requirement::agency only::software only::Pinzo managed model` |
| `workflow_phases` | `days::title::step;step;step` |
| `plans` | `tag::name::description::feature;feature;feature::cta label::cta href::featured` |
| the rest | `Label::Description` pairs, or plain text |

Repeatable item separator:

`|`

Label and description separator:

`::`

Examples:

`Problem::Impact|Problem::Impact`

`Question::Answer|Question::Answer`

Rules:

- Save as UTF-8.
- Quote fields according to RFC 4180.
- Do not place raw line breaks inside fields unless the importer explicitly supports them.
- Do not use `|` or `::` inside normal prose.
- Use absolute URLs in `canonical_url`.
- Use route paths in `url`.
- Keep FAQ copy identical to visible HTML and JSON-LD.
- Keep `index_status` as `noindex` until launch gates pass.

## 11. Quality and indexation gates

| Criterion | Maximum | Pass requirement |
| --- | ---: | --- |
| URL, locale and canonical | 10 | Route, canonical and locale match |
| Metadata and intent | 10 | Unique title, description, H1 and intent |
| Industry uniqueness | 15 | Real services, customer decisions, trust and conversion |
| City uniqueness | 15 | Useful catchment logic and real local context |
| Service depth | 10 | Full Local SEO scope, not GBP only |
| AEO and FAQ | 10 | Direct answers and exact schema parity |
| AI readiness | 10 | Safe claims, clear entities and useful answers |
| Proof and trust | 10 | Real proof or clearly labelled samples |
| Internal linking | 5 | Relevant links with no broken destinations |
| Technical and conversion | 5 | Valid schema, mobile UX, form storage and analytics |

Decision rules:

| Score | Status | Robots |
| ---: | --- | --- |
| 90 to 100 | Priority index candidate | `index,follow` after final launch QA |
| 80 to 89 | Eligible after review | `index,follow` after proof and technical QA |
| 70 to 79 | Preview only | `noindex,follow` |
| Below 70 | Incomplete | `noindex,nofollow` |

## 12. Anti-duplication test

Before a page can be indexed, an editor must be able to answer yes to all questions:

1. Does the industry search section describe real behaviour for this industry?
2. Does the city section explain a real catchment rather than list neighbourhoods?
3. Does the service matrix use industry-specific examples?
4. Does the conversion journey end in the correct action?
5. Are single-location and multi-location workflows meaningfully different?
6. Are the FAQs adapted to real buyer questions?
7. Are proof assets real or clearly labelled as samples?
8. Are internal links relevant and live?
9. Does the form store a lead before displaying success?
10. Would the page still be useful if the exact-match keyword were removed from the H1?

If any answer is no, keep the page on `noindex`.

## 13. Editorial lint

Run all checks against:

- HTML source
- Visible page text
- Meta tags
- JSON-LD
- JavaScript strings
- CSV values
- Markdown specification

Required checks:

```text
Prohibited Unicode or encoded dash:
Scan for Unicode code points 2013 and 2014, plus their named HTML,
numeric HTML and escaped JSON forms.

One H1:
count(//h1) = 1

FAQ parity:
visible FAQ question and answer = FAQPage question and answer

No duplicate IDs:
count(unique id values) = count(all id values)

No false success:
success state requires a confirmed successful HTTP response
```

Recommended phrase review:

```text
unlock
game changer
digital landscape
seamless
robust
holistic
revolutionise
supercharge
one-stop solution
at the end of the day
in today's fast-paced world
```

A phrase match does not always mean the copy is wrong, but it requires human review.

## 14. Final launch checklist

- [ ] Title, description, H1 and canonical are unique.
- [ ] Country, region, city and locale are correct.
- [ ] No Unicode en or em dash exists anywhere.
- [ ] Copy has passed a human editorial review.
- [ ] No unsupported claim or invented proof exists.
- [ ] All sample assets are labelled.
- [ ] All internal links return a valid destination.
- [ ] Parent pillar pages are live.
- [ ] Form sends data to the approved endpoint.
- [ ] A test lead is received in the CRM or approved inbox.
- [ ] Success appears only after confirmed delivery.
- [ ] UTM and GCLID values are stored.
- [ ] Analytics events exclude personal data.
- [ ] JSON-LD is valid and matches visible content.
- [ ] Mobile navigation, tables, FAQs and sticky CTA work.
- [ ] Privacy and consent copy has been approved.
- [ ] Robots state matches the QA score and launch decision.
- [ ] Page has been checked on desktop and mobile.

## 15. Reference page status

The Dentists in Mumbai HTML supplied with this package is ready for upload as a controlled preview.

Keep it on `noindex` until:

- The country and industry parent pages are live.
- Every internal link has been checked.
- The lead destination is approved for production.
- A real end-to-end lead test passes.
- The final proof assets are approved.
- The page passes the launch checklist above.
