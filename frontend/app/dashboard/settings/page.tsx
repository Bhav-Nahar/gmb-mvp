'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { BrandingSettings } from '@/components/settings/BrandingSettings'
import { Shield, AlertTriangle, User as UserIcon, Trash2, X, Building2, Mail, CalendarDays, Globe, ChevronRight, FileClock, BellRing } from 'lucide-react'

interface UserProfile {
  id: number
  email: string
  name: string
  avatar?: string
  role: string
  created_at?: string
  weekly_report_email?: boolean
  lead_email_notifications?: boolean
  organization?: {
    name: string
  }
}

interface TokenStatus {
  status: string
  google_email?: string
}

export default function SettingsPage() {
  const router = useRouter()
  const { logout } = useAuth()
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null)
  const [tokenStatus, setTokenStatus] = useState<TokenStatus | null>(null)
  const [loading, setLoading] = useState(true)

  // Delete modal
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [deleteConfirmationText, setDeleteConfirmationText] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  // Notification toggles
  const [savingPref, setSavingPref] = useState('')

  useEffect(() => {
    loadProfile()
    loadTokenStatus()
  }, [])

  const loadProfile = async () => {
    try {
      const data = await api.get<UserProfile>('/users/me')
      setUserProfile(data)
    } catch (error) {
      console.error('Failed to load profile', error)
    } finally {
      setLoading(false)
    }
  }

  const loadTokenStatus = async () => {
    try {
      const data = await api.get<TokenStatus>('/users/me/token-status')
      setTokenStatus(data)
    } catch (e) { /* non-fatal */ }
  }

  const togglePref = async (key: 'weekly_report_email' | 'lead_email_notifications') => {
    if (!userProfile || savingPref) return
    const next = !(userProfile[key] ?? true)
    setSavingPref(key)
    setUserProfile({ ...userProfile, [key]: next }) // optimistic
    try {
      await api.patch('/users/me/preferences', { [key]: next })
    } catch (e) {
      setUserProfile({ ...userProfile, [key]: !next }) // revert on failure
    } finally {
      setSavingPref('')
    }
  }

  const handleDeleteAccount = async () => {
    if (deleteConfirmationText !== 'DELETE') return
    setIsDeleting(true)
    setDeleteError('')
    try {
      await api.delete('/users/me')
      await logout()
      router.push('/login?deleted=true')
    } catch (err: any) {
      setDeleteError(err.message || 'Failed to delete account. Please try again.')
      setIsDeleting(false)
    }
  }

  const googleConnected = tokenStatus?.status === 'active' || tokenStatus?.status === 'requires_refresh'

  return (
    <div className="w-full font-sans">
      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground flex items-center gap-2">
            <UserIcon className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
            Profile
          </h1>
          <p className="mt-1.5 text-sm font-medium text-muted-foreground">Your account details and workspace.</p>
        </div>

        {/* Profile card */}
        <section className="rounded-2xl border border-border glass-panel overflow-hidden">
          {loading ? (
            <div className="animate-pulse space-y-4 p-8">
              <div className="h-20 w-20 bg-muted/40 rounded-full" />
              <div className="h-4 bg-muted/40 rounded w-1/3" />
              <div className="h-4 bg-muted/40 rounded w-1/2" />
            </div>
          ) : userProfile ? (
            <>
              {/* Identity header */}
              <div className="flex items-center gap-5 p-6 sm:p-8 border-b border-border/60">
                {userProfile.avatar ? (
                  <img src={userProfile.avatar} alt={userProfile.name} referrerPolicy="no-referrer" className="h-20 w-20 rounded-full border-2 border-border shadow-md" />
                ) : (
                  <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-border bg-muted/40 text-muted-foreground shadow-md">
                    <UserIcon className="h-10 w-10" />
                  </div>
                )}
                <div className="min-w-0">
                  <h2 className="text-xl font-bold text-foreground truncate">{userProfile.name}</h2>
                  <p className="text-sm font-medium text-muted-foreground mt-0.5 truncate">{userProfile.email}</p>
                  <span className="mt-2 inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-300 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-500/30">
                    <Shield className="h-3.5 w-3.5" />
                    {userProfile.role}
                  </span>
                </div>
              </div>

              {/* Account meta grid */}
              <dl className="grid grid-cols-1 sm:grid-cols-2 divide-y sm:divide-y-0 sm:divide-x divide-border/60">
                <MetaRow icon={Building2} label="Organization" value={userProfile.organization?.name || '—'} />
                <MetaRow icon={Mail} label="Email" value={userProfile.email} />
                <div className="border-t border-border/60 sm:col-span-2 grid grid-cols-1 sm:grid-cols-2 sm:divide-x divide-border/60">
                  <div className="flex items-start gap-3 p-5">
                    <Globe className="h-4 w-4 text-muted-foreground/70 mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <dt className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">Google Account</dt>
                      <dd className="mt-1 flex items-center gap-1.5 text-sm font-semibold text-foreground truncate">
                        <span className={`h-2 w-2 rounded-full shrink-0 ${googleConnected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                        <span className="truncate">{tokenStatus?.google_email || (googleConnected ? 'Connected' : 'Not connected')}</span>
                      </dd>
                    </div>
                  </div>
                  <MetaRow icon={CalendarDays} label="Member Since" value={userProfile.created_at ? new Date(userProfile.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' }) : '—'} />
                </div>
              </dl>
            </>
          ) : (
            <p className="text-sm text-red-600 dark:text-red-400 p-8">Failed to load profile.</p>
          )}
        </section>

        {/* Quick link to activity logs */}
        <Link href="/dashboard/settings/logs" className="flex items-center justify-between rounded-xl border border-border bg-card px-5 py-4 shadow-sm hover:border-primary/40 transition-colors group">
          <span className="flex items-center gap-3">
            <FileClock className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            <span>
              <span className="block text-sm font-bold text-foreground">Activity Logs</span>
              <span className="block text-xs text-muted-foreground">Synchronization history across all locations</span>
            </span>
          </span>
          <ChevronRight className="h-4 w-4 text-muted-foreground group-hover:text-foreground transition-colors" />
        </Link>

        {/* Notifications */}
        <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center gap-2 mb-3">
            <BellRing className="h-5 w-5 text-indigo-600 dark:text-indigo-400 shrink-0" />
            <h3 className="text-sm font-bold text-foreground">Email notifications</h3>
          </div>
          <div className="divide-y divide-border/60">
            <PrefToggle
              title="Weekly report email"
              description="A Monday summary of your Google performance — profile views, calls, new reviews and ratings."
              checked={userProfile?.weekly_report_email ?? true}
              disabled={!userProfile || savingPref !== ''}
              onToggle={() => togglePref('weekly_report_email')}
            />
            <PrefToggle
              title="New lead emails"
              description="Get an email the moment someone submits an enquiry on one of your microsites."
              checked={userProfile?.lead_email_notifications ?? true}
              disabled={!userProfile || savingPref !== ''}
              onToggle={() => togglePref('lead_email_notifications')}
            />
          </div>
        </section>

        {/* Agency white-labelling — self-hides unless is_agency */}
        <BrandingSettings />

        {/* Danger zone — compact */}
        <section className="rounded-xl border border-red-300/60 dark:border-red-500/30 bg-red-50/50 dark:bg-red-500/5 p-4 sm:p-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
              <div>
                <h4 className="text-sm font-bold text-foreground">Delete Account</h4>
                <p className="text-xs text-muted-foreground mt-0.5 max-w-md">Removes your account from this app only — your Google Business Profile data is untouched.</p>
              </div>
            </div>
            <button
              onClick={() => setIsDeleteModalOpen(true)}
              className="shrink-0 w-full sm:w-auto self-start sm:self-auto inline-flex items-center justify-center gap-1.5 rounded-lg border border-red-300 dark:border-red-500/30 bg-transparent px-3 h-11 sm:h-auto sm:py-1.5 text-xs font-bold text-red-600 dark:text-red-400 hover:bg-red-500 hover:text-white hover:border-red-500 transition-colors"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        </section>
      </main>

      {/* Delete Confirmation Modal */}
      {isDeleteModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-background/80 backdrop-blur-sm p-0 sm:p-4">
          <div className="w-full sm:w-[calc(100%-2rem)] sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl border border-red-500/30 bg-card p-6 shadow-2xl">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-xl font-bold text-foreground flex items-center gap-2">
                <AlertTriangle className="h-6 w-6 text-red-500" />
                Delete Account?
              </h3>
              <button onClick={() => { setIsDeleteModalOpen(false); setDeleteConfirmationText(''); setDeleteError('') }} className="flex h-10 w-10 sm:h-auto sm:w-auto items-center justify-center rounded-lg p-1 text-muted-foreground hover:bg-muted/20 hover:text-foreground transition-colors">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
                <p className="text-sm font-bold text-red-600 dark:text-red-400 mb-2">Warning: This action is irreversible.</p>
                <p className="text-xs text-red-600/80 dark:text-red-400/80 leading-relaxed">
                  This only deletes your account from this application. Your Google Business Profile data will NOT be deleted.
                  If you are the only Owner of the workspace, the entire workspace and all its local data will be permanently erased.
                </p>
              </div>
              {deleteError && <p className="text-sm font-bold text-red-500">{deleteError}</p>}
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                  Please type <span className="text-red-600 dark:text-red-400 select-none">DELETE</span> to confirm
                </label>
                <input
                  type="text"
                  value={deleteConfirmationText}
                  onChange={(e) => setDeleteConfirmationText(e.target.value)}
                  className="w-full h-11 sm:h-auto rounded-xl border border-border bg-background px-4 py-2.5 text-sm font-medium text-foreground placeholder-muted-foreground focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 transition-all"
                  placeholder="DELETE"
                />
              </div>
              <div className="flex gap-3 pt-4 border-t border-border/50">
                <button onClick={() => { setIsDeleteModalOpen(false); setDeleteConfirmationText(''); setDeleteError('') }} className="flex-1 rounded-xl border border-border bg-transparent px-4 h-11 sm:h-auto sm:py-2.5 text-sm font-bold text-foreground hover:bg-muted/50 transition-colors">Cancel</button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={deleteConfirmationText !== 'DELETE' || isDeleting}
                  className="flex-1 rounded-xl bg-red-500 px-4 h-11 sm:h-auto sm:py-2.5 text-sm font-bold text-white hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex justify-center items-center gap-2"
                >
                  {isDeleting ? (
                    <><div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" /> Deleting…</>
                  ) : 'Confirm Deletion'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function PrefToggle({ title, description, checked, disabled, onToggle }: { title: string; description: string; checked: boolean; disabled: boolean; onToggle: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        <p className="text-xs text-muted-foreground mt-0.5 max-w-md">{description}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={onToggle}
        disabled={disabled}
        className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${checked ? 'bg-indigo-600' : 'bg-muted-foreground/30'}`}
      >
        <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${checked ? 'translate-x-5' : 'translate-x-0.5'}`} />
      </button>
    </div>
  )
}

function MetaRow({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="flex items-start gap-3 p-5">
      <Icon className="h-4 w-4 text-muted-foreground/70 mt-0.5 shrink-0" />
      <div className="min-w-0">
        <dt className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">{label}</dt>
        <dd className="mt-1 text-sm font-semibold text-foreground truncate">{value}</dd>
      </div>
    </div>
  )
}
