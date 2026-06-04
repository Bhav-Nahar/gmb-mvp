import sys

def process_posts_page():
    with open('app/dashboard/posts/page.tsx', 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('export default function PostsPage() {', 'export default function PostsPage({ locationId }: { locationId?: number }) {')
    
    parts = content.split('<main className="mx-auto max-w-7xl px-4 py-8 space-y-8">\n          \n          <div className="flex justify-between items-center glass-panel')
    if len(parts) == 2:
        top = parts[0] + '<main className={locationId ? "" : "mx-auto max-w-7xl px-4 py-8 space-y-8"}>\n          \n          {!locationId && (<div className="flex justify-between items-center glass-panel'
        
        middle_parts = parts[1].split('<div className="grid grid-cols-1 lg:grid-cols-3 gap-8">')
        if len(middle_parts) == 2:
            middle = middle_parts[0] + ')}<div className="grid grid-cols-1 lg:grid-cols-3 gap-8">'
            content = top + middle + middle_parts[1]
    
    new_button = ''')}

          {locationId && (
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold flex items-center gap-2 text-white">
                <FileText className="h-5 w-5 text-indigo-400" />
                Location Posts
              </h2>
              <button
                onClick={() => setIsModalOpen(true)}
                className="bg-indigo-600 hover:bg-indigo-500 px-4 py-2 rounded-lg font-bold text-sm flex items-center gap-2 transition-colors cursor-pointer"
              >
                <Plus className="h-4 w-4" /> New Post
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">'''
    content = content.replace(')}<div className="grid grid-cols-1 lg:grid-cols-3 gap-8">', new_button)
    
    content = content.replace('<AuthGuard>\n      <div className="min-h-screen bg-background text-white pb-20">\n        <Navbar />', '<AuthGuard>\n      <div className={locationId ? "pb-20" : "min-h-screen bg-background text-white pb-20"}>\n        {!locationId && <Navbar />}')
    
    with open('app/dashboard/posts/page.tsx', 'w', encoding='utf-8') as f:
        f.write(content)

def process_reviews_page():
    with open('app/dashboard/reviews/page.tsx', 'r', encoding='utf-8') as f:
        content = f.read()
    
    content = content.replace('export default function ReviewsPage() {', 'export default function ReviewsPage({ locationId }: { locationId?: number }) {')
    
    content = content.replace('<main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">\n          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">\n            <div>\n              <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">',
    '<main className={locationId ? "space-y-6" : "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8"}>\n          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">\n            {!locationId && (<div>\n              <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">')
    
    content = content.replace('<p className="text-muted-foreground mt-2">Manage and respond to Google Business Profile reviews.</p>\n            </div>', '<p className="text-muted-foreground mt-2">Manage and respond to Google Business Profile reviews.</p>\n            </div>)}')
    
    content = content.replace('<AuthGuard>\n      <div className="min-h-screen bg-background">\n        <Navbar />', '<AuthGuard>\n      <div className={locationId ? "" : "min-h-screen bg-background"}>\n        {!locationId && <Navbar />}')
    
    content = content.replace('<div className="flex flex-col gap-1.5">\n              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</label>',
    '{!locationId && (<div className="flex flex-col gap-1.5">\n              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</label>')
    
    content = content.replace('</select>\n            </div>\n\n            <div className="flex flex-col gap-1.5">\n              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sentiment</label>',
    '</select>\n            </div>)}\n\n            <div className="flex flex-col gap-1.5">\n              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sentiment</label>')
    
    with open('app/dashboard/reviews/page.tsx', 'w', encoding='utf-8') as f:
        f.write(content)

process_posts_page()
process_reviews_page()
