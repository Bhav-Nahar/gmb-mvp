# Pinzo pSEO QA Checklist: Industry × City Pages

Publish only if score is 80/100 or above.

## 1. Intent satisfaction — 15 points

- Page clearly answers what GBP management means for the industry in the city. — 4
- Page explains who the service/tool is for. — 3
- Page gives actionable guidance before pitching Pinzo. — 4
- Page includes local discovery/search behavior. — 4

## 2. Industry specificity — 20 points

- Includes at least 5 industry pain points. — 5
- Includes real category/service examples. — 4
- Includes review strategy specific to the industry. — 4
- Includes Google Posts ideas specific to the industry. — 3
- Includes photo/video guidance specific to the industry. — 2
- Includes compliance/sensitivity notes where relevant. — 2

## 3. City/local relevance — 15 points

- Includes city-specific search modifiers. — 3
- Includes neighborhoods/service areas naturally. — 3
- Explains local buyer behavior. — 3
- Includes local market/competition context without fake claims. — 3
- Avoids simple city-name swapping. — 3

## 4. Pinzo product alignment — 15 points

- Connects to GBP audit. — 2
- Connects to AI review replies. — 2
- Connects to Google Posts scheduler. — 2
- Connects to services/category optimization. — 2
- Connects to reporting/profile score. — 2
- Connects to managed service or trial CTA. — 3
- Explains workflow/process clearly. — 2

## 5. AIO/GEO/AEO readiness — 15 points

- Includes 40–70 word quick answer block near the top. — 3
- Uses clean entity-rich headings. — 2
- Includes checklist/table/scorecard. — 3
- Includes 7+ FAQs with direct answers. — 3
- Uses clear, factual, non-hype language. — 2
- Outputs required JSON-LD graph: `WebPage`, `BreadcrumbList`, `Service`, `Organization`, and `SoftwareApplication`. — 2

## 6. SEO and internal linking — 10 points

- Meta title and description are unique. — 2
- H1 is aligned with URL and primary keyword. — 2
- Includes mapped internal links. — 3
- Uses natural anchor text. — 1
- Avoids keyword stuffing. — 2

## 7. Risk control — 10 points

- No guaranteed ranking claims. — 2
- No fake case studies or fake local proof. — 2
- No claim of being Google or officially affiliated with Google unless verified. — 2
- No unethical review removal or fake review advice. — 2
- Regulated industry disclaimers included where needed. — 2

## 8. Schema QA gate — mandatory pass/fail

This gate does not add points. A page fails publish-readiness if any item fails.

- JSON-LD is valid and included in rendered HTML.
- Required schema stack is present: `WebPage`, `BreadcrumbList`, `Service`, `Organization`, `SoftwareApplication`.
- `WebPage.mainEntity` points to the page-specific `Service`.
- `Service.provider` points to Pinzo `Organization`.
- `Service.areaServed` matches the target city.
- `Service.audience` matches the target industry.
- `BreadcrumbList` matches visible breadcrumb/navigation.
- `FAQPage` is enabled only if FAQs are visible on the page.
- `Offer` is enabled only if the offer/audit/demo/pricing is visible on the page.
- `LocalBusiness` is disabled unless Pinzo has truthful local presence data.
- No fake `Review`, fake `AggregateRating`, fake address, or fake pricing.
- URL, canonical URL, and schema URL are consistent.
- Tested in Rich Results Test or Schema Markup Validator before publishing.

## Score interpretation

- 90–100: Ready to publish
- 80–89: Publish after editor review
- 70–79: Keep as draft; improve unique content
- Below 70: Do not publish
