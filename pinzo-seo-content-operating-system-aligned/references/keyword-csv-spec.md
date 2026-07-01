# Pinzo Keyword CSV Specification

The skill can accept keyword exports or use the built-in strategy files.

## Preferred input columns

| Column | Required | Description |
|---|---:|---|
| Keyword | Yes | Search query |
| Intent | Recommended | Informational, commercial, transactional, navigational, local, comparison |
| Volume | Recommended | Monthly volume |
| KD | Recommended | Keyword difficulty |
| Cluster | Recommended | Topic cluster |
| Mapped URL | Recommended | Canonical URL for the keyword |
| Page Type | Recommended | Product Landing, Guide, Feature Landing, Industry Landing, Tool Page, etc. |
| Funnel | Recommended | TOFU, MOFU, BOFU |
| Business Fit | Recommended | 1-5 score |
| SEO Effort | Optional | Low, Medium, High |
| Priority | Recommended | P1, P2, P3 |
| Priority Score | Optional | Numeric score |

## Mapping rules

- If `Mapped URL` exists, use it.
- If keyword has similar intent to an existing page, add it as a section or FAQ, not a new page.
- Create new pages only when the job-to-be-done is distinct.
- Prioritize business fit and conversion potential over volume alone.
- Navigational/support keywords require disclaimers and cautious positioning.
- Head terms should strengthen the product hub.
