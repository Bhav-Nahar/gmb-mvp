import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.comparison_cache_service import ComparisonCacheService

# Metrics charted as a daily series (sum metrics only — rates/ratings are noisy per-day).
SERIES_METRICS = {
    "profile_views", "search_impressions", "maps_views", "phone_calls",
    "website_clicks", "direction_requests", "reviews_received",
    "searches_direct", "searches_indirect", "searches_chain",
    "positive_review_count", "neutral_review_count", "negative_review_count",
}


def _metrics_select(t: str) -> str:
    """SUM/weighted-avg/recomputed-rate columns for source alias `t` (ldi or gdi)."""
    return f"""
        COALESCE(SUM({t}.profile_views),0) as profile_views,
        COALESCE(SUM({t}.search_impressions),0) as search_impressions,
        COALESCE(SUM({t}.maps_views),0) as maps_views,
        COALESCE(SUM({t}.phone_calls),0) as phone_calls,
        COALESCE(SUM({t}.website_clicks),0) as website_clicks,
        COALESCE(SUM({t}.direction_requests),0) as direction_requests,
        COALESCE(SUM({t}.reviews_received),0) as reviews_received,
        COALESCE(SUM({t}.searches_direct),0) as searches_direct,
        COALESCE(SUM({t}.searches_indirect),0) as searches_indirect,
        COALESCE(SUM({t}.searches_chain),0) as searches_chain,
        COALESCE(SUM({t}.positive_review_count),0) as positive_review_count,
        COALESCE(SUM({t}.neutral_review_count),0) as neutral_review_count,
        COALESCE(SUM({t}.negative_review_count),0) as negative_review_count,
        CASE WHEN SUM({t}.reviews_received)>0 THEN SUM({t}.avg_rating*{t}.reviews_received)/SUM({t}.reviews_received) END as avg_rating,
        CASE WHEN SUM({t}.reviews_received)>0 THEN SUM({t}.avg_sentiment_score*{t}.reviews_received)/SUM({t}.reviews_received) END as avg_sentiment_score,
        CASE WHEN SUM({t}.reviews_received)>0 THEN SUM({t}.response_rate*{t}.reviews_received)/SUM({t}.reviews_received) ELSE 0 END as response_rate,
        CASE WHEN SUM({t}.reviews_received)>0 THEN SUM({t}.avg_response_time_hours*{t}.reviews_received)/SUM({t}.reviews_received) END as avg_response_time_hours,
        CASE WHEN SUM({t}.profile_views)>0 THEN CAST(SUM({t}.website_clicks) AS float)/SUM({t}.profile_views)*100 END as click_through_rate,
        CASE WHEN SUM({t}.profile_views)>0 THEN CAST(SUM({t}.phone_calls) AS float)/SUM({t}.profile_views)*100 END as call_conversion_rate,
        CASE WHEN SUM({t}.profile_views)>0 THEN CAST(SUM({t}.direction_requests) AS float)/SUM({t}.profile_views)*100 END as direction_conversion_rate
    """


# avg_rank/solv only exist on group_daily_insights (from rank scans), so they're
# selected per-branch for REGION/CUSTOM_GROUP; CITY/STATE rows leave them null.
_METRIC_KEYS = [
    "profile_views", "search_impressions", "maps_views", "phone_calls",
    "website_clicks", "direction_requests", "reviews_received",
    "searches_direct", "searches_indirect", "searches_chain",
    "positive_review_count", "neutral_review_count", "negative_review_count",
    "avg_rating", "avg_sentiment_score", "response_rate", "avg_response_time_hours",
    "click_through_rate", "call_conversion_rate", "direction_conversion_rate",
    "avg_rank", "solv",
]

_FLOAT_KEYS = {
    "avg_rating", "avg_sentiment_score", "response_rate", "avg_response_time_hours",
    "click_through_rate", "call_conversion_rate", "direction_conversion_rate",
    "avg_rank", "solv",
}


def _row_metrics(row) -> dict:
    out = {}
    for k in _METRIC_KEYS:
        v = getattr(row, k, None)
        if v is None:
            out[k] = None
        elif k in _FLOAT_KEYS:
            out[k] = round(float(v), 2)
        else:
            out[k] = int(v)
    return out

