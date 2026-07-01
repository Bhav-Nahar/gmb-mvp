# Pinzo Bulk Keyword Clustering and Mapping Prompt

Use this when the user uploads or pastes many keywords.

## Goal

Map every keyword to an existing Pinzo roadmap URL where possible. Create new URLs only when search intent is distinct and cannibalization risk is low.

## Inputs

Keyword CSV:
```
{{keyword_csv}}
```

Existing roadmap:
- `strategy/page-roadmap.csv`
- `strategy/keyword-mapping.csv`
- `strategy/cluster-summary.csv`

## Output

For each keyword or keyword group, return:

| Keyword Group | Primary Keyword | Secondary Keywords | Intent | Cluster | Mapped URL | Page Type | Priority | Funnel | Business Fit | New Page Needed? | Cannibalization Risk | Recommended CTA | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|

## Rules

- Prefer existing mapped URL when the keyword is already in `keyword-mapping.csv`.
- Do not create separate pages for small variants of login/account/app/head-term searches.
- Create support sections inside parent pages when intent overlap is high.
- Create separate pages only for different jobs-to-be-done: setup, verification, optimization, reviews, posts, services/categories, photos/logo, support, suspension, ownership, tools, industry, agency, multi-location, comparison.
- Mark page priority as P1/P2/P3 based on roadmap and cluster commercial potential.
- Recommend a lead magnet from `cro-lead-magnets.csv`.
- Flag pSEO candidates but cap rollout per `programmatic-seo.csv`.
