# Pinzo CMS Output JSON Spec

Use this structure when the user asks for content that can be taken live on Pinzo's website.

```json
{
  "strategy_brief": {
    "mapped_url": "",
    "page_type": "",
    "priority": "",
    "cluster": "",
    "primary_keyword": "",
    "secondary_keywords": [],
    "search_intent": "",
    "funnel_stage": "",
    "business_fit": "",
    "lead_magnet": "",
    "main_cta": "",
    "cannibalization_notes": ""
  },
  "seo": {
    "slug": "",
    "title_tag": "",
    "meta_description": "",
    "canonical_url": "",
    "h1": "",
    "excerpt": "",
    "breadcrumbs": []
  },
  "content": {
    "body_markdown": "",
    "toc": [],
    "faq": [
      {
        "question": "",
        "answer": ""
      }
    ],
    "tables": [],
    "checklists": [],
    "templates": []
  },
  "conversion": {
    "primary_cta": "",
    "secondary_cta": "",
    "lead_magnet": "",
    "cta_blocks": [
      {
        "placement": "",
        "headline": "",
        "copy": "",
        "button_text": "",
        "target_url_or_event": ""
      }
    ]
  },
  "internal_links": [
    {
      "target_url": "",
      "anchor_text": "",
      "placement": "",
      "reason": ""
    }
  ],
  "media": {
    "screenshot_brief": [],
    "image_file_names": [],
    "alt_text": []
  },
  "schema": {
    "recommended_types": [],
    "notes": "",
    "json_ld_sample": {}
  },
  "tracking": {
    "events": [
      "seo_cta_click",
      "free_audit_start",
      "demo_click",
      "whatsapp_click",
      "tool_use",
      "pricing_view"
    ],
    "gsc_segment": ""
  },
  "technical": {
    "indexability": "index, follow",
    "canonical_policy": "self-canonical unless user says otherwise",
    "sitemap_group": "",
    "lastmod_guidance": "update only when materially changed",
    "rendering_requirement": "server-rendered or pre-rendered primary content"
  },
  "source_notes": [],
  "qa": {
    "publish_readiness_score": 0,
    "threshold": 0,
    "missing_items": [],
    "risk_notes": [],
    "update_frequency": ""
  }
}
```
