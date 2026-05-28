'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
import { api } from '@/lib/api'
import { Settings, Shield, AlertTriangle, User as UserIcon, Trash2, X } from 'lucide-react'

interface UserProfile {
  id: number
  email: string
  name: string
  avatar?: string
  role: string
  organization?: {
    name: string
  }
}

export default function SettingsPage() {
  const router = useRouter()
  const [userProfile, setUserProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  
  // Modal states
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false)
  const [deleteConfirmationText, setDeleteConfirmationText] = useState('')
  const [isDeleting, setIsDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState('')

  useEffect(() => {
    loadProfile()
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

  const handleDeleteAccount = async () => {
    if (deleteConfirmationText !== 'DELETE') return
    
    setIsDeleting(true)
    setDeleteError('')
    
    try {
      await api.delete('/users/me')
      // Successfully deleted. Clear local storage and redirect.
      localStorage.removeItem('gmb_logged_in')
      localStorage.removeItem('gmb_user')
      router.push('/login?deleted=true')
    } catch (err: any) {
      setDeleteError(err.message || 'Failed to delete account. Please try again.')
      setIsDeleting(false)
    }
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-[#0A0A0B] text-foreground font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
        <Navbar />

        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center gap-3">
                <Settings className="h-8 w-8 text-indigo-400" />
                Settings
              </h1>
              <p className="mt-2 text-sm font-medium text-muted-foreground">
                Manage your account and preferences.
              </p>
            </div>
          </div>

          <div className="space-y-8 max-w-3xl">
            {/* Profile Section */}
            <section className="rounded-2xl border border-border glass-panel p-6 sm:p-8">
              <h2 className="text-lg font-bold text-white mb-6 flex items-center gap-2">
                <UserIcon className="h-5 w-5 text-indigo-400" />
                Profile Details
              </h2>
              
              {loading ? (
                <div className="animate-pulse space-y-4">
                  <div className="h-4 bg-muted/40 rounded w-1/4"></div>
                  <div className="h-4 bg-muted/40 rounded w-1/2"></div>
                  <div className="h-4 bg-muted/40 rounded w-1/3"></div>
                </div>
              ) : userProfile ? (
                <div className="space-y-6">
                  <div className="flex items-center gap-6">
                    {userProfile.avatar ? (
                      <img
                        src={userProfile.avatar}
                        alt={userProfile.name}
                        className="h-20 w-20 rounded-full border-2 border-border shadow-lg"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className="flex h-20 w-20 items-center justify-center rounded-full border-2 border-border bg-muted/40 text-muted-foreground shadow-lg">
                        <UserIcon className="h-10 w-10" />
                      </div>
                    )}
                    <div>
                      <h3 className="text-xl font-bold text-white">{userProfile.name}</h3>
                      <p className="text-sm font-medium text-muted-foreground mt-1">{userProfile.email}</p>
                      <div className="mt-2 flex items-center gap-2">
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                          <Shield className="h-3.5 w-3.5" />
                          {userProfile.role}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-red-400">Failed to load profile.</p>
              )}
            </section>

            {/* Danger Zone */}
            <section className="rounded-2xl border border-red-500/30 bg-red-500/5 p-6 sm:p-8">
              <h2 className="text-lg font-bold text-red-400 mb-2 flex items-center gap-2">
                <AlertTriangle className="h-5 w-5" />
                Danger Zone
              </h2>
              <p className="text-sm font-medium text-red-400/80 mb-6">
                Irreversible and destructive actions. Please proceed with caution.
              </p>

              <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 rounded-xl border border-red-500/20 bg-black/40 gap-4">
                <div>
                  <h4 className="font-bold text-white">Delete Account</h4>
                  <p className="text-xs text-muted-foreground mt-1 max-w-md">
                    Permanently remove your account and active sessions from this application. 
                    <br/><span className="text-red-400 font-semibold">Note: This only deletes your account from this application. Your Google Business Profile data will NOT be deleted.</span>
                  </p>
                </div>
                <button
                  onClick={() => setIsDeleteModalOpen(true)}
                  className="shrink-0 flex items-center justify-center gap-2 rounded-lg bg-red-500/10 border border-red-500/30 px-4 py-2 text-sm font-bold text-red-400 hover:bg-red-500 hover:text-white transition-all shadow-lg hover:shadow-red-500/20"
                >
                  <Trash2 className="h-4 w-4" />
                  Delete Account
                </button>
              </div>
            </section>
          </div>
        </main>

        {/* Delete Confirmation Modal */}
        {isDeleteModalOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4">
            <div className="w-full max-w-md rounded-2xl border border-red-500/30 bg-[#121214] p-6 shadow-2xl shadow-red-500/10">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-xl font-bold text-white flex items-center gap-2">
                  <AlertTriangle className="h-6 w-6 text-red-500" />
                  Delete Account?
                </h3>
                <button
                  onClick={() => {
                    setIsDeleteModalOpen(false)
                    setDeleteConfirmationText('')
                    setDeleteError('')
                  }}
                  className="rounded-lg p-1 text-muted-foreground hover:bg-white/10 hover:text-white transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-4">
                  <p className="text-sm font-bold text-red-400 mb-2">
                    Warning: This action is irreversible.
                  </p>
                  <p className="text-xs text-red-400/80 leading-relaxed">
                    This only deletes your account from this application. Your Google Business Profile data will NOT be deleted.
                    If you are the only Owner of the workspace, the entire workspace and all its local data will be permanently erased.
                  </p>
                </div>

                {deleteError && (
                  <p className="text-sm font-bold text-red-500">
                    {deleteError}
                  </p>
                )}

                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">
                    Please type <span className="text-red-400 select-none">DELETE</span> to confirm
                  </label>
                  <input
                    type="text"
                    value={deleteConfirmationText}
                    onChange={(e) => setDeleteConfirmationText(e.target.value)}
                    className="w-full rounded-xl border border-border bg-black/50 px-4 py-2.5 text-sm font-medium text-white placeholder-muted-foreground focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500 transition-all"
                    placeholder="DELETE"
                  />
                </div>

                <div className="flex gap-3 pt-4 border-t border-border/50">
                  <button
                    onClick={() => {
                      setIsDeleteModalOpen(false)
                      setDeleteConfirmationText('')
                      setDeleteError('')
                    }}
                    className="flex-1 rounded-xl border border-border bg-transparent px-4 py-2.5 text-sm font-bold text-white hover:bg-white/5 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDeleteAccount}
                    disabled={deleteConfirmationText !== 'DELETE' || isDeleting}
                    className="flex-1 rounded-xl bg-red-500 px-4 py-2.5 text-sm font-bold text-white hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex justify-center items-center gap-2"
                  >
                    {isDeleting ? (
                      <>
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></div>
                        Deleting...
                      </>
                    ) : (
                      'Confirm Deletion'
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AuthGuard>
  )
}
