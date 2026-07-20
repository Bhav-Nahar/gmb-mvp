// Feature landing pages: a small fixed set of hand-written marketing pages, one per
// Pinzo capability. Content lives here as data; components/features/FeatureLanding.tsx
// renders it and app/features/[slug]/page.tsx wires metadata + JSON-LD. Root-level
// URLs (/features/{slug}) like /pricing — global English pages, no locale routing.

export interface FeatureStep { title: string; detail: string }
export interface FeatureFaq { q: string; a: string }

export interface Feature {
  slug: string
  name: string
  icon: string // lucide icon name; mapped in FeatureLanding
  badge: string
  metaTitle: string
  metaDescription: string
  h1: string
  heroSub: string
  // AEO answer block — a direct "what is X" definition.
  definition: string
  howItWorks: FeatureStep[]
  benefits: FeatureStep[]
  faqs: FeatureFaq[]
  plan: string // where it sits in pricing, shown as a soft note linking /pricing
  related: string[] // slugs of related features
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

// Claims stay safe/factual (no "rank #1 guaranteed", no "AI engines recommend you"):
// describe what the product does and the customer benefit, not ranking promises.
export const FEATURES: Feature[] = [
  {
    slug: 'ai-review-replies',
    name: 'AI Review Replies',
    icon: 'MessageSquare',
    badge: 'Reputation management',
    metaTitle: 'AI Google Review Replies | Pinzo',
    metaDescription: 'Draft professional replies to every Google review in your own tone with AI, then approve and publish from one dashboard. Auto-reply and templates for multi-location brands.',
    h1: 'Reply to every Google review with AI',
    heroSub: 'Pinzo drafts a professional, on-brand reply to each Google review in seconds. You review, edit if you want, and publish — so no customer is left without a response.',
    definition: 'AI review replies means Pinzo reads each Google review and drafts a suggested response in your business’s tone, which you approve before it publishes. It keeps every location responsive without writing each reply by hand.',
    howItWorks: [
      { title: 'Connect Google', detail: 'Securely link your Google Business Profiles with Google OAuth — no password sharing.' },
      { title: 'AI drafts a reply', detail: 'For every new review, Pinzo suggests a reply in your tone that addresses what the customer actually said.' },
      { title: 'Approve and publish', detail: 'Edit if you want, then publish. Turn on auto-reply and templates to clear the queue faster.' },
    ],
    benefits: [
      { title: 'Never miss a review', detail: 'Every review gets a timely, thoughtful response — positive or negative.' },
      { title: 'Consistent brand voice', detail: 'Replies stay on-brand across locations and team members.' },
      { title: 'Handle negatives with care', detail: 'Draft measured responses to pricing, service or delay complaints before they cost you a customer.' },
      { title: 'Save hours every week', detail: 'Approve in bulk instead of composing each reply from scratch.' },
    ],
    faqs: [
      { q: 'Can I edit the AI reply before it posts?', a: 'Yes. Every AI-drafted reply is a suggestion — you can edit it or rewrite it before publishing. Nothing posts without your approval unless you enable auto-reply.' },
      { q: 'Does it work across multiple locations?', a: 'Yes. Pinzo drafts replies for every connected Google Business Profile from one dashboard, so multi-location brands stay responsive everywhere.' },
      { q: 'Will replies sound generic?', a: 'No — replies are drafted from the specific review text and your business context, so they address what the customer actually mentioned.' },
    ],
    plan: 'Included on every plan, including Lite. Auto-reply and reply templates are on Basic and Pro.',
    related: ['local-insights', 'multi-location-gbp-management', 'gbp-audit'],
  },
  {
    slug: 'ai-search-visibility',
    name: 'AI Search Visibility',
    icon: 'Sparkles',
    badge: 'Answer Engine Optimization',
    metaTitle: 'AI Search Visibility — Get Found on ChatGPT, Gemini & Google AI | Pinzo',
    metaDescription: 'See whether ChatGPT, Google AI, Gemini and Perplexity name your business in local answers, get an AI Visibility Score, and follow clear steps to improve your presence.',
    h1: 'Be the business AI search names',
    heroSub: 'Customers now ask ChatGPT, Google AI, Gemini and Perplexity who’s best nearby. Pinzo shows whether these engines mention your business, scores your AI visibility, and tells you exactly what to improve.',
    definition: 'AI Search Visibility (also called Answer Engine Optimization) is about how often AI assistants name your business in their answers to local questions. Pinzo checks each engine, gives you an AI Visibility Score, and highlights the profile gaps holding you back.',
    howItWorks: [
      { title: 'Ask the engines', detail: 'Pinzo runs real local prompts against ChatGPT, Google AI, Gemini and Perplexity for your category and area.' },
      { title: 'Score your presence', detail: 'See where you’re named, where you’re missing, and a single AI Visibility Score to track over time.' },
      { title: 'Fix the gaps', detail: 'Get concrete recommendations — missing services, categories, content — that help engines understand your business.' },
    ],
    benefits: [
      { title: 'Know where you stand', detail: 'A clear, per-engine view of whether AI assistants mention your business.' },
      { title: 'Track it over time', detail: 'One score shows whether your AI presence is improving quarter over quarter.' },
      { title: 'Actionable, not vague', detail: 'Recommendations point at specific profile fields and content to complete.' },
      { title: 'Cover every major engine', detail: 'Google AI on Basic; ChatGPT, Gemini and Perplexity on Pro.' },
    ],
    faqs: [
      { q: 'Can anyone guarantee an AI engine will recommend my business?', a: 'No — and be wary of anyone who claims to. AI answers depend on many signals. Pinzo helps you complete the profile and content that give engines accurate context, and measures your presence so you can see progress.' },
      { q: 'Which AI engines does Pinzo check?', a: 'Google AI answers on the Basic plan, and ChatGPT, Gemini and Perplexity on Pro.' },
      { q: 'How is the AI Visibility Score calculated?', a: 'It reflects how consistently the engines name your business across relevant local prompts, combined with the completeness of the signals they rely on.' },
    ],
    plan: 'Google AI answers on Basic; full ChatGPT, Gemini and Perplexity coverage on Pro.',
    related: ['gbp-audit', 'local-rank-tracker', 'local-insights'],
  },
  {
    slug: 'local-rank-tracker',
    name: 'Local Rank Tracker',
    icon: 'Map',
    badge: 'Local SEO',
    metaTitle: 'Local Rank Tracker — Geo-Grid Google Maps Rankings | Pinzo',
    metaDescription: 'See exactly where your business ranks on Google Maps street by street with a geo-grid heatmap, and track how many keywords sit in the local top 3 over time.',
    h1: 'See where you rank, street by street',
    heroSub: 'Pinzo drops a geo-grid over your area and shows your Google Maps rank in each cell — so you know exactly where you show up for “near me” searches and where you don’t.',
    definition: 'A local rank tracker measures your position in Google Maps results from many points around your location, shown as a colour-coded heatmap. It reveals the neighbourhoods where you’re visible and the ones where competitors win.',
    howItWorks: [
      { title: 'Pick keywords and a location', detail: 'Choose the searches that matter (e.g. “jeweller near me”) for each of your locations.' },
      { title: 'Scan the geo-grid', detail: 'Pinzo checks your rank across a grid of points and paints a heatmap — green where you’re top 3, red where you’re not.' },
      { title: 'Track the trend', detail: 'Watch how many keywords climb into the local top 3 week over week as you optimize.' },
    ],
    benefits: [
      { title: 'Pinpoint weak areas', detail: 'Find the exact neighbourhoods where you’re losing visibility.' },
      { title: 'Prove progress', detail: 'A clear trend line shows optimization work paying off.' },
      { title: 'Compare locations', detail: 'See which branches rank well and which need attention.' },
      { title: 'Focus your effort', detail: 'Direct posts, photos and reviews where they’ll move the needle.' },
    ],
    faqs: [
      { q: 'What is a geo-grid?', a: 'A geo-grid is a set of points spread around your business. Pinzo checks your Google Maps rank at each point, so you see visibility across the whole area — not just from one spot.' },
      { q: 'How often does it refresh?', a: 'You can scan on demand and track the trend over time to see the impact of your optimization work.' },
      { q: 'Which plan includes rank tracking?', a: 'Local Rank geo-grid heatmaps are part of the Pro plan.' },
    ],
    plan: 'Available on the Pro plan.',
    related: ['ai-search-visibility', 'gbp-audit', 'local-insights'],
  },
  {
    slug: 'google-posts-scheduler',
    name: 'Google Posts Scheduler',
    icon: 'Calendar',
    badge: 'Content & engagement',
    metaTitle: 'Google Posts Scheduler for Multiple Locations | Pinzo',
    metaDescription: 'Plan and schedule Google Business Profile posts — offers, updates and events — across every location from one dashboard, and keep your profiles active all month.',
    h1: 'Schedule Google Posts across every location',
    heroSub: 'Plan offers, updates and events ahead of time and publish them to one or a hundred Google Business Profiles on schedule — so your profiles stay active without daily effort.',
    definition: 'A Google Posts scheduler lets you write posts in advance and set when they go live on your Google Business Profiles. It keeps profiles fresh with current offers and updates that customers see when they view your listing.',
    howItWorks: [
      { title: 'Write once', detail: 'Draft a post — an offer, a new collection, an event — with an image and a call to action.' },
      { title: 'Pick locations and time', detail: 'Choose which profiles it goes to and when it should publish.' },
      { title: 'Keep a rhythm', detail: 'Queue a month of posts so every location stays active without daily work.' },
    ],
    benefits: [
      { title: 'Stay active effortlessly', detail: 'Fresh posts keep your profile current for customers viewing your listing.' },
      { title: 'One post, every location', detail: 'Publish the same update across all branches in a click.' },
      { title: 'Plan around demand', detail: 'Schedule festive offers and seasonal campaigns in advance.' },
      { title: 'Consistent presence', detail: 'No more gaps where a profile looks abandoned.' },
    ],
    faqs: [
      { q: 'Can I post to many locations at once?', a: 'Yes. Write a post once and publish it to any set of your connected Google Business Profiles.' },
      { q: 'Can I post immediately as well as schedule?', a: 'Yes — “post now” is available on every plan; scheduling ahead is on Basic and Pro.' },
      { q: 'What should I post about?', a: 'Offers, new products or collections, events, seasonal campaigns and announcements all work well and keep your profile fresh.' },
    ],
    plan: 'Post now on every plan; scheduling ahead on Basic and Pro.',
    related: ['ai-review-replies', 'multi-location-gbp-management', 'local-insights'],
  },
  {
    slug: 'gbp-audit',
    name: 'GBP Audit & Health Score',
    icon: 'Building',
    badge: 'Diagnostics',
    metaTitle: 'Free Google Business Profile Audit & Health Score | Pinzo',
    metaDescription: 'Connect Google and get a Health Score for every location in seconds — missing services, review gaps, photo freshness and branch inconsistencies, all in one report.',
    h1: 'Audit every Google Business Profile in seconds',
    heroSub: 'Connect Google and Pinzo scores each location’s profile, then lists exactly what’s missing — services, categories, photos, review replies and branch inconsistencies — so you know what to fix first.',
    definition: 'A Google Business Profile audit checks how complete and consistent each of your listings is and turns it into a Health Score with a prioritized list of fixes. It’s the fastest way to see what’s holding a location back.',
    howItWorks: [
      { title: 'Connect Google', detail: 'Link your profiles securely with Google OAuth — the audit runs in seconds.' },
      { title: 'Get a Health Score', detail: 'Each location gets a score plus branch-wise breakdown so you can spot the weak profiles.' },
      { title: 'Fix what matters', detail: 'Work through a prioritized list: missing services, unanswered reviews, stale photos, inconsistent details.' },
    ],
    benefits: [
      { title: 'See gaps instantly', detail: 'Missing fields and review gaps surface automatically across every location.' },
      { title: 'Prioritized fixes', detail: 'Know what to do first instead of guessing.' },
      { title: 'Branch-level clarity', detail: 'Compare scores across locations to focus effort where it’s needed.' },
      { title: 'A baseline to improve', detail: 'Track the score upward as you complete the fixes.' },
    ],
    faqs: [
      { q: 'Is the audit free?', a: 'Yes — you can connect Google and run an audit to see your Health Score and gaps. No credit card required to start.' },
      { q: 'What does the Health Score measure?', a: 'Profile completeness and consistency — categories, services, photos, review responsiveness and matching business details across locations.' },
      { q: 'Does it cover every location?', a: 'Yes. You get a score per location plus a branch-wise view so multi-location brands can compare and prioritize.' },
    ],
    plan: 'Free to run when you connect Google; deeper tooling scales with Basic and Pro.',
    related: ['ai-search-visibility', 'local-rank-tracker', 'multi-location-gbp-management'],
  },
  {
    slug: 'multi-location-gbp-management',
    name: 'Multi-Location GBP Dashboard',
    icon: 'LayoutDashboard',
    badge: 'For multi-location brands',
    metaTitle: 'Multi-Location Google Business Profile Management | Pinzo',
    metaDescription: 'Manage unlimited Google Business Profiles from one dashboard — reviews, posts, audits and insights across every branch, with team members and roles.',
    h1: 'Manage every location from one dashboard',
    heroSub: 'Whether you run one storefront or a hundred, Pinzo brings every Google Business Profile into a single dashboard — reviews, posts, audits and insights — with team members and roles.',
    definition: 'Multi-location GBP management means running all of your Google Business Profiles from one place instead of logging into each listing. Pinzo centralizes reviews, posts, audits and reporting, with role-based access for your team.',
    howItWorks: [
      { title: 'Connect all locations', detail: 'Link every Google Business Profile once — Pinzo supports unlimited locations on Basic and Pro.' },
      { title: 'Work in one place', detail: 'Reply to reviews, schedule posts and run audits across branches without switching accounts.' },
      { title: 'Add your team', detail: 'Invite team members with roles so the right people manage the right locations.' },
    ],
    benefits: [
      { title: 'One login for everything', detail: 'No more juggling separate Google accounts per branch.' },
      { title: 'Consistent everywhere', detail: 'Keep details, posts and replies consistent across all locations.' },
      { title: 'Compare branches', detail: 'A leaderboard shows which locations lead and which lag.' },
      { title: 'Team roles', detail: 'Delegate safely with role-based access.' },
    ],
    faqs: [
      { q: 'How many locations can I manage?', a: 'Unlimited locations are included on the Basic and Pro plans. Lite is designed for a single storefront.' },
      { q: 'Can my team help manage profiles?', a: 'Yes — invite team members with roles on Basic and Pro so each person manages the locations they’re responsible for.' },
      { q: 'Can I compare performance across branches?', a: 'Yes. A leaderboard and comparison view rank your locations so you can see leaders and laggards at a glance.' },
    ],
    plan: 'Unlimited locations, team members and roles on Basic and Pro.',
    related: ['gbp-audit', 'local-insights', 'ai-review-replies'],
  },
  {
    slug: 'lead-capture-microsite',
    name: 'Lead-Capture Microsite',
    icon: 'Globe',
    badge: 'Convert local traffic',
    metaTitle: 'Lead-Capture Microsite for Local Businesses | Pinzo',
    metaDescription: 'Turn Google Business Profile visitors into enquiries with a fast, mobile-first microsite per location — built from your profile, with a lead form and click-to-call.',
    h1: 'Turn profile visitors into enquiries',
    heroSub: 'Pinzo builds a fast, mobile-first microsite for each location from your Google Business Profile — with your services, photos, reviews and a lead form — so visitors can enquire, call or get directions in one tap.',
    definition: 'A lead-capture microsite is a lightweight web page for a location, generated from its Google Business Profile, designed to convert visitors into calls and enquiries. It gives customers a clear next step beyond the Google listing.',
    howItWorks: [
      { title: 'Generate from your profile', detail: 'Pinzo pulls your services, photos, hours and reviews into a ready-to-publish microsite.' },
      { title: 'Add a lead form', detail: 'Visitors submit an enquiry, tap to call, or get directions — no friction.' },
      { title: 'Share the link', detail: 'Use it in your profile, ads and posts to send traffic somewhere that converts.' },
    ],
    benefits: [
      { title: 'Capture more leads', detail: 'Give visitors a clear way to enquire instead of bouncing.' },
      { title: 'Mobile-first and fast', detail: 'Built to load quickly for customers on their phones.' },
      { title: 'Always up to date', detail: 'Reflects the details, photos and reviews from your profile.' },
      { title: 'One per location', detail: 'Every branch gets its own page with its own contact details.' },
    ],
    faqs: [
      { q: 'Where does the content come from?', a: 'The microsite is generated from your Google Business Profile — services, photos, hours and reviews — so it stays consistent with your listing.' },
      { q: 'How do leads reach me?', a: 'Visitors can submit an enquiry form, tap to call, or message on WhatsApp, so enquiries come straight to you.' },
      { q: 'Which plan includes the microsite?', a: 'The lead-capture microsite is part of the Pro plan.' },
    ],
    plan: 'Available on the Pro plan.',
    related: ['ai-review-replies', 'local-insights', 'multi-location-gbp-management'],
  },
  {
    slug: 'local-insights',
    name: 'Insights & Search Intelligence',
    icon: 'BarChart2',
    badge: 'Analytics',
    metaTitle: 'Google Business Profile Insights & Search Intelligence | Pinzo',
    metaDescription: 'Track calls, direction requests, website clicks and the searches customers use to find each location — with a leaderboard to compare branches over time.',
    h1: 'See what drives calls and visits',
    heroSub: 'Pinzo turns Google Business Profile activity into clear insights — calls, direction requests, website clicks and the searches customers use to find you — so you can see what’s working across every location.',
    definition: 'Google Business Profile insights show how customers find and act on your listing: the searches they use, and the calls, directions and clicks that follow. Pinzo collects this across locations and adds a leaderboard so you can compare branches.',
    howItWorks: [
      { title: 'Connect Google', detail: 'Pinzo syncs profile activity for every connected location.' },
      { title: 'Read the signals', detail: 'See calls, direction requests, website clicks and the top search terms bringing customers in.' },
      { title: 'Compare and act', detail: 'Use the leaderboard to spot leading and lagging branches and focus your effort.' },
    ],
    benefits: [
      { title: 'Know what customers do', detail: 'Track the actions that matter — calls, directions, clicks.' },
      { title: 'Understand demand', detail: 'See the search terms customers use to find each location.' },
      { title: 'Compare branches', detail: 'A leaderboard ranks locations so you can see who leads.' },
      { title: 'Track history', detail: 'Full insights history on Basic and Pro to spot trends.' },
    ],
    faqs: [
      { q: 'What metrics does Pinzo show?', a: 'Calls, direction requests, website clicks, review trends and the search terms customers use to find each location.' },
      { q: 'Can I compare locations?', a: 'Yes — a leaderboard and comparison view rank your branches so you can see leaders and laggards.' },
      { q: 'How far back does history go?', a: 'Lite keeps 7 days of insights and top-10 search intelligence; Basic and Pro include full history and search intelligence.' },
    ],
    plan: 'Top-10 search intelligence and 7-day history on Lite; full history and intelligence on Basic and Pro.',
    related: ['local-rank-tracker', 'ai-search-visibility', 'multi-location-gbp-management'],
  },
]

export const getFeature = (slug: string): Feature | undefined => FEATURES.find((f) => f.slug === slug)
export const featureUrl = (slug: string) => `${SITE_URL}/features/${slug}`

// @graph mirroring the pSEO schema stack: Organization, SoftwareApplication, WebPage,
// BreadcrumbList (+FAQPage). Only marks up FAQs that are visible on the page.
export function buildFeatureJsonLd(f: Feature) {
  const url = featureUrl(f.slug)
  const orgId = `${SITE_URL}/#organization`
  const graph: any[] = [
    { '@type': 'Organization', '@id': orgId, name: 'Pinzo', url: SITE_URL, logo: `${SITE_URL}/logo-horizontal-3.png` },
    {
      '@type': 'SoftwareApplication', '@id': `${SITE_URL}/#software`, name: 'Pinzo', url: SITE_URL,
      applicationCategory: 'BusinessApplication', operatingSystem: 'Web', publisher: { '@id': orgId },
      offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD', description: 'Free audit, no card required. 7-day free trial — no charge today.' },
    },
    {
      '@type': 'WebPage', '@id': `${url}#webpage`, url, name: f.metaTitle, description: f.metaDescription,
      isPartOf: { '@type': 'WebSite', url: SITE_URL, name: 'Pinzo' }, about: f.name, inLanguage: 'en',
    },
    {
      '@type': 'BreadcrumbList', '@id': `${url}#breadcrumb`,
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'Features', item: `${SITE_URL}/features` },
        { '@type': 'ListItem', position: 3, name: f.name, item: url },
      ],
    },
  ]
  if (f.faqs.length > 0) {
    graph.push({
      '@type': 'FAQPage', '@id': `${url}#faq`,
      mainEntity: f.faqs.map((q) => ({ '@type': 'Question', name: q.q, acceptedAnswer: { '@type': 'Answer', text: q.a } })),
    })
  }
  return { '@context': 'https://schema.org', '@graph': graph }
}
