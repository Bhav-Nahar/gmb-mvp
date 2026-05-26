'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Mail, Shield, Send, CheckCircle2, AlertTriangle, Copy, Check, MapPin, Eye } from 'lucide-react'

interface InviteMemberProps {
  onInviteCreated?: () => void;
}

export default function InviteMember({ onInviteCreated }: InviteMemberProps = {}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('Store Manager')
  const [locationIds, setLocationIds] = useState<number[]>([])
  const [viewerScope, setViewerScope] = useState('assigned')
  
  const [locations, setLocations] = useState<any[]>([])
  const [currentUserRole, setCurrentUserRole] = useState('Viewer')
  
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const userStr = localStorage.getItem('gmb_user')
    if (userStr) {
      try {
        const u = JSON.parse(userStr)
        setCurrentUserRole(u.role || 'Viewer')
        if (u.role === 'Regional Manager') {
            setRole('Store Manager')
        } else {
            setRole('Admin')
        }
      } catch (e) {}
    }
    
    // Fetch locations to allow assignment
    api.get('/locations/')
       .then((res: any) => setLocations(res))
       .catch((err) => console.error("Failed to load locations", err))
  }, [])

  const handleLocationToggle = (id: number) => {
    if (role === 'Store Manager') {
        setLocationIds([id]) // single select
    } else {
        if (locationIds.includes(id)) {
            setLocationIds(locationIds.filter(l => l !== id))
        } else {
            setLocationIds([...locationIds, id])
        }
    }
  }

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setInviteUrl('')
    setCopied(false)

    try {
      const payload: any = { email, role }
      if (['Regional Manager', 'Store Manager'].includes(role) || (role === 'Viewer' && viewerScope === 'assigned')) {
         if (locationIds.length === 0) {
             throw new Error("Please select at least one location for this role.")
         }
         payload.location_ids = locationIds
      }
      if (role === 'Viewer') {
         payload.viewer_scope = viewerScope
      }
      
      const response: any = await api.post('/users/invite', payload)
      if (response && response.invite_url) {
        setInviteUrl(response.invite_url)
        setEmail('')
        setLocationIds([])
        if (onInviteCreated) {
          onInviteCreated()
        }
      } else {
        throw new Error('Failed to generate invite URL')
      }
    } catch (err: any) {
      let msg = err.message || 'Failed to send invitation.'
      if (msg.includes('already a member') || msg.includes('already registered in another organization')) {
        msg = 'User already joined workspace.'
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = () => {
    if (inviteUrl) {
      navigator.clipboard.writeText(inviteUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const canManageAllRoles = ['Owner', 'Admin'].includes(currentUserRole)

  return (
    <div className="glass-panel border border-border rounded-2xl p-6 relative overflow-hidden">
      <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-indigo-500/5 blur-2xl"></div>
      
      <div className="space-y-4">
        <div className="space-y-1">
          <h3 className="text-lg font-bold text-white tracking-tight flex items-center gap-2">
            <Mail className="h-5 w-5 text-indigo-400" />
            Invite Team Member
          </h3>
          <p className="text-xs text-muted-foreground">
            Add team members to your organization's workspace.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs font-semibold text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!inviteUrl ? (
          <form onSubmit={handleInvite} className="space-y-4">
            <div className="grid grid-cols-1 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-white/80" htmlFor="email">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input
                    id="email"
                    type="email"
                    required
                    placeholder="colleague@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full rounded-lg border border-border bg-background/50 pl-10 pr-4 py-2 text-sm text-white placeholder-muted-foreground/60 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-bold text-white/80" htmlFor="role">
                  Workspace Role
                </label>
                <div className="relative">
                  <Shield className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <select
                    id="role"
                    value={role}
                    onChange={(e) => {
                        setRole(e.target.value)
                        setLocationIds([])
                    }}
                    className="w-full appearance-none rounded-lg border border-border bg-background/50 pl-10 pr-4 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    {canManageAllRoles && <option value="Admin" className="bg-background text-white">Admin (Full Control)</option>}
                    {canManageAllRoles && <option value="Regional Manager" className="bg-background text-white">Regional Manager (Multi-location)</option>}
                    <option value="Store Manager" className="bg-background text-white">Store Manager (Single location)</option>
                    {canManageAllRoles && <option value="Viewer" className="bg-background text-white">Viewer (Read Only)</option>}
                  </select>
                </div>
              </div>
              
              {role === 'Viewer' && (
                <div className="space-y-1.5">
                  <label className="text-xs font-bold text-white/80" htmlFor="viewerScope">
                    Viewer Scope
                  </label>
                  <div className="relative">
                    <Eye className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <select
                      id="viewerScope"
                      value={viewerScope}
                      onChange={(e) => setViewerScope(e.target.value)}
                      className="w-full appearance-none rounded-lg border border-border bg-background/50 pl-10 pr-4 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="assigned" className="bg-background text-white">Assigned Locations Only</option>
                      <option value="organization" className="bg-background text-white">All Workspace Locations</option>
                    </select>
                  </div>
                </div>
              )}

              {(['Regional Manager', 'Store Manager'].includes(role) || (role === 'Viewer' && viewerScope === 'assigned')) && (
                 <div className="space-y-1.5">
                   <label className="text-xs font-bold text-white/80">
                     Assign Locations {role === 'Store Manager' && '(Select Exactly 1)'}
                   </label>
                   <div className="max-h-40 overflow-y-auto rounded-lg border border-border bg-background/50 p-2 space-y-1">
                     {locations.map(loc => (
                       <label key={loc.id} className="flex items-center gap-2 cursor-pointer hover:bg-muted/10 p-1.5 rounded">
                         <input 
                           type={role === 'Store Manager' ? "radio" : "checkbox"} 
                           name="location_assignment"
                           checked={locationIds.includes(loc.id)}
                           onChange={() => handleLocationToggle(loc.id)}
                           className="h-3.5 w-3.5 border-border bg-background text-indigo-500 focus:ring-indigo-500"
                         />
                         <div className="flex flex-col">
                           <span className="text-xs font-semibold text-white">{loc.location_name}</span>
                           <span className="text-[10px] text-muted-foreground">{loc.address}</span>
                         </div>
                       </label>
                     ))}
                     {locations.length === 0 && (
                         <div className="text-xs text-muted-foreground p-2">No locations available. Sync first.</div>
                     )}
                   </div>
                 </div>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-all cursor-pointer shadow-lg shadow-indigo-500/10"
            >
              {loading ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
              ) : (
                <Send className="h-4 w-4" />
              )}
              <span>{loading ? 'Generating...' : 'Generate Invite Link'}</span>
            </button>
          </form>
        ) : (
          <div className="space-y-3 rounded-xl bg-indigo-500/5 border border-indigo-500/10 p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
              <span>Invite Link Generated!</span>
            </div>
            
            <p className="text-xs text-muted-foreground">
              Send this URL to the new member to join the workspace.
            </p>

            <div className="flex items-center gap-2">
              <input
                type="text"
                readOnly
                value={inviteUrl}
                className="w-full rounded-lg border border-border bg-background/70 px-3 py-2 text-xs font-mono text-white focus:outline-none"
              />
              <button
                onClick={handleCopy}
                className="flex items-center justify-center h-9 w-9 shrink-0 rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-400 transition-colors"
                title="Copy Link"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>

            <button
              onClick={() => setInviteUrl('')}
              className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Invite another member
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
