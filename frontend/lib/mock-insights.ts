export function generateMockInsightsData(): any {
  const today = new Date();
  const trends = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    
    // Add some random noise for realism
    const baseViews = 450 + Math.random() * 200;
    const baseImpressions = 800 + Math.random() * 300;
    
    trends.push({
      date: d.toISOString().split('T')[0],
      profile_views: Math.floor(baseViews),
      search_impressions: Math.floor(baseImpressions),
      maps_views: Math.floor(baseViews * 0.7),
      phone_calls: Math.floor(5 + Math.random() * 15),
      website_clicks: Math.floor(20 + Math.random() * 30),
      direction_requests: Math.floor(10 + Math.random() * 20),
      searches_direct: Math.floor(baseImpressions * 0.3),
      searches_indirect: Math.floor(baseImpressions * 0.6),
      searches_chain: Math.floor(baseImpressions * 0.1),
      reviews_received: Math.floor(Math.random() * 3),
      avg_rating: 4.8,
      click_through_rate: 0.12,
      call_conversion_rate: 0.05,
      direction_conversion_rate: 0.08,
      avg_sentiment_score: 0.85
    });
  }

  return {
    kpis: {
      profile_views: { current: 14235, prior: 12100, percentage_change: 17.6 },
      search_impressions: { current: 28450, prior: 24200, percentage_change: 17.5 },
      maps_views: { current: 9964, prior: 8200, percentage_change: 21.5 },
      phone_calls: { current: 345, prior: 290, percentage_change: 18.9 },
      website_clicks: { current: 1240, prior: 1100, percentage_change: 12.7 },
      direction_requests: { current: 512, prior: 480, percentage_change: 6.6 }
    },
    trends,
    leaderboard: [
      { location_id: 1, location_name: "Downtown Flagship", profile_views: 4521, search_impressions: 8900, reviews_count: 342, avg_rating: 4.9 },
      { location_id: 2, location_name: "Westside Branch", profile_views: 3210, search_impressions: 6540, reviews_count: 215, avg_rating: 4.7 },
      { location_id: 3, location_name: "North Hills", profile_views: 2890, search_impressions: 5400, reviews_count: 189, avg_rating: 4.8 },
    ],
    attention_locations_count: 1,
    sentiment: {
      positive: 420,
      neutral: 45,
      negative: 15,
      positive_percentage: 87.5,
      neutral_percentage: 9.3,
      negative_percentage: 3.1,
      avg_sentiment_score: 0.82
    },
    sla: {
      total_reviews: 480,
      replied_reviews: 465,
      response_rate: 96.8,
      avg_response_time_hours: 2.4
    },
    top_issue_categories: [
      { category: "Wait Times", count: 8 },
      { category: "Parking", count: 5 },
      { category: "Staff Attitude", count: 2 }
    ],
    platform_device: {
      google_search_desktop: 15,
      google_search_mobile: 55,
      google_maps_desktop: 10,
      google_maps_mobile: 20
    },
    reputation: {
      avg_rating: 4.82,
      rated_location_count: 3,
      total_reviews_all_time: 480,
      review_velocity_per_day: {
        current: 0.8,
        prior: 0.6,
        percentage_change: 33.3
      },
      response_rate: 96.8
    }
  };
}
