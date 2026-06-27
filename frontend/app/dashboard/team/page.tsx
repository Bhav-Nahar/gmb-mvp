'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import InviteMember from '@/components/InviteMember'
import { useAuth } from '@/hooks/useAuth'
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
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [tempInviteUrl, setTempInviteUrl] = useState('')
  const [tempInviteCopied, setTempInviteCopied] = useState(false)

  const canManageTeam = user ? ['Owner', 'Admin', 'Regional Manager'].includes(user.role) : false

  const {
    data: users = [],
    isLoading: loading,
    error: usersError,
  } = useQuery<UserProfile[]>({
    // Fetches users in active organization
    queryKey: ['team-users'],
    queryFn: () => api.get<UserProfile[]>('/users/'),
  })
  const error = usersError ? ((usersError as any).message || 'Failed to fetch team members.') : ''

  const {
    data: invites = [],
    isLoading: invitesLoading,
    error: invitesQueryError,
  } = useQuery<InviteProfile[]>({
    queryKey: ['team-invites'],
    queryFn: () => api.get<InviteProfile[]>('/users/invites'),
    enabled: canManageTeam,
  })
  const invitesError = invitesQueryError ? ((invitesQueryError as any).message || 'Failed to fetch pending invites.') : ''

  const loadTeamInvites = () => {
    queryClient.invalidateQueries({ queryKey: ['team-invites'] })
  }

  const loadTeamUsers = () => {
    queryClient.invalidateQueries({ queryKey: ['team-users'] })
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

  return (
    <div className="min-h-screen bg-background text-foreground">

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
          {/* Page Title */}
          <div className="space-y-1.5">
            <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
              <Users className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
              Team Management
            </h2>
            <p className="text-sm text-muted-foreground">
              Manage team workspace permissions, roles, and invite new storefront administrators or staff members.
            </p>
          </div>

          {!canManageTeam ? (
            <div className="flex items-center gap-3 rounded-xl bg-amber-500/10 border border-amber-500/20 p-5 text-sm font-medium text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <div>
                <h4 className="font-bold text-foreground mb-0.5">Management Permissions Required</h4>
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
                  <h3 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
                    <Users className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-400" />
                    Workspace Personnel ({users.length})
                  </h3>
                  <button
                    onClick={loadTeamUsers}
                    disabled={loading}
                    className="flex h-10 w-10 sm:h-8 sm:w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-600 dark:hover:text-indigo-400 transition-all cursor-pointer"
                    title="Refresh Personnel"
                  >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                  </button>
                </div>

                {error && (
                  <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-xs font-semibold text-red-600 dark:text-red-400">
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
                  <>
                    {/* Mobile stacked cards */}
                    <div className="space-y-3 sm:hidden">
                      {users.map((u) => (
                        <div key={u.id} className="rounded-2xl border border-border glass-panel p-4 space-y-3">
                          <div className="flex items-center gap-3 min-w-0">
                            {u.avatar ? (
                              <img
                                src={u.avatar}
                                alt={u.name}
                                className="h-9 w-9 rounded-full border border-border shrink-0"
                                referrerPolicy="no-referrer"
                              />
                            ) : (
                              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-muted/40 text-muted-foreground">
                                <UserIcon className="h-4 w-4" />
                              </div>
                            )}
                            <div className="min-w-0">
                              <p className="text-sm font-bold text-foreground truncate">{u.name}</p>
                              <p className="text-xs text-muted-foreground font-semibold truncate">{u.email}</p>
                            </div>
                          </div>
                          <div className="flex items-center justify-between gap-2 text-xs">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${
                              u.role === 'Admin'
                                ? 'bg-indigo-100 text-indigo-800 border border-indigo-300 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-500/30'
                                : 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                            }`}>
                              <Shield className="h-3 w-3" />
                              {u.role}
                            </span>
                            <span className="flex items-center gap-1.5 text-muted-foreground">
                              <Calendar className="h-3.5 w-3.5 text-muted-foreground/60" />
                              {new Date(u.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                            </span>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* Desktop table */}
                    <div className="hidden sm:block overflow-x-auto rounded-2xl border border-border glass-panel">
                      <table className="hidden sm:table w-full text-left border-collapse">
                        <thead>
                          <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground bg-muted/10">
                            <th className="px-4 sm:px-6 py-3.5">Name</th>
                            <th className="px-4 sm:px-6 py-3.5">Email</th>
                            <th className="px-4 sm:px-6 py-3.5">Role</th>
                            <th className="px-4 sm:px-6 py-3.5">Joined Date</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/40 text-xs font-medium">
                          {users.map((u) => (
                            <tr key={u.id} className="hover:bg-muted/5 transition-colors">
                              <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
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
                                  <span className="font-bold text-foreground">{u.name}</span>
                                </div>
                              </td>
                              <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-muted-foreground font-semibold">
                                {u.email}
                              </td>
                              <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                  u.role === 'Admin'
                                    ? 'bg-indigo-100 text-indigo-800 border border-indigo-300 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-500/30'
                                    : 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                                }`}>
                                  <Shield className="h-3 w-3" />
                                  {u.role}
                                </span>
                              </td>
                              <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-muted-foreground flex items-center gap-1.5 pt-6">
                                <Calendar className="h-3.5 w-3.5 text-muted-foreground/60" />
                                {new Date(u.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                {/* Pending Invites Section */}
                <div className="pt-8 space-y-4 border-t border-border/50">
                  <div className="flex items-center justify-between">
                    <h3 className="text-lg font-bold tracking-tight text-foreground flex items-center gap-2">
                      <Mail className="h-4.5 w-4.5 text-indigo-600 dark:text-indigo-400" />
                      Pending Invitations
                    </h3>
                    <button
                      onClick={loadTeamInvites}
                      disabled={invitesLoading}
                      className="flex h-10 w-10 sm:h-8 sm:w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-600 dark:hover:text-indigo-400 transition-all cursor-pointer"
                      title="Refresh Invites"
                    >
                      <RefreshCw className={`h-4 w-4 ${invitesLoading ? 'animate-spin' : ''}`} />
                    </button>
                  </div>

                  {tempInviteUrl && (
                    <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 text-sm font-bold text-indigo-600 dark:text-indigo-400">
                          <span>Link Regenerated Successfully!</span>
                        </div>
                        <button onClick={() => setTempInviteUrl('')} className="text-xs text-muted-foreground hover:text-foreground cursor-pointer">Close</button>
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          readOnly
                          value={tempInviteUrl}
                          className="w-full h-11 sm:h-auto rounded-lg border border-border bg-background/70 px-3 py-2 text-xs font-mono text-foreground focus:outline-none"
                        />
                        <button
                          onClick={handleCopyTempUrl}
                          className="flex items-center justify-center h-11 w-11 sm:h-9 sm:w-9 shrink-0 rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors cursor-pointer"
                          title="Copy Link"
                        >
                          {tempInviteCopied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                        </button>
                      </div>
                    </div>
                  )}

                  {invitesError && (
                    <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4 text-xs font-semibold text-red-600 dark:text-red-400">
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
                    <>
                      {/* Mobile stacked cards */}
                      <div className="space-y-3 sm:hidden">
                        {invites.map((inv) => (
                          <div key={inv.id} className="rounded-2xl border border-border glass-panel p-4 space-y-3">
                            <p className="text-sm font-semibold text-foreground break-all">{inv.email}</p>
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold bg-muted/20 text-muted-foreground border border-border">
                                {inv.role}
                              </span>
                              <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold ${
                                inv.status === 'pending' || inv.status === 'in_progress'
                                  ? 'bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30'
                                  : inv.status === 'accepted'
                                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                                  : inv.status === 'revoked'
                                  ? 'bg-zinc-100 text-zinc-600 border border-zinc-300 dark:bg-zinc-500/15 dark:text-zinc-400 dark:border-zinc-500/30'
                                  : 'bg-red-100 text-red-800 border border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30'
                              }`}>
                                {inv.status === 'in_progress' ? 'In Progress' : inv.status.charAt(0).toUpperCase() + inv.status.slice(1)}
                              </span>
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Expires {new Date(inv.expires_at).toLocaleDateString()}
                            </p>
                            {inv.status !== 'accepted' && (
                              <div className="flex items-center gap-2 pt-1">
                                <button
                                  onClick={() => handleResend(inv.id)}
                                  className="flex-1 flex items-center justify-center h-11 text-xs font-bold text-indigo-700 dark:text-indigo-400 hover:text-indigo-600 transition-colors px-3 rounded-lg bg-indigo-500/10 cursor-pointer"
                                >
                                  {inv.status === 'pending' || inv.status === 'in_progress' ? 'Resend' : 'Regenerate'}
                                </button>
                                {(inv.status === 'pending' || inv.status === 'in_progress') && (
                                  <button
                                    onClick={() => handleRevoke(inv.id)}
                                    className="flex-1 flex items-center justify-center h-11 text-xs font-bold text-red-700 dark:text-red-400 hover:text-red-600 transition-colors px-3 rounded-lg bg-red-500/10 cursor-pointer"
                                  >
                                    Revoke
                                  </button>
                                )}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>

                      {/* Desktop table */}
                      <div className="hidden sm:block overflow-x-auto rounded-2xl border border-border glass-panel">
                        <table className="hidden sm:table w-full text-left border-collapse">
                          <thead>
                            <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground bg-muted/10">
                              <th className="px-4 sm:px-6 py-3.5">Email</th>
                              <th className="px-4 sm:px-6 py-3.5">Role</th>
                              <th className="px-4 sm:px-6 py-3.5">Status</th>
                              <th className="px-4 sm:px-6 py-3.5">Expires</th>
                              <th className="px-4 sm:px-6 py-3.5 text-right">Actions</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-border/40 text-xs font-medium">
                            {invites.map((inv) => (
                              <tr key={inv.id} className="hover:bg-muted/5 transition-colors">
                                <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-foreground font-semibold">
                                  {inv.email}
                                </td>
                                <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                                  <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-muted/20 text-muted-foreground border border-border">
                                    {inv.role}
                                  </span>
                                </td>
                                <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                                  <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                                    inv.status === 'pending' || inv.status === 'in_progress'
                                      ? 'bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30'
                                      : inv.status === 'accepted'
                                      ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
                                      : inv.status === 'revoked'
                                      ? 'bg-zinc-100 text-zinc-600 border border-zinc-300 dark:bg-zinc-500/15 dark:text-zinc-400 dark:border-zinc-500/30'
                                      : 'bg-red-100 text-red-800 border border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30'
                                  }`}>
                                    {inv.status === 'in_progress' ? 'In Progress' : inv.status.charAt(0).toUpperCase() + inv.status.slice(1)}
                                  </span>
                                </td>
                                <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-muted-foreground">
                                  {new Date(inv.expires_at).toLocaleDateString()}
                                </td>
                                <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-right">
                                  {inv.status !== 'accepted' && (
                                    <div className="flex items-center justify-end gap-2">
                                      <button
                                        onClick={() => handleResend(inv.id)}
                                        className="text-[10px] font-bold text-indigo-700 dark:text-indigo-400 hover:text-indigo-600 transition-colors px-2 py-1 rounded bg-indigo-500/10 cursor-pointer"
                                      >
                                        {inv.status === 'pending' || inv.status === 'in_progress' ? 'Resend' : 'Regenerate'}
                                      </button>
                                      {(inv.status === 'pending' || inv.status === 'in_progress') && (
                                        <button
                                          onClick={() => handleRevoke(inv.id)}
                                          className="text-[10px] font-bold text-red-700 dark:text-red-400 hover:text-red-600 transition-colors px-2 py-1 rounded bg-red-500/10 cursor-pointer"
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
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
  )
}
