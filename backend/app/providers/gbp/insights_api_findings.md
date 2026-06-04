# Google Business Profile Performance API v1 Findings

This document summarizes findings on the response schema, metrics structure, date formats, and sparse data handling of the Google Business Profile Performance API (`v1` endpoint).

---

## 1. Request Structure
The API endpoint is queried using a `POST` request to fetch daily time-series:
```http
POST https://businessprofileperformance.googleapis.com/v1/{location_id=locations/*}:fetchMultiDailyMetricsTimeSeries
```

Payload example:
```json
{
  "dailyMetrics": [
    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
    "WEBSITE_CLICKS",
    "CALL_CLICKS",
    "BUSINESS_DIRECTION_REQUESTS",
    "QUERIES_DIRECT",
    "QUERIES_INDIRECT",
    "QUERIES_CHAIN"
  ],
  "dailyRange": {
    "startDate": { "year": 2026, "month": 6, "day": 1 },
    "endDate": { "year": 2026, "month": 6, "day": 18 }
  }
}
```

---

## 2. API Response Schema

The response has the top-level key `multiDailyMetricTimeSeries` containing an array of objects. Each object contains `dailyMetricTimeSeries`, which is a list of time-series data grouped by metric.

### Schema Blueprint (JSON)
```json
{
  "multiDailyMetricTimeSeries": [
    {
      "dailyMetricTimeSeries": [
        {
          "dailyMetric": "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
          "timeSeries": {
            "datedValues": [
              {
                "date": { "year": 2026, "month": 6, "day": 1 },
                "value": "15"
              },
              {
                "date": { "year": 2026, "month": 6, "day": 2 },
                "value": "20"
              }
            ]
          }
        },
        {
          "dailyMetric": "CALL_CLICKS",
          "timeSeries": {
            "datedValues": [
              {
                "date": { "year": 2026, "month": 6, "day": 1 },
                "value": "3"
              }
            ]
          }
        }
      ]
    }
  ]
}
```

---

## 3. Key Observations & Design Decisions

### Date Representation
Dates are represented as nested objects: `{"year": YYYY, "month": MM, "day": DD}`. In the normalization layer, we parse these objects into Python's `datetime.date`.

### Sparse-Day Behavior
- **Omission of Zero Values**: If a metric has no activity on a given date (e.g. 0 call clicks), the date object is **completely omitted** from the `datedValues` list for that metric.
- **Sparse Days**: Not all days in the requested window will appear in the API output.
- **Resolution**: The normalization algorithm initializes all dates within the expected `startDate` → `endDate` range to zero using a pre-populated dictionary `day_data = {date: DailyInsightMetric(date=date)}`. Values are then accumulated incrementally.

### Pagination
- The endpoint supports pagination via `nextPageToken`.
- When paginating, we pass `pageToken` as a query parameter in subsequent requests.

### Normalization Metric Map
The raw GBP metric names are converted to internal schema columns using the following map:
- `BUSINESS_IMPRESSIONS_DESKTOP_SEARCH` + `BUSINESS_IMPRESSIONS_MOBILE_SEARCH` $\rightarrow$ `search_views` (aggregated)
- `BUSINESS_IMPRESSIONS_DESKTOP_MAPS` + `BUSINESS_IMPRESSIONS_MOBILE_MAPS` $\rightarrow$ `map_views` (aggregated)
- `WEBSITE_CLICKS` $\rightarrow$ `website_clicks` (1:1 mapping)
- `CALL_CLICKS` $\rightarrow$ `phone_calls` (1:1 mapping)
- `BUSINESS_DIRECTION_REQUESTS` $\rightarrow$ `direction_requests` (1:1 mapping)
- `QUERIES_DIRECT` $\rightarrow$ `search_queries_direct` (1:1 mapping)
- `QUERIES_INDIRECT` $\rightarrow$ `search_queries_indirect` (1:1 mapping)
- `QUERIES_CHAIN` $\rightarrow$ `search_queries_chain` (1:1 mapping)
- Unmapped metrics log a warning and are ignored.