# Region = an auto-derived geographic zone from the location's state, so REGION
# behaves like CITY/STATE (no user-defined regions table). India only for now —
# add other countries' zones here when locations outside India appear.
INDIA_ZONES = {
    "North": ["Delhi", "Haryana", "Punjab", "Uttar Pradesh", "Uttarakhand",
              "Himachal Pradesh", "Jammu and Kashmir", "Ladakh", "Chandigarh", "Rajasthan"],
    "West": ["Maharashtra", "Gujarat", "Goa", "Dadra and Nagar Haveli and Daman and Diu"],
    "South": ["Karnataka", "Kerala", "Tamil Nadu", "Andhra Pradesh", "Telangana", "Puducherry"],
    "East": ["West Bengal", "Bihar", "Jharkhand", "Odisha"],
    "Central": ["Madhya Pradesh", "Chhattisgarh"],
    "Northeast": ["Assam", "Meghalaya", "Manipur", "Mizoram", "Nagaland",
                  "Tripura", "Arunachal Pradesh", "Sikkim"],
}


def _region_case(col: str = "l.state") -> str:
    """SQL CASE mapping a state column to its India zone (NULL if unmapped)."""
    whens = " ".join(
        f"WHEN {col} IN ({', '.join(repr(s) for s in states)}) THEN {zone!r}"
        for zone, states in INDIA_ZONES.items()
    )
    return f"CASE {whens} ELSE NULL END"


def _geo_col(group_type: str) -> str:
    """The group-by column for a location-level (CITY/STATE/REGION) comparison."""
    if group_type == "CITY":
        return "l.city"
    if group_type == "REGION":
        return _region_case("l.state")
    return "l.state"


