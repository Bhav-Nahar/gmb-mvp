'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import { Mail, Shield, Send, CheckCircle2, AlertTriangle, Copy, Check } from 'lucide-react'

export default function InviteMember() {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('Staff')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [inviteUrl, setInviteUrl] = useState('')
  const [copied, setCopied] = useState(false)

  const handleInvite = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setInviteUrl('')
    setCopied(false)

    try {
      const response: any = await api.post('/users/invite', { email, role })
      if (response && response.invite_url) {
        setInviteUrl(response.invite_url)
        setEmail('')
      } else {
        throw new Error('Failed to generate invite URL')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to send invitation.')
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
            Add team members to your organization's workspace. Invited users can access GBP sync dashboards.
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Email Field */}
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

              {/* Role Field */}
              <div className="space-y-1.5">
                <label className="text-xs font-bold text-white/80" htmlFor="role">
                  Workspace Role
                </label>
                <div className="relative">
                  <Shield className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <select
                    id="role"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    className="w-full appearance-none rounded-lg border border-border bg-background/50 pl-10 pr-4 py-2 text-sm text-white focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="Staff" className="bg-background text-white">Staff (View & Sync)</option>
                    <option value="Admin" className="bg-background text-white">Admin (Full Control)</option>
                  </select>
                </div>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-all cursor-pointer shadow-lg shadow-indigo-500/10"
            >
              {loading ? (
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
              ) : (
                <Send className="h-4 w-4" />
              )}
              <span>{loading ? 'Generating Invite...' : 'Generate Invite Link'}</span>
            </button>
          </form>
        ) : (
          <div className="space-y-3 rounded-xl bg-indigo-500/5 border border-indigo-500/10 p-4">
            <div className="flex items-center gap-2 text-sm font-bold text-emerald-400">
              <CheckCircle2 className="h-5 w-5" />
              <span>Invitation Link Generated Successfully!</span>
            </div>
            
            <p className="text-xs text-muted-foreground">
              Send this secure URL to your team member. They can join your workspace by logging in with their Google account.
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
                className="flex items-center justify-center h-9 w-9 rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-400 transition-colors"
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
