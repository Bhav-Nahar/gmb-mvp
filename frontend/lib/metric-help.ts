// Plain-English explanations for the metrics and sections shown in the
// dashboard. Keyed by the exact title rendered on screen so KPI cards can look
// their own hint up — no need to thread help text through every call site.
// Deliberately not annotated `Record<string, string>` — leaving the keys inferred
// makes `METRIC_HELP['Typo']` a compile error, so tsc catches a hint that would
// otherwise silently render an empty popup. Use `helpFor()` for dynamic lookups.
export const METRIC_HELP = {
  // ---- Insights KPI cards --------------------------------------------------
  'Profile Views':
    'How many times people opened your Business Profile on Google Search or Maps. One person opening it twice counts twice.',
  'Search Impressions':
    'How many times your profile appeared in Google Search results — seen, but not necessarily clicked.',
  'Maps Views':
    'How many times your profile appeared to people browsing Google Maps.',
  'Phone Calls':
    'Taps on the "Call" button on your profile. Calls dialled manually from elsewhere are not counted.',
  'Website Clicks':
    'Taps on the website link on your profile — usually your strongest signal of buying intent.',
  'Directions Requests':
    'People who asked Google for directions to you. A good proxy for foot traffic.',
  'Avg Rating':
    'Your current star rating on Google, out of 5. This is a standing value, not a change over the period.',
  'Reviews / Day':
    'Average new reviews per day over the selected period. Steady review flow matters more to ranking than one big burst.',
  'Reviews Received': 'New reviews left on your profile during the selected period.',

  // ---- Insights sections ---------------------------------------------------
  'Growth Velocity':
    'How fast each metric is moving compared with the period just before this one. Green means it grew, red means it shrank.',
  'Traffic Acquisition':
    'Where your views came from — Google Search versus Google Maps, and on mobile versus desktop.',
  'How Customers Found You':
    'The split between people who searched for your name directly and people who found you by searching for what you sell.',
  'Period Comparison':
    'This period side by side with the one immediately before it, of the same length.',
  'Platform & Device Impressions':
    'Where your profile was shown: Google Search or Maps, and on a phone or a computer. Useful for deciding what to optimise for.',

  // ---- Search intelligence -------------------------------------------------
  'Total Impressions':
    'Every time one of your tracked keywords showed your profile in Google results, across the selected period.',
  'Branded Impressions':
    'Impressions from searches containing one of your brand terms — people who were already looking for you by name.',
  'Non-Branded (Discovery)':
    'Impressions from searches that don’t mention your name — customers finding you by category, product or service. This is the number that grows your reach.',
  'Keywords Tracked':
    'How many distinct search terms brought up your profile in this period. Google only reports keywords above a privacy threshold, so low-volume terms may be hidden.',
  'Visibility Trend':
    'Branded versus discovery impressions day by day, so you can see whether new customers are finding you or the same people are returning.',
  'Location Comparison':
    'The same branded/discovery split per location, so you can see which ones are winning discovery searches.',
  'Brand Terms':
    'The words that mark a search as "branded" — usually your business name and its common misspellings. Everything else counts as discovery.',

  // ---- Comparison page metric picker (short labels) ------------------------
  Calls: 'Taps on the "Call" button on your profile.',
  Impressions: 'How many times your profile appeared in Google Search results.',
  Reviews: 'New reviews received during the selected period.',
  Directions: 'People who asked Google for directions to you. A good proxy for foot traffic.',
  'Resp. Time (h)':
    'Average hours between a review being posted and your reply. Lower is better; under 24 hours is a healthy target.',
  CTR: 'Click-through rate — website clicks divided by profile views.',
  'Call Conv.': 'Call conversion — phone calls divided by profile views.',
  'Dir. Conv.': 'Directions conversion — directions requests divided by profile views.',
  Direct: 'Searches for your business name or address — people who already knew you.',
  Discovery: 'Searches for a category, product or service — new customers finding you.',
  Branded: 'Searches for a related brand or chain name.',
  Positive: 'Reviews our AI read as positive in tone.',
  Neutral: 'Reviews our AI read as neither positive nor negative.',
  Negative: 'Reviews our AI read as negative in tone — the ones worth replying to first.',
  Locs: 'How many locations fall into this group.',

  // ---- Health score (see backend/app/services/health_score_service.py) ------
  'Health Score':
    'A 0–100 score for how complete and well-maintained your profile is: profile fields (30 pts), reviews & rating (25), review response rate (10), posting activity (20), photos (15). 90+ is Excellent, 75+ Good, 60+ Average, 40+ Poor.',
  'Score Breakdown':
    'The five areas that make up your 100-point Health Score, and how many points each one is currently earning.',
  'Profile Strength':
    'The same Health Score, split by area so you can see where the points are being lost. Ranking, traffic, sentiment and website axes are shown for context — they are not part of the 100-point total.',

  // ---- Local rank (see backend/app/services/local_rank_service.py) ---------
  SoLV:
    'Share of Local Voice — the percentage of grid points around your address where you rank in Google’s top 3 for that keyword.',
  'Share of local voice':
    'The percentage of grid points where each business shows up in the results at all, scan by scan. Scans taken before appearance counts were recorded fall back to your top-3 share.',
  'Review lead':
    'How many more reviews you have than whichever tracked competitor has the most. A negative number means they are ahead of you.',
  'Momentum & gaps':
    'How fast each tracked competitor is gaining reviews and photos, and how far ahead or behind you they are right now.',
  'Who wins each keyword':
    'For every keyword you have scanned, the business that ranks best across the grid.',
  'Avg rank':
    'Your average position across the grid points where you were found. Points where you don’t appear at all are excluded, so a good average with a low "found" count still means poor coverage.',
  'Found in':
    'How many of the grid points you appeared in at all, out of the total scanned. Low coverage means Google isn’t showing you in parts of your own area.',
  'Grid size':
    'We search from a grid of points around your address — a 5×5 grid means 25 separate searches. Bigger grids give a finer picture and cost more scan credits.',

  // ---- AI visibility / AEO (see backend/app/services/aeo_service.py) -------
  'AI Visibility Score':
    'How often AI assistants mention your business. We run your tracked queries against each AI surface and average the percentage of queries where you appear — 0 means never mentioned, 100 means always.',
  'Tracked queries':
    'The customer-style questions we ask the AI assistants each month. Some are generated from your profile; you can add your own.',
  'Presence by AI surface':
    'For each AI assistant, the percentage of your tracked queries where its answer named your business.',
  'Per-query breakdown':
    'Query by query, which AI assistants mentioned you and roughly where you appeared in the answer.',
  'AI answer coverage':
    'How often your business is named, across every tracked query and every AI surface combined.',
  'Scan history': 'Your previous monthly scans — useful for seeing whether the score is trending up.',

  // ---- Leaderboard / compare (backend/app/core/leaderboard_config.py) ------
  Composite:
    'A single 0–100 ranking score: average rating (30%), health score (25%), review volume (15%), review velocity (15%) and response rate (15%). Locations need at least 3 reviews and 14 days of sync history to be ranked.',
  Cohort:
    'Locations are grouped by review volume so a 5-review store isn’t ranked against a 5,000-review one: Emerging (under 50), Growing (50–199), Established (200–999), Flagship (1,000+).',
  'Composite Breakdown':
    'How many of this location’s Composite points came from each input: average rating, reviews this month, profile health, total reviews and response rate.',
  'Top Performer': 'The location with the highest Composite score this period.',
  'Review Champion': 'The location that collected the most new reviews this period.',
  'Most Improved': 'The location that climbed the most rank positions since last period.',
  'Highest Rated': 'The eligible location with the highest average star rating — volume is ignored here.',

  // ---- Reviews / SLA (see backend/app/constants/sla.py) --------------------
  'Response SLA':
    'How quickly you reply to reviews, measured from when the review was posted: Best is within 12 hours, Good within 24, Average within 72. Slower than 72 hours counts as Poor.',
  'Avg Response':
    'Average hours between a review being posted and your reply. Only replied reviews are counted.',
  Overdue: 'Reviews that are still unanswered more than 72 hours after they were posted.',
  'SLA Pending':
    'Reviews across all your locations that are still waiting for a reply. Anything unanswered after 72 hours is counted as overdue.',
  'Response rate': 'Replied reviews ÷ all reviews on the profile. Deleted reviews are excluded.',
  Sentiment:
    'Positive, neutral or negative, read from the review text by AI. This is our analysis, not something Google provides.',
  Themes:
    'Recurring topics our AI found across your review text — useful for spotting what customers keep praising or complaining about.',
}

// Case-insensitive so the same concept spelled two ways on two screens
// ("Response Rate" vs "Response rate") resolves to one entry.
const BY_LOWER: Record<string, string> = Object.fromEntries(
  Object.entries(METRIC_HELP as Record<string, string>).map(([k, v]) => [k.toLowerCase(), v])
)

/** Lookup by an on-screen title that isn't known at compile time. */
export const helpFor = (title: string): string | undefined => BY_LOWER[title.toLowerCase()]
