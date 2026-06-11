'use client'

import { useEffect, useState, useRef } from 'react'
import { api } from '@/lib/api'
import {
  Sparkles,
  Plus,
  FileText,
  History,
  MapPin,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Search,
  Upload,
  Send,
  Loader2,
  X
} from 'lucide-react'

interface Location {
  id: number
  location_name: string
  primary_category?: string
  address?: string
  phone?: string
}

interface CampaignJob {
  id: number
  location_id: number
  status: string
  last_error?: string | null
}

interface CampaignAuditLog {
  id: number
  action: string
  previous_status?: string | null
  new_status: string
  created_at: string
}

interface Campaign {
  id: number
  name: string
  status: string
  total_locations: number
  total_pending: number
  total_published: number
  total_failed: number
  created_at: string
  jobs?: CampaignJob[]
  audit_logs?: CampaignAuditLog[]
}

export default function PostsPage(props: any) {
  const locationId = props.locationId;
  const [locations, setLocations] = useState<Location[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [campaignName, setCampaignName] = useState('')
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [ctaType, setCtaType] = useState('NONE')
  const [ctaUrl, setCtaUrl] = useState('')
  const [locationSearch, setLocationSearch] = useState('')
  const [selectedLocationIds, setSelectedLocationIds] = useState<number[]>(locationId ? [locationId] : [])

  // Media
  const [uploading, setUploading] = useState(false)
  const [mediaUrl, setMediaUrl] = useState('')
  const [mediaPayload, setMediaPayload] = useState<any>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Guard refs
  const isMounted = useRef(true)
  const campaignsLoadedOnce = useRef(false)

  // Autocomplete & Live Preview State
  const [showSuggest, setShowSuggest] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const getCityFromAddress = (address?: string, name?: string) => {
    if (!address) return name || ''
    const parts = address.split(',').map(p => p.trim())
    for (let i = 0; i < parts.length; i++) {
      if (/\b\d{5}\b/.test(parts[i]) || /\b[A-Z]{2}\s\d{5}\b/.test(parts[i])) {
        if (i > 0) return parts[i - 1]
      }
    }
    if (parts.length >= 3) return parts[parts.length - 3]
    return name || ''
  }

  const getLivePreview = () => {
    if (selectedLocationIds.length === 0) return 'Select a location to see a live preview...'
    const firstLoc = locations.find(l => l.id === selectedLocationIds[0])
    if (!firstLoc) return 'Select a location to see a live preview...'
    
    const city = getCityFromAddress(firstLoc.address, firstLoc.location_name)
    const phone = firstLoc.phone || ''
    
    return summary
      .replaceAll('{{location}}', firstLoc.location_name)
      .replaceAll('{{city}}', city)
      .replaceAll('{{phone}}', phone)
  }

  const handleSummaryChange = (val: string) => {
    setSummary(val)
    const textarea = textareaRef.current
    if (!textarea) return
    const selectionEnd = textarea.selectionEnd
    const textBeforeCursor = val.slice(0, selectionEnd)
    
    if (textBeforeCursor.endsWith('{{')) {
      setShowSuggest(true)
    } else if (!textBeforeCursor.includes('{{') || (textBeforeCursor.lastIndexOf('}}') > textBeforeCursor.lastIndexOf('{{'))) {
      setShowSuggest(false)
    }
  }

  const insertVariable = (variable: string) => {
    const textarea = textareaRef.current
    if (!textarea) return
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const textBefore = summary.slice(0, start)
    const lastOpenIndex = textBefore.lastIndexOf('{{')
    if (lastOpenIndex === -1) return
    
    const newSummary = summary.slice(0, lastOpenIndex) + `{{${variable}}}` + summary.slice(end)
    setSummary(newSummary)
    setShowSuggest(false)
    
    setTimeout(() => {
      textarea.focus()
      const newCursorPos = lastOpenIndex + variable.length + 4
      textarea.setSelectionRange(newCursorPos, newCursorPos)
    }, 10)
  }

  const handleCampaignAction = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!selectedCampaignId) return
    try {
      setSuccessAlert('')
      setErrorAlert('')
      const updated: Campaign = await api.post(`/posts/campaigns/${selectedCampaignId}/${action}`)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? updated : c))
      setSuccessAlert(`Campaign ${action}d successfully.`)
    } catch (err: any) {
      setErrorAlert(err.message || `Failed to ${action} campaign.`)
    }
  }

  // Submitting
  const [submitting, setSubmitting] = useState(false)
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')

  // Selected Campaign
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null)
  const [pollingActive, setPollingActive] = useState(false)

  useEffect(() => {
    isMounted.current = true
    loadLocations()
    if (!campaignsLoadedOnce.current) {
      campaignsLoadedOnce.current = true
      loadCampaigns()
    }
    return () => {
      isMounted.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (locationId) {
      setSelectedLocationIds([locationId])
      if (!campaignsLoadedOnce.current) {
        campaignsLoadedOnce.current = true
        loadCampaigns()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationId])

  useEffect(() => {
    if (!selectedCampaignId) {
      setPollingActive(false)
      return
    }

    // Do not start polling if the campaign is already in a terminal state
    const currentCampaign = campaigns.find(c => c.id === selectedCampaignId)
    const terminalStatuses = ['COMPLETED', 'FAILED', 'CANCELLED']
    if (currentCampaign && terminalStatuses.includes(currentCampaign.status.toUpperCase())) {
      setPollingActive(false)
      return
    }

    loadCampaignProgress()
    setPollingActive(true)
    const interval = setInterval(() => {
      const latest = campaigns.find(c => c.id === selectedCampaignId)
      if (latest && terminalStatuses.includes(latest.status.toUpperCase())) {
        clearInterval(interval)
        setPollingActive(false)
        return
      }
      loadCampaignProgress()
    }, 3000)
    return () => {
      clearInterval(interval)
      setPollingActive(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCampaignId])

  const loadLocations = async () => {
    try {
      const data = await api.get<Location[]>('/locations/')
      setLocations(data)
    } catch (e: any) {}
  }

  const loadCampaigns = async () => {
    try {
      const url = locationId ? `/posts/campaigns?size=50&location_id=${locationId}` : '/posts/campaigns?size=50'
      const data: any = await api.get(url)
      const allCampaigns = data.campaigns || []
      
      setCampaigns(allCampaigns)
      if (allCampaigns.length > 0 && !selectedCampaignId) {
        setSelectedCampaignId(allCampaigns[0].id)
      }
    } catch (e: any) {}
  }

  const loadCampaignProgress = async () => {
    if (!selectedCampaignId) return
    try {
      const updated: Campaign = await api.get(`/posts/campaigns/${selectedCampaignId}/progress`)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? updated : c))
    } catch (e) {}
  }

  const validateUrl = (url: string): boolean => {
    if (!url) return true // empty is allowed; required check is separate
    try {
      const parsed = new URL(url)
      return parsed.protocol === 'http:' || parsed.protocol === 'https:'
    } catch {
      return false
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    const file = files[0]
    if (!file.type.startsWith('image/') && !file.type.startsWith('video/')) {
      setErrorAlert('Invalid file type. Please upload an image or video file.')
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    setUploading(true)
    const formData = new FormData()
    formData.append('file', file)
    try {
      const resMedia: any = await api.post('/media/upload', formData)
      setMediaUrl(resMedia.cdn_url)
      setMediaPayload(resMedia)
    } catch (err: any) {
      setErrorAlert(err.message || 'File upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const handleRemoveMedia = () => {
    setMediaUrl('')
    setMediaPayload(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleToggleSelectAll = () => {
    if (selectedLocationIds.length === filteredLocations.length && filteredLocations.length > 0) {
      setSelectedLocationIds([])
    } else {
      setSelectedLocationIds(filteredLocations.map(l => l.id))
    }
  }

  const handleCreateCampaign = async () => {
    if (!campaignName || !summary || selectedLocationIds.length === 0) {
      setErrorAlert('Please provide a campaign name, post summary, and select at least one location.')
      return
    }
    if (ctaUrl && !validateUrl(ctaUrl)) {
      setErrorAlert('CTA URL must be a valid http or https URL.')
      return
    }
    setSubmitting(true)
    setErrorAlert('')
    setSuccessAlert('')

    try {
      // 1. Create Campaign
      const camp: any = await api.post('/posts/campaigns', {
        name: campaignName,
        total_locations: selectedLocationIds.length
      })

      // 2. Create Post
      const post: any = await api.post('/posts/draft', {
        title: title || null,
        summary,
        post_type: 'UPDATE',
        cta_type: ctaType !== 'NONE' ? ctaType : null,
        cta_url: ctaType !== 'NONE' && ctaUrl ? ctaUrl : null,
        is_bulk_post: true,
        campaign_id: camp.id
      })

      // 3. Attach Media (ONLY if mediaPayload is present)
      if (mediaPayload) {
        await api.post(`/posts/${post.id}/media`, {
          storage_provider: mediaPayload.storage_provider,
          storage_key: mediaPayload.storage_key || null,
          media_type: 'PHOTO',
          original_filename: mediaPayload.original_filename,
          mime_type: mediaPayload.mime_type,
          file_size: mediaPayload.file_size,
          width: mediaPayload.width,
          height: mediaPayload.height,
          sha256_hash: mediaPayload.sha256_hash,
          cdn_url: mediaPayload.cdn_url
        })
      }

      // 4. Launch Campaign
      await api.post(`/posts/campaigns/${camp.id}/launch`, {
        location_ids: selectedLocationIds
      })

      setSuccessAlert('Campaign launched successfully!')
      
      // Reset form
      setCampaignName('')
      setTitle('')
      setSummary('')
      setCtaType('NONE')
      setCtaUrl('')
      setMediaUrl('')
      setMediaPayload(null)
      setSelectedLocationIds(locationId ? [locationId] : [])
      
      // Close modal and refresh after a short delay
      setTimeout(() => {
        if (!isMounted.current) return
        setIsModalOpen(false)
        loadCampaigns()
        setSelectedCampaignId(camp.id)
      }, 1000)
    } catch (e: any) {
      console.error('Campaign creation error:', e)
      setErrorAlert(e.message || 'Failed to launch campaign.')
    } finally {
      setSubmitting(false)
    }
  }

  const filteredLocations = locations.filter(l => l.location_name.toLowerCase().includes(locationSearch.toLowerCase()))

  const getStatusBadge = (status: string) => {
    switch(status.toUpperCase()) {
      case 'DRAFT': return <span className="bg-gray-500/20 text-gray-400 px-2 py-1 rounded text-[10px] font-bold">Draft</span>
      case 'QUEUED':
      case 'RUNNING': return <span className="bg-yellow-500/20 text-yellow-400 px-2 py-1 rounded text-[10px] font-bold animate-pulse">Running</span>
      case 'COMPLETED': return <span className="bg-emerald-500/20 text-emerald-400 px-2 py-1 rounded text-[10px] font-bold">Completed</span>
      default: return <span className="bg-gray-500/20 text-gray-400 px-2 py-1 rounded text-[10px] font-bold">{status}</span>
    }
  }

  const selectedCampaign = campaigns.find(c => c.id === selectedCampaignId)

  return (
    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>
      <main className={locationId ? "" : "mx-auto max-w-7xl px-4 py-8 space-y-8"}>
          
          {!locationId && (<div className="flex justify-between items-center bg-card shadow-sm border border-border p-6 rounded-2xl relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-primary/5 blur-2xl"></div>
            <div>
              <h2 className="text-2xl font-bold flex items-center gap-2 text-foreground">
                <Sparkles className="h-6 w-6 text-primary" />
                Campaign Orchestrator
              </h2>
              <p className="text-muted-foreground text-sm mt-1">Manage bulk publishing campaigns across thousands of locations.</p>
            </div>
            <button
              onClick={() => setIsModalOpen(true)}
              className="bg-primary hover:bg-primary/90 px-4 py-2 rounded-lg font-bold text-sm text-primary-foreground flex items-center gap-2 transition-colors cursor-pointer"
            >
              <Plus className="h-4 w-4" /> New Campaign
            </button>
          </div>

          )}

          {locationId && (
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold flex items-center gap-2 text-foreground">
                <FileText className="h-5 w-5 text-primary" />
                Location Posts
              </h2>
              <button
                onClick={() => setIsModalOpen(true)}
                className="bg-primary hover:bg-primary/90 px-4 py-2 rounded-lg font-bold text-sm text-primary-foreground flex items-center gap-2 transition-colors cursor-pointer"
              >
                <Plus className="h-4 w-4" /> New Post
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-1 bg-card shadow-sm border border-border rounded-2xl p-5 h-fit">
              <h3 className="text-sm font-bold uppercase text-muted-foreground mb-4 flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" /> Campaigns
              </h3>
              <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
                {campaigns.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center">No campaigns yet. Create one!</p>
                ) : (
                  campaigns.map(c => (
                    <button
                      key={c.id}
                      onClick={() => setSelectedCampaignId(c.id)}
                      className={`w-full text-left p-4 rounded-xl border transition-all cursor-pointer ${selectedCampaignId === c.id ? 'bg-primary/5 border-primary/30' : 'bg-background border-border/40 hover:bg-muted/30 hover:border-border/80 text-foreground'}`}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-bold truncate text-sm">{c.name}</span>
                        {getStatusBadge(c.status)}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        Locations: {c.total_locations}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>

            <div className="lg:col-span-2 space-y-6">
              {selectedCampaign ? (
                <div className="bg-card shadow-sm border border-border rounded-2xl p-6">
                  <div className="flex justify-between items-center mb-6">
                    <h3 className="text-lg font-bold flex items-center gap-2 text-foreground">
                      <History className="w-5 h-5 text-primary" /> Campaign Progress Monitor
                    </h3>
                    <div className="flex items-center gap-2">
                      {['QUEUED', 'PROCESSING'].includes(selectedCampaign.status.toUpperCase()) && (
                        <button
                          onClick={() => handleCampaignAction('pause')}
                          className="bg-amber-600 hover:bg-amber-700 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer"
                        >
                          Pause
                        </button>
                      )}
                      {selectedCampaign.status.toUpperCase() === 'PAUSED' && (
                        <button
                          onClick={() => handleCampaignAction('resume')}
                          className="bg-primary hover:bg-primary/90 text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer"
                        >
                          Resume
                        </button>
                      )}
                      {['QUEUED', 'PROCESSING', 'PAUSED'].includes(selectedCampaign.status.toUpperCase()) && (
                        <button
                          onClick={() => handleCampaignAction('cancel')}
                          className="bg-red-600/80 hover:bg-red-500 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer"
                        >
                          Cancel
                        </button>
                      )}
                      {pollingActive && <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping ml-2"></span>}
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-4 gap-4 mb-8">
                    <div className="bg-muted/30 p-4 rounded-xl border border-border text-center">
                      <div className="text-2xl font-bold text-foreground">{selectedCampaign.total_locations}</div>
                      <div className="text-xs text-muted-foreground uppercase mt-1">Total</div>
                    </div>
                    <div className="bg-emerald-500/10 p-4 rounded-xl border border-emerald-500/20 text-center">
                      <div className="text-2xl font-bold text-emerald-400">{selectedCampaign.total_published}</div>
                      <div className="text-xs text-emerald-500/70 uppercase mt-1">Published</div>
                    </div>
                    <div className="bg-yellow-500/10 p-4 rounded-xl border border-yellow-500/20 text-center">
                      <div className="text-2xl font-bold text-yellow-400">{selectedCampaign.total_pending}</div>
                      <div className="text-xs text-yellow-500/70 uppercase mt-1">Pending</div>
                    </div>
                    <div className="bg-red-500/10 p-4 rounded-xl border border-red-500/20 text-center">
                      <div className="text-2xl font-bold text-red-400">{selectedCampaign.total_failed}</div>
                      <div className="text-xs text-red-500/70 uppercase mt-1">Failed</div>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <div className="flex justify-between text-xs font-bold text-muted-foreground">
                      <span>Publishing Progress</span>
                      <span>{Math.round((selectedCampaign.total_published / (selectedCampaign.total_locations || 1)) * 100)}%</span>
                    </div>
                    <div className="h-3 w-full bg-muted rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-primary transition-all duration-500" 
                        style={{ width: `${(selectedCampaign.total_published / (selectedCampaign.total_locations || 1)) * 100}%` }}
                      ></div>
                    </div>
                  </div>

                  {selectedCampaign.jobs && selectedCampaign.jobs.filter((j: CampaignJob) => j.status === 'FAILED').length > 0 && (
                    <div className="mt-8">
                      <h4 className="text-sm font-bold text-red-400 uppercase mb-3 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4" /> Failed Locations
                      </h4>
                      <div className="bg-background border border-border rounded-xl overflow-hidden">
                        <table className="w-full text-sm text-left">
                          <thead className="bg-muted text-xs uppercase text-muted-foreground">
                            <tr>
                              <th className="px-4 py-3">Location ID</th>
                              <th className="px-4 py-3">Error Reason</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedCampaign.jobs.filter((j: CampaignJob) => j.status === 'FAILED').map((job: CampaignJob) => (
                              <tr key={job.id} className="border-t border-border">
                                <td className="px-4 py-3 font-medium text-foreground">{locations.find(l => l.id === job.location_id)?.location_name || job.location_id}</td>
                                <td className="px-4 py-3 text-red-600 font-mono text-xs">{job.last_error || 'Unknown error'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {selectedCampaign.audit_logs && selectedCampaign.audit_logs.length > 0 && (
                    <div className="mt-8">
                      <h4 className="text-sm font-bold text-muted-foreground uppercase mb-3 flex items-center gap-2">
                        <FileText className="w-4 h-4" /> Audit Logs
                      </h4>
                      <div className="bg-background border border-border rounded-xl overflow-hidden max-h-[250px] overflow-y-auto">
                        <table className="w-full text-sm text-left">
                          <thead className="bg-muted text-xs uppercase text-muted-foreground sticky top-0 backdrop-blur-md">
                            <tr>
                              <th className="px-4 py-3">Action</th>
                              <th className="px-4 py-3">Status Change</th>
                              <th className="px-4 py-3">Timestamp</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selectedCampaign.audit_logs.map((log: CampaignAuditLog) => (
                              <tr key={log.id} className="border-t border-border hover:bg-muted/50 transition-colors">
                                <td className="px-4 py-3 font-medium text-foreground uppercase text-xs">{log.action}</td>
                                <td className="px-4 py-3 text-muted-foreground">
                                  {log.previous_status ? <span className="line-through opacity-50 mr-2">{log.previous_status}</span> : null}
                                  <span className="text-primary font-bold">{log.new_status}</span>
                                </td>
                                <td className="px-4 py-3 text-muted-foreground text-xs">{new Date(log.created_at).toLocaleString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                </div>
              ) : (
                <div className="bg-card shadow-sm border border-border rounded-2xl p-12 text-center text-muted-foreground">
                  Select a campaign to view the live monitor
                </div>
              )}
            </div>
          </div>
        </main>

        {isModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <div className="bg-background border border-border rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-y-auto shadow-2xl flex flex-col relative">
              <div className="p-5 flex justify-between items-center border-b border-border sticky top-0 bg-background/95 backdrop-blur z-10">
                <h3 className="text-lg font-bold text-foreground flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary" /> New Multi-Location Campaign
                </h3>
                <button onClick={() => setIsModalOpen(false)} className="text-muted-foreground hover:text-foreground cursor-pointer">
                  <X className="w-5 h-5" />
                </button>
              </div>

              <div className="p-6 space-y-8 flex-1 overflow-y-auto">
                {errorAlert && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-medium rounded-lg">{errorAlert}</div>}
                
                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-muted-foreground uppercase border-b border-border pb-2">1. Campaign Details</h4>
                  <input type="text" placeholder="Campaign Name (e.g. Summer Sale)" value={campaignName} onChange={e => setCampaignName(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors" />
                  <input type="text" placeholder="Post Title (Optional)" value={title} onChange={e => setTitle(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors" />
                  
                  <div className="relative">
                    <textarea
                      ref={textareaRef}
                      rows={4}
                      placeholder="Post Body... Use {{location}}, {{city}}, {{phone}}"
                      value={summary}
                      onChange={e => handleSummaryChange(e.target.value)}
                      className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors"
                    />
                    {showSuggest && (
                      <div className="absolute left-3 bottom-full mb-2 z-50 bg-card border border-border rounded-xl shadow-2xl p-2 w-48 space-y-1 text-sm">
                        <div className="text-[10px] text-muted-foreground uppercase px-2 py-1 font-bold">Insert Variable</div>
                        {['location', 'city', 'phone'].map((variable) => (
                          <button
                            key={variable}
                            type="button"
                            onClick={() => insertVariable(variable)}
                            className="w-full text-left px-3 py-2 rounded-lg font-mono text-xs text-foreground hover:bg-muted transition-colors cursor-pointer"
                          >
                            {`{{${variable}}}`}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* CTA Selection Controls */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <label className="text-xs font-bold uppercase text-muted-foreground">CTA Button Type</label>
                      <select
                        value={ctaType}
                        onChange={e => setCtaType(e.target.value)}
                        className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors"
                      >
                        <option value="NONE" className="bg-background">None (Text-only Post)</option>
                        <option value="LEARN_MORE" className="bg-background">Learn More</option>
                        <option value="BOOK" className="bg-background">Book</option>
                        <option value="ORDER" className="bg-background">Order Online</option>
                        <option value="SHOP" className="bg-background">Shop</option>
                        <option value="SIGN_UP" className="bg-background">Sign Up</option>
                        <option value="CALL" className="bg-background">Call Now (Uses Location Phone)</option>
                      </select>
                    </div>
                    
                    {ctaType !== 'NONE' && ctaType !== 'CALL' && (
                      <div className="space-y-1.5">
                        <label className="text-xs font-bold uppercase text-muted-foreground">CTA Destination URL</label>
                        <input
                          type="text"
                          placeholder="https://example.com/promo?loc={{location_id}}"
                          value={ctaUrl}
                          onChange={e => {
                            setCtaUrl(e.target.value)
                            if (e.target.value && !validateUrl(e.target.value)) {
                              setErrorAlert('CTA URL must be a valid http or https URL.')
                            } else {
                              setErrorAlert('')
                            }
                          }}
                          className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors"
                        />
                      </div>
                    )}
                  </div>


                  {/* Live Interpolation Preview */}
                  <div className="bg-card shadow-sm border border-border rounded-xl p-4 space-y-3">
                    <div className="text-xs font-bold uppercase text-muted-foreground flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-primary" /> Live Interpolation Preview
                    </div>
                    <div className="bg-muted/10 border border-border rounded-xl p-4 space-y-3 relative overflow-hidden shadow-inner">
                      <div className="flex items-center gap-2 mb-1">
                        <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center font-bold text-xs text-primary">
                          G
                        </div>
                        <div>
                          <div className="text-xs font-bold text-foreground flex items-center gap-1">
                            {selectedLocationIds.length > 0
                              ? locations.find(l => l.id === selectedLocationIds[0])?.location_name
                              : 'Your Location Name'}
                            <span className="text-[10px] text-primary bg-primary/10 px-1 rounded">GBP Post Preview</span>
                          </div>
                          <div className="text-[9px] text-muted-foreground">Just now</div>
                        </div>
                      </div>
                      <div className="text-xs text-foreground/80 whitespace-pre-wrap leading-relaxed">
                        {getLivePreview()}
                      </div>
                      {ctaType !== 'NONE' && (
                        <div className="pt-2">
                          <span className="inline-block bg-primary text-primary-foreground font-bold text-xs px-4 py-2 rounded-lg">
                            {ctaType === 'LEARN_MORE' ? 'Learn More' : ctaType === 'BOOK' ? 'Book' : ctaType === 'ORDER' ? 'Order' : ctaType === 'SHOP' ? 'Shop' : ctaType === 'SIGN_UP' ? 'Sign Up' : 'Call'}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                </div>

                <div className="space-y-4">
                  <h4 className="text-sm font-bold text-muted-foreground uppercase border-b border-border pb-2">2. Media</h4>
                  {mediaUrl ? (
                    <div className="flex items-center justify-between gap-4 bg-muted/30 border border-border p-4 rounded-xl">
                      <div className="flex items-center gap-4">
                        <img src={mediaUrl} className="w-16 h-16 object-cover rounded-lg border border-border" />
                        <div className="text-sm text-emerald-600 font-bold flex items-center gap-1"><CheckCircle2 className="w-4 h-4"/> Validated</div>
                      </div>
                      <button onClick={handleRemoveMedia} className="p-2 text-muted-foreground hover:text-red-500 transition-colors rounded-lg hover:bg-red-500/10 cursor-pointer">
                        <XCircle className="w-5 h-5" />
                      </button>
                    </div>
                  ) : (
                    <div>
                      <input type="file" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
                      <button onClick={() => fileInputRef.current?.click()} className="flex items-center gap-2 bg-muted/30 border border-border hover:bg-muted/50 px-4 py-3 rounded-xl text-sm font-bold text-foreground transition-colors cursor-pointer">
                        {uploading ? <Loader2 className="w-4 h-4 animate-spin"/> : <Upload className="w-4 h-4 text-primary"/>} Upload Validation-Ready Image
                      </button>
                    </div>
                  )}
                </div>

                {!locationId ? (
                  <div className="space-y-4">
                    <h4 className="text-sm font-bold text-muted-foreground uppercase border-b border-border pb-2 flex justify-between items-center">
                      <span>3. Target Locations</span>
                      <div className="flex items-center gap-4">
                        <button onClick={handleToggleSelectAll} className="text-xs text-primary hover:text-primary/80 font-bold cursor-pointer transition-colors">
                          {selectedLocationIds.length === filteredLocations.length && filteredLocations.length > 0 ? 'Deselect All' : 'Select All'}
                        </button>
                        <span className="text-primary bg-primary/10 px-2 py-0.5 rounded text-xs">{selectedLocationIds.length} Selected</span>
                      </div>
                    </h4>
                    <div className="relative">
                      <Search className="w-4 h-4 absolute left-3 top-3.5 text-muted-foreground" />
                      <input type="text" placeholder="Search locations..." value={locationSearch} onChange={e => setLocationSearch(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl pl-10 p-3 text-sm focus:ring-1 focus:ring-primary outline-none transition-colors" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pr-1">
                      {filteredLocations.map(loc => (
                        <button key={loc.id} onClick={() => setSelectedLocationIds(p => p.includes(loc.id) ? p.filter(id => id !== loc.id) : [...p, loc.id])} className={`flex items-start text-left p-3 rounded-xl border transition-colors cursor-pointer ${selectedLocationIds.includes(loc.id) ? 'bg-primary/5 border-primary/50' : 'bg-background border-border hover:bg-muted/50'}`}>
                          <input type="checkbox" checked={selectedLocationIds.includes(loc.id)} readOnly className="mt-1 mr-3 rounded text-primary bg-background border-input cursor-pointer" />
                          <div>
                            <div className="text-sm font-bold text-foreground">{loc.location_name}</div>
                            <div className="text-xs text-muted-foreground truncate max-w-[200px]">{loc.address}</div>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                    <div className="space-y-2 bg-primary/5 border border-primary/20 p-4 rounded-xl">
                    <span className="text-xs font-bold text-primary uppercase tracking-wider block">Target Location</span>
                    <div className="text-sm font-bold text-foreground mt-1">
                      {locations.find(l => l.id === Number(locationId))?.location_name || `Storefront Location ID: ${locationId}`}
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">Creating this post from the storefront profile scopes it strictly to this location.</p>
                  </div>
                )}
              </div>

              <div className="p-5 border-t border-border flex justify-end gap-3 sticky bottom-0 bg-background/95 backdrop-blur z-10">
                <button onClick={() => setIsModalOpen(false)} className="px-5 py-2.5 rounded-lg text-sm font-bold bg-muted/50 text-foreground hover:bg-muted border border-border transition-colors cursor-pointer">Cancel</button>
                <button onClick={handleCreateCampaign} disabled={submitting || uploading} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm cursor-pointer">
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin"/> : <Send className="w-4 h-4"/>} Launch Campaign
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
  )
}
