import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

export interface ComparisonFilters {
  group_type: 'CITY' | 'STATE' | 'REGION' | 'CUSTOM_GROUP';
  start_date: string;
  end_date: string;
  group_ids?: string[];
}

export interface GroupRow {
  group_id: string;
  group_name: string;
  locations_count: number;
  profile_views: number;
  search_impressions: number;
  maps_views: number;
  phone_calls: number;
  website_clicks: number;
  direction_requests: number;
  reviews_received: number;
  searches_direct: number;
  searches_indirect: number;
  searches_chain: number;
  positive_review_count: number;
  neutral_review_count: number;
  negative_review_count: number;
  avg_rating: number | null;
  avg_sentiment_score: number | null;
  response_rate: number | null;
  avg_response_time_hours: number | null;
  click_through_rate: number | null;
  call_conversion_rate: number | null;
  direction_conversion_rate: number | null;
  avg_rank: number | null;
  solv: number | null;
  previous: Record<string, number | null>;
}

export interface GroupSeries {
  group_name: string;
  points: { date: string; value: number }[];
}

export interface ComparisonGroup {
  id: string;
  name: string;
}

function qs(filters: ComparisonFilters): string {
  const p = new URLSearchParams({
    group_type: filters.group_type,
    start_date: filters.start_date,
    end_date: filters.end_date,
  });
  (filters.group_ids || []).forEach(id => p.append('group_ids', id));
  return p.toString();
}

export function useComparisonDashboard(
  orgId: number | undefined,
  filters: ComparisonFilters,
  metric: string,
) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [breakdown, setBreakdown] = useState<GroupRow[]>([]);
  const [series, setSeries] = useState<GroupSeries[]>([]);
  const [availableGroups, setAvailableGroups] = useState<ComparisonGroup[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  // Bust the server-side cache, then refetch.
  const refresh = async () => {
    try { await api.post('/comparison/refresh'); } catch { /* refetch anyway */ }
    setRefreshKey(k => k + 1);
  };

  useEffect(() => {
    let mounted = true;
    async function run() {
      if (!orgId) { setLoading(false); return; }
      setLoading(true);
      setError(null);
      const q = qs(filters);
      try {
        const [b, s, g] = await Promise.all([
          api.get<GroupRow[]>(`/comparison/breakdown?${q}`),
          api.get<GroupSeries[]>(`/comparison/series?${q}&metric=${metric}`),
          api.get<ComparisonGroup[]>(`/comparison/groups?group_type=${filters.group_type}`),
        ]);
        if (mounted) { setBreakdown(b); setSeries(s); setAvailableGroups(g); }
      } catch (err: any) {
        if (mounted) setError(err.message || 'Failed to load comparison data');
      } finally {
        if (mounted) setLoading(false);
      }
    }
    run();
    return () => { mounted = false; };
    // group_ids joined to a stable string so an unchanged array doesn't refetch every render
  }, [orgId, filters.group_type, filters.start_date, filters.end_date, metric, (filters.group_ids || []).join(','), refreshKey]);

  return { loading, error, breakdown, series, availableGroups, refresh };
}
