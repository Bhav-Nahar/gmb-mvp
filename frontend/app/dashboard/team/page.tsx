'use client'

import { useEffect, useState } from 'react'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
import InviteMember from '@/components/InviteMember'
import { api } from '@/lib/api'
import { Users, RefreshCw, AlertTriangle, Shield, Calendar, User as UserIcon, Mail, Copy, Check } from 'lucide-react'

interface UserProfile {
  id: number
  email: string
  name: string
  avatar?: string
  role: string
  created_at: string
}

interface InviteProfile {
  id: number
  email: string
  role: string
  status: string
  created_at: string
  expires_at: string
  last_opened_at?: string
}

export default function TeamSettingsPage() {
  const [users, setUsers] = useState<UserProfile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [canManageTeam, setCanManageTeam] = useState(false)

  const [invites, setInvites] = useState<InviteProfile[]>([])
  const [invitesLoading, setInvitesLoading] = useState(false)
  const [invitesError, setInvitesError] = useState('')
  const [tempInviteUrl, setTempInviteUrl] = useState('')
  const [tempInviteCopied, setTempInviteCopied] = useState(false)

  useEffect(() => {
    // Resolve role from localStorage user profile
    const userStr = localStorage.getItem('gmb_user')
    if (userStr) {
      try {
        const profile = JSON.parse(userStr)
        const canManage = ['Owner', 'Admin', 'Regional Manager'].includes(profile.role)
        setCanManageTeam(canManage)
        if (canManage) {
           loadTeamInvites()
        }
      } catch (e) {
        console.error('Error parsing profile', e)
      }
    }

    loadTeamUsers()
  }, [])

  const loadTeamInvites = async () => {
    setInvitesLoading(true)
    setInvitesError('')
    try {
      const data = await api.get<InviteProfile[]>('/users/invites')
      setInvites(data)
    } catch (err: any) {
      setInvitesError(err.message || 'Failed to fetch pending invites.')
    } finally {
      setInvitesLoading(false)
    }
  }

  const handleRevoke = async (id: number) => {
    if (!confirm('Are you sure you want to revoke this invitation?')) return
    try {
      await api.delete(`/users/invites/${id}`)
      loadTeamInvites()
    } catch (err: any) {
      alert(err.message || 'Failed to revoke invite')
    }
  }

  const handleResend = async (id: number) => {
    try {
      const data: any = await api.post(`/users/invites/${id}/resend`)
      if (data && data.token) {
        setTempInviteUrl(`${window.location.origin}/invite/${data.token}`)
        loadTeamInvites()
      }
    } catch (err: any) {
      alert(err.message || 'Failed to resend invite')
    }
  }

  const handleCopyTempUrl = () => {
    if (tempInviteUrl) {
      navigator.clipboard.writeText(tempInviteUrl)
      setTempInviteCopied(true)
      setTimeout(() => setTempInviteCopied(false), 2000)
    }
  }

  const loadTeamUsers = async () => {
    setLoading(true)
    setError('')
    try {
      // Fetches users in active organization
      const data = await api.get<UserProfile[]>('/users/')
      setUsers(data)
    } catch (err: any) {
      setError(err.message || 'Failed to fetch team members.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-background text-white">
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
          {/* Page Title */}
          <div className="space-y-1.5">
            <h2 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <Users className="h-6 w-6 text-indigo-400" />
              Team Management
            </h2>
            <p className="text-sm text-muted-foreground">
              Manage team workspace permissions, roles, and invite new storefront administrators or staff members.
            </p>
          </div>

          {!canManageTeam ? (
            <div className="flex items-center gap-3 rounded-xl bg-amber-500/10 border border-amber-500/20 p-5 text-sm font-medium text-amber-400">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <div>
                <h4 className="font-bold text-white mb-0.5">Management Permissions Required</h4>
                <p className="text-xs text-muted-foreground/90 font-semibold leading-relaxed">
                  Only Owners, Admins, and Regional Managers have access to generate invite links or view organization personnel settings.
                </p>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
              {/* Invite Component Column */}
              <div className="lg:col-span-1 space-y-6">
                <InviteMember onInviteCreated={loadTeamInvites} />
              </div>

              {/* Members Table Column */}
              <div className="lg:col-span-2 space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                    <Users className="h-4.5 w-4.5 text-indigo-400" />
                    Workspace Personnel ({users.length})
                  </h3>
                  <button
                    onClick={loadTeamUsers}
                    disabled={loading}
                    className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-400 transition-all cursor-pointer"
                    title="Refresh Personnel"
                  >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>

                {error && (
                  <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-xs font-semibold text-red-400">
                    {error}
                  </div>
                )}

                {loading ? (
                  <div className="flex h-64 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                    <div className="flex flex-col items-center gap-2">
                      <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
                      <p className="text-xs text-muted-foreground">Syncing team directory...</p>
                    </div>
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-2xl border border-border glass-panel">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground bg-muted/10">
                          <th className="px-6 py-3.5">Name</th>
                          <th className="px-6 py-3.5">Email</th>
                          <th className="px-6 py-3.5">Role</th>
                          <th className="px-6 py-3.5">Joined Date</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40 text-xs font-medium">
                        {users.map((u) => (
                          <tr key={u.id} className="hover:bg-muted/5 transition-colors">
                            <td className="px-6 py-4 whitespace-nowrap">
                              <div className="flex items-center gap-3">
                                {u.avatar ? (
                                  <img
                                    src={u.avatar}
                                    alt={u.name}
                                    className="h-8 w-8 rounded-full border border-border"
                                    referrerPolicy="no-referrer"
                                  />
                                ) : (
                                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-muted/40 text-muted-foreground">
                                    <UserIcon className="h-4 w-4" />
                                  </div>
                                )}
                                <span className="font-bold text-white">{u.name}</span>
                              </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-muted-foreground font-semibold">
                              {u.email}
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                              <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                u.role === 'Admin' 
                                  ? 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20'
                                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              }`}>
                                <Shield className="h-3 w-3" />
                                {u.role}
                              </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-muted-foreground flex items-center gap-1.5 pt-6">
                              <Calendar className="h-3.5 w-3.5 text-muted-foreground/60" />
                              {new Date(u.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Pending Invites Section */}
                <div className="pt-8 space-y-4 border-t border-border/50">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                      <Mail className="h-4.5 w-4.5 text-indigo-400" />
                      Pending Invitations
                    </h3>
                    <button
                      onClick={loadTeamInvites}
                      disabled={invitesLoading}
                      className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-400 transition-all cursor-pointer"
                      title="Refresh Invites"
                    >
                      <RefreshCw className={`h-4 w-4 ${invitesLoading ? 'animate-spin' : ''}`} />
                    </button>
                  </div>

                  {tempInviteUrl && (
                    <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm font-bold text-indigo-400">
                          <span>Link Regenerated Successfully!</span>
                        </div>
                        <button onClick={() => setTempInviteUrl('')} className="text-xs text-muted-foreground hover:text-white cursor-pointer">Close</button>
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={tempInviteUrl}
                          className="w-full rounded-lg border border-border bg-background/70 px-3 py-2 text-xs font-mono text-white focus:outline-none"
                        />
                        <button
                          onClick={handleCopyTempUrl}
                          className="flex items-center justify-center h-9 w-9 shrink-0 rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-400 transition-colors cursor-pointer"
                          title="Copy Link"
                        >
                          {tempInviteCopied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                  )}

                  {invitesError && (
                    <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-xs font-semibold text-red-400">
                      {invitesError}
                    </div>
                  )}

                  {invitesLoading && invites.length === 0 ? (
                    <div className="flex h-32 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                      <RefreshCw className="h-5 w-5 animate-spin text-indigo-500" />
                    </div>
                  ) : invites.length === 0 ? (
                    <div className="flex h-32 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                      <p className="text-xs text-muted-foreground">No active or pending invitations.</p>
                    </div>
                  ) : (
                    <div className="overflow-x-auto rounded-2xl border border-border glass-panel">
                      <table className="w-full text-left border-collapse">
                        <thead>
                          <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground bg-muted/10">
                            <th className="px-6 py-3.5">Email</th>
                            <th className="px-6 py-3.5">Role</th>
                            <th className="px-6 py-3.5">Status</th>
                            <th className="px-6 py-3.5">Expires</th>
                            <th className="px-6 py-3.5 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40 text-xs font-medium">
                          {invites.map((inv) => (
                            <tr key={inv.id} className="hover:bg-muted/5 transition-colors">
                              <td className="px-6 py-4 whitespace-nowrap text-white font-semibold">
                                {inv.email}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-muted/20 text-muted-foreground border border-border">
                                  {inv.role}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                  inv.status === 'pending' || inv.status === 'in_progress'
                                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                                    : inv.status === 'accepted'
                                    ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                    : inv.status === 'revoked'
                                    ? 'bg-gray-500/10 text-gray-400 border border-gray-500/20'
                                    : 'bg-red-500/10 text-red-400 border border-red-500/20'
                                }`}>
                                  {inv.status === 'in_progress' ? 'In Progress' : inv.status.charAt(0).toUpperCase() + inv.status.slice(1)}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">
                                {new Date(inv.expires_at).toLocaleDateString()}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-right">
                                {inv.status !== 'accepted' && (
                                  <div className="flex items-center justify-end gap-2">
                                    <button
                                      onClick={() => handleResend(inv.id)}
                                      className="text-[10px] font-bold text-indigo-400 hover:text-indigo-300 transition-colors px-2 py-1 rounded bg-indigo-500/10 cursor-pointer"
                                    >
                                      {inv.status === 'pending' || inv.status === 'in_progress' ? 'Resend' : 'Regenerate'}
                                    </button>
                                    {(inv.status === 'pending' || inv.status === 'in_progress') && (
                                      <button
                                        onClick={() => handleRevoke(inv.id)}
                                        className="text-[10px] font-bold text-red-400 hover:text-red-300 transition-colors px-2 py-1 rounded bg-red-500/10 cursor-pointer"
                                      >
                                        Revoke
                                      </button>
                                    )}
                                  </div>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </AuthGuard>
  )
}