class ComparisonSnapshotService:

    @staticmethod
    def _coerce_filters(filters: dict, group_type: str) -> tuple[date, date, list[Any]]:
        """Parses dates and coerces group_ids types correctly."""
        start_date = date.fromisoformat(filters["start_date"]) if isinstance(filters["start_date"], str) else filters["start_date"]
        end_date = date.fromisoformat(filters["end_date"]) if isinstance(filters["end_date"], str) else filters["end_date"]

        group_ids = filters.get("group_ids") or []
        if group_type == "CUSTOM_GROUP" and group_ids:
            # Coerce string IDs to integers to match the DB column type
            # (REGION group_ids are zone-name strings, handled like CITY/STATE)
            coerced_ids = []
            for gid in group_ids:
                try:
                    coerced_ids.append(int(gid))
                except (ValueError, TypeError):
                    pass
            group_ids = coerced_ids

        return start_date, end_date, group_ids

    @staticmethod
    def _cache_filters(filters: dict, allowed_location_ids: Optional[List[int]]) -> dict:
        # allowed_location_ids must be part of the cache key, else a restricted user
        # could be served an org-wide (unrestricted) cached result.
        return {**filters, "_allowed": allowed_location_ids}

    @staticmethod
    def get_summary(db: Session, org_id: int, filters: dict, allowed_location_ids: Optional[List[int]] = None) -> Dict[str, Any]:
        group_type = filters.get("group_type", "CITY")
        cache_filters = ComparisonSnapshotService._cache_filters(filters, allowed_location_ids)

        cached = ComparisonCacheService.get_cached_comparison(
            org_id, group_type,
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters,
        )
        if cached:
            return cached

        start_date, end_date, group_ids = ComparisonSnapshotService._coerce_filters(filters, group_type)

        result = {
            "profile_views": 0, "search_impressions": 0, "website_clicks": 0,
            "phone_calls": 0, "direction_requests": 0, "avg_rating": None, "response_rate": 0.0,
        }
        params = {"org_id": org_id, "start_date": start_date, "end_date": end_date, "group_ids": group_ids}

        if group_type == "CUSTOM_GROUP":
            table_filter = "gdi.group_id = ANY(:group_ids)" if group_ids else "1=1"
            params["group_type"] = group_type
            sql = f"""
                SELECT
                    SUM(gdi.profile_views) as profile_views,
                    SUM(gdi.search_impressions) as search_impressions,
                    SUM(gdi.website_clicks) as website_clicks,
                    SUM(gdi.phone_calls) as phone_calls,
                    SUM(gdi.direction_requests) as direction_requests,
                    CASE WHEN SUM(gdi.reviews_received) > 0 THEN SUM(gdi.avg_rating * gdi.reviews_received) / SUM(gdi.reviews_received) ELSE NULL END as avg_rating,
                    CASE WHEN SUM(gdi.reviews_received) > 0 THEN SUM(gdi.response_rate * gdi.reviews_received) / SUM(gdi.reviews_received) ELSE 0.0 END as response_rate
                FROM group_daily_insights gdi
                WHERE gdi.organization_id = :org_id
                  AND gdi.group_type = :group_type
                  AND gdi.date >= :start_date AND gdi.date <= :end_date
                  AND {table_filter}
            """
        else:
            group_col = _geo_col(group_type)
            table_filter = f"{group_col} = ANY(:group_ids)" if group_ids else "1=1"
            allowed_filter = ""
            if allowed_location_ids is not None:
                allowed_filter = "AND ldi.location_id = ANY(:allowed_ids)"
                params["allowed_ids"] = allowed_location_ids
            sql = f"""
                SELECT
                    SUM(ldi.profile_views) as profile_views,
                    SUM(ldi.search_impressions) as search_impressions,
                    SUM(ldi.website_clicks) as website_clicks,
                    SUM(ldi.phone_calls) as phone_calls,
                    SUM(ldi.direction_requests) as direction_requests,
                    CASE WHEN SUM(ldi.reviews_received) > 0 THEN SUM(ldi.avg_rating * ldi.reviews_received) / SUM(ldi.reviews_received) ELSE NULL END as avg_rating,
                    CASE WHEN SUM(ldi.reviews_received) > 0 THEN SUM(ldi.response_rate * ldi.reviews_received) / SUM(ldi.reviews_received) ELSE 0.0 END as response_rate
                FROM location_daily_insights ldi
                JOIN locations l ON ldi.location_id = l.id
                WHERE ldi.organization_id = :org_id
                  AND ldi.date >= :start_date AND ldi.date <= :end_date
                  {allowed_filter}
                  AND {table_filter}
            """

        row = db.execute(text(sql), params).fetchone()
        if row:
            result = {
                "profile_views": int(row.profile_views or 0),
                "search_impressions": int(row.search_impressions or 0),
                "website_clicks": int(row.website_clicks or 0),
                "phone_calls": int(row.phone_calls or 0),
                "direction_requests": int(row.direction_requests or 0),
                "avg_rating": round(row.avg_rating, 2) if row.avg_rating is not None else None,
                "response_rate": round(row.response_rate, 2) if row.response_rate is not None else 0.0,
            }

        ComparisonCacheService.set_cached_comparison(
            org_id, group_type,
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters, result,
        )
        return result

    @staticmethod
    def get_leaderboard(db: Session, org_id: int, filters: dict, allowed_location_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        group_type = filters.get("group_type", "CITY")
        cache_filters = ComparisonSnapshotService._cache_filters(filters, allowed_location_ids)

        cached = ComparisonCacheService.get_cached_comparison(
            org_id, group_type + "_leaderboard",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters,
        )
        if cached:
            return cached

        start_date, end_date, group_ids = ComparisonSnapshotService._coerce_filters(filters, group_type)
        params = {"org_id": org_id, "start_date": start_date, "end_date": end_date, "group_ids": group_ids}
        result = []

        if group_type == "CUSTOM_GROUP":
            table_filter = "gdi.group_id = ANY(:group_ids)" if group_ids else "1=1"
            join_table = "regions" if group_type == "REGION" else "custom_groups"
            params["group_type"] = group_type
            sql = f"""
                SELECT g.name as name, COALESCE(SUM(gdi.profile_views), 0) as score
                FROM group_daily_insights gdi
                JOIN {join_table} g ON gdi.group_id = g.id
                WHERE gdi.organization_id = :org_id
                  AND gdi.group_type = :group_type
                  AND gdi.date >= :start_date AND gdi.date <= :end_date
                  AND {table_filter}
                GROUP BY g.name, gdi.group_id
                ORDER BY score DESC
                LIMIT 200
            """
        else:
            group_col = _geo_col(group_type)
            table_filter = f"{group_col} = ANY(:group_ids)" if group_ids else "1=1"
            allowed_filter = ""
            if allowed_location_ids is not None:
                allowed_filter = "AND ldi.location_id = ANY(:allowed_ids)"
                params["allowed_ids"] = allowed_location_ids
            sql = f"""
                SELECT {group_col} as name, COALESCE(SUM(ldi.profile_views), 0) as score
                FROM location_daily_insights ldi
                JOIN locations l ON ldi.location_id = l.id
                WHERE ldi.organization_id = :org_id
                  AND ldi.date >= :start_date AND ldi.date <= :end_date
                  AND {group_col} IS NOT NULL
                  {allowed_filter}
                  AND {table_filter}
                GROUP BY {group_col}
                ORDER BY score DESC
                LIMIT 200
            """

        rows = db.execute(text(sql), params).fetchall()
        result = [{"name": row.name, "score": float(row.score or 0)} for row in rows]

        ComparisonCacheService.set_cached_comparison(
            org_id, group_type + "_leaderboard",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters, result,
        )
        return result

    @staticmethod
    def get_trends(db: Session, org_id: int, filters: dict, allowed_location_ids: Optional[List[int]] = None) -> List[Dict[str, Any]]:
        group_type = filters.get("group_type", "CITY")
        cache_filters = ComparisonSnapshotService._cache_filters(filters, allowed_location_ids)

        cached = ComparisonCacheService.get_cached_comparison(
            org_id, group_type + "_trends",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters,
        )
        if cached:
            return cached

        start_date, end_date, group_ids = ComparisonSnapshotService._coerce_filters(filters, group_type)
        params = {"org_id": org_id, "start_date": start_date, "end_date": end_date, "group_ids": group_ids}
        result = []

        if group_type == "CUSTOM_GROUP":
            table_filter = "gdi.group_id = ANY(:group_ids)" if group_ids else "1=1"
            params["group_type"] = group_type
            sql = f"""
                SELECT gdi.date as date, COALESCE(SUM(gdi.profile_views), 0) as views
                FROM group_daily_insights gdi
                WHERE gdi.organization_id = :org_id
                  AND gdi.group_type = :group_type
                  AND gdi.date >= :start_date AND gdi.date <= :end_date
                  AND {table_filter}
                GROUP BY gdi.date
                ORDER BY gdi.date ASC
            """
        else:
            group_col = _geo_col(group_type)
            table_filter = f"{group_col} = ANY(:group_ids)" if group_ids else "1=1"
            allowed_filter = ""
            if allowed_location_ids is not None:
                allowed_filter = "AND ldi.location_id = ANY(:allowed_ids)"
                params["allowed_ids"] = allowed_location_ids
            sql = f"""
                SELECT ldi.date as date, COALESCE(SUM(ldi.profile_views), 0) as views
                FROM location_daily_insights ldi
                JOIN locations l ON ldi.location_id = l.id
                WHERE ldi.organization_id = :org_id
                  AND ldi.date >= :start_date AND ldi.date <= :end_date
                  {allowed_filter}
                  AND {table_filter}
                GROUP BY ldi.date
                ORDER BY ldi.date ASC
            """

        rows = db.execute(text(sql), params).fetchall()
        result = [{"date": row.date, "views": int(row.views or 0)} for row in rows]

        ComparisonCacheService.set_cached_comparison(
            org_id, group_type + "_trends",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters, result,
        )
        return result

    # ------------------------------------------------------------------ #
    # Rich per-group breakdown + multi-series for the comparison dashboard
    # ------------------------------------------------------------------ #

    @staticmethod
    def _group_rows(db, org_id, group_type, start_date, end_date, group_ids, allowed_location_ids) -> Dict[str, dict]:
        """Per-group metric rows for one window, keyed by group name."""
        params = {"org_id": org_id, "start_date": start_date, "end_date": end_date, "group_ids": group_ids}
        if group_type == "CUSTOM_GROUP":
            params["group_type"] = group_type
            join_table = "regions" if group_type == "REGION" else "custom_groups"
            link_table = "region_locations" if group_type == "REGION" else "custom_group_locations"
            link_col = "region_id" if group_type == "REGION" else "custom_group_id"
            gf = "AND gdi.group_id = ANY(:group_ids)" if group_ids else ""
            sql = f"""
                SELECT g.id::text as group_id, g.name as name,
                  (SELECT COUNT(*) FROM {link_table} ll WHERE ll.{link_col} = g.id) as locations_count,
                  AVG(gdi.avg_rank) as avg_rank, AVG(gdi.solv) as solv,
                  {_metrics_select('gdi')}
                FROM group_daily_insights gdi
                JOIN {join_table} g ON gdi.group_id = g.id
                WHERE gdi.organization_id = :org_id AND gdi.group_type = :group_type
                  AND gdi.date >= :start_date AND gdi.date <= :end_date {gf}
                GROUP BY g.id, g.name
            """
        else:
            group_col = _geo_col(group_type)
            gf = f"AND {group_col} = ANY(:group_ids)" if group_ids else ""
            af = ""
            if allowed_location_ids is not None:
                af = "AND ldi.location_id = ANY(:allowed_ids)"
                params["allowed_ids"] = allowed_location_ids
            sql = f"""
                SELECT {group_col} as group_id, {group_col} as name,
                  COUNT(DISTINCT ldi.location_id) as locations_count,
                  {_metrics_select('ldi')}
                FROM location_daily_insights ldi
                JOIN locations l ON ldi.location_id = l.id
                WHERE ldi.organization_id = :org_id
                  AND ldi.date >= :start_date AND ldi.date <= :end_date
                  AND {group_col} IS NOT NULL {af} {gf}
                GROUP BY {group_col}
            """
        rows = db.execute(text(sql), params).fetchall()
        out = {}
        for r in rows:
            out[r.name] = {
                "group_id": r.group_id, "group_name": r.name,
                "locations_count": int(r.locations_count or 0),
                **_row_metrics(r),
            }
        return out

    @staticmethod
    def get_breakdown(db, org_id, filters, allowed_location_ids=None) -> List[Dict[str, Any]]:
        group_type = filters.get("group_type", "CITY")
        cache_filters = ComparisonSnapshotService._cache_filters(filters, allowed_location_ids)
        cached = ComparisonCacheService.get_cached_comparison(
            org_id, group_type + "_breakdown",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]}, cache_filters)
        if cached:
            return cached

        start_date, end_date, group_ids = ComparisonSnapshotService._coerce_filters(filters, group_type)
        # Previous equal-length window immediately before the selected range.
        span = (end_date - start_date).days + 1
        prev_end = start_date - timedelta(days=1)
        prev_start = prev_end - timedelta(days=span - 1)

        cur = ComparisonSnapshotService._group_rows(db, org_id, group_type, start_date, end_date, group_ids, allowed_location_ids)
        prev = ComparisonSnapshotService._group_rows(db, org_id, group_type, prev_start, prev_end, group_ids, allowed_location_ids)

        result = []
        for name, row in cur.items():
            row["previous"] = {k: prev.get(name, {}).get(k) for k in _METRIC_KEYS}
            result.append(row)
        result.sort(key=lambda r: r.get("profile_views") or 0, reverse=True)

        ComparisonCacheService.set_cached_comparison(
            org_id, group_type + "_breakdown",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters, result)
        return result

    @staticmethod
    def get_series(db, org_id, filters, metric, allowed_location_ids=None) -> List[Dict[str, Any]]:
        """Multi-series: one date-line per group for the chosen metric."""
        if metric not in SERIES_METRICS:
            metric = "profile_views"
        group_type = filters.get("group_type", "CITY")
        cache_filters = {**ComparisonSnapshotService._cache_filters(filters, allowed_location_ids), "_metric": metric}
        cached = ComparisonCacheService.get_cached_comparison(
            org_id, group_type + "_series",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]}, cache_filters)
        if cached:
            return cached

        start_date, end_date, group_ids = ComparisonSnapshotService._coerce_filters(filters, group_type)
        params = {"org_id": org_id, "start_date": start_date, "end_date": end_date, "group_ids": group_ids}

        if group_type == "CUSTOM_GROUP":
            params["group_type"] = group_type
            join_table = "regions" if group_type == "REGION" else "custom_groups"
            gf = "AND gdi.group_id = ANY(:group_ids)" if group_ids else ""
            sql = f"""
                SELECT g.name as name, gdi.date as d, COALESCE(SUM(gdi.{metric}),0) as v
                FROM group_daily_insights gdi JOIN {join_table} g ON gdi.group_id = g.id
                WHERE gdi.organization_id=:org_id AND gdi.group_type=:group_type
                  AND gdi.date>=:start_date AND gdi.date<=:end_date {gf}
                GROUP BY g.name, gdi.date ORDER BY gdi.date
            """
        else:
            group_col = _geo_col(group_type)
            gf = f"AND {group_col} = ANY(:group_ids)" if group_ids else ""
            af = ""
            if allowed_location_ids is not None:
                af = "AND ldi.location_id = ANY(:allowed_ids)"
                params["allowed_ids"] = allowed_location_ids
            sql = f"""
                SELECT {group_col} as name, ldi.date as d, COALESCE(SUM(ldi.{metric}),0) as v
                FROM location_daily_insights ldi JOIN locations l ON ldi.location_id=l.id
                WHERE ldi.organization_id=:org_id AND ldi.date>=:start_date AND ldi.date<=:end_date
                  AND {group_col} IS NOT NULL {af} {gf}
                GROUP BY {group_col}, ldi.date ORDER BY ldi.date
            """
        rows = db.execute(text(sql), params).fetchall()
        groups: dict = {}
        for r in rows:
            groups.setdefault(r.name, []).append({"date": r.d.isoformat(), "value": int(r.v or 0)})
        result = [{"group_name": n, "points": pts} for n, pts in groups.items()]

        ComparisonCacheService.set_cached_comparison(
            org_id, group_type + "_series",
            {"start_date": filters["start_date"], "end_date": filters["end_date"]},
            cache_filters, result)
        return result
