import { useState, useEffect, useCallback } from 'react'
import { Plus, Pencil, Trash2, KeyRound, Loader2, X, Check, ShieldCheck, RefreshCw, UserPlus, AlertTriangle } from 'lucide-react'
import { cn } from '../lib/utils'
import { apiClient } from '../services/apiClient'
import { useAuthStore } from '../stores/authStore'
import { confirm } from '../stores/confirmStore'
import { useT } from '../hooks/useT'

interface UserData {
  id: number
  username: string
  display_name: string
  role: string
  brans: string
  is_active: boolean
  created_at: string
  updated_at: string
}

interface UserListResponse {
  users: UserData[]
  total: number
}

interface OpenEMRDoctor {
  openemr_id: string
  username: string
  fname: string
  lname: string
  specialty: string
  already_in_system: boolean
}

interface OpenEMRSyncResponse {
  doctors: OpenEMRDoctor[]
  new_count: number
  total_count: number
}

export function AdminPage(): React.JSX.Element {
  const [users, setUsers] = useState<UserData[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingUser, setEditingUser] = useState<UserData | null>(null)
  const [passwordUserId, setPasswordUserId] = useState<number | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [newOpenEMRDoctors, setNewOpenEMRDoctors] = useState<OpenEMRDoctor[]>([])
  const [isSyncing, setIsSyncing] = useState(false)
  const [addingDoctor, setAddingDoctor] = useState<OpenEMRDoctor | null>(null)
  const currentUser = useAuthStore((s) => s.user)
  const t = useT()

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiClient.get<UserListResponse>('/api/v1/admin/users')
      setUsers(data.users)
    } catch {
      setMessage({ type: 'error', text: t('admin_loadError') })
    } finally {
      setLoading(false)
    }
  }, [t])

  const syncOpenEMR = useCallback(async () => {
    setIsSyncing(true)
    try {
      const data = await apiClient.get<OpenEMRSyncResponse>('/api/v1/admin/openemr-doctors')
      const newDocs = data.doctors.filter((d) => !d.already_in_system)
      setNewOpenEMRDoctors(newDocs)
      if (newDocs.length === 0) {
        setMessage({ type: 'success', text: t('admin_syncSuccess') })
      }
    } catch {
      setMessage({ type: 'error', text: t('admin_syncFailed') })
    } finally {
      setIsSyncing(false)
    }
  }, [t])

  useEffect(() => {
    void fetchUsers()
    void syncOpenEMR()
  }, [fetchUsers, syncOpenEMR])

  useEffect(() => {
    if (!message) return undefined
    const timer = setTimeout(() => setMessage(null), 4000)
    return () => clearTimeout(timer)
  }, [message])

  const bransLabel = (brans: string): string => {
    if (brans === 'dahiliye') return t('admin_internalMed')
    if (brans === 'ortopedi') return t('admin_ortho')
    return '-'
  }

  const roleLabel = (role: string): string => {
    if (role === 'admin') return t('admin_role_admin')
    return t('admin_role_doctor')
  }

  return (
    <div className="flex-1 overflow-auto bg-slate-50 dark:bg-slate-900 p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-7 w-7 text-blue-600" />
            <div>
              <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">{t('admin_title')}</h1>
              <p className="text-sm text-slate-500 dark:text-slate-400">{t('admin_subtitle')}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void syncOpenEMR()}
              disabled={isSyncing}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-2 text-sm font-medium text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700/50  transition-colors disabled:opacity-50"
            >
              {isSyncing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              {t('admin_syncOpenEMR')}
            </button>
            <button
              onClick={() => {
                setShowCreateForm(true)
                setEditingUser(null)
                setPasswordUserId(null)
                setAddingDoctor(null)
              }}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 transition-colors"
            >
              <Plus className="h-4 w-4" />
              {t('admin_newUser')}
            </button>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div
            className={cn(
              'rounded-lg border px-4 py-3 text-sm',
              message.type === 'success'
                ? 'border-emerald-200 dark:border-emerald-800 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                : 'border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300'
            )}
          >
            {message.text}
          </div>
        )}

        {/* New OpenEMR Doctors Banner */}
        {newOpenEMRDoctors.length > 0 && (
          <div className="rounded-xl border-2 border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-200">
                {t('admin_newDoctorsFound', { count: newOpenEMRDoctors.length })}
              </h3>
            </div>
            <p className="text-xs text-amber-700 dark:text-amber-300">{t('admin_newDoctorsDesc')}</p>
            <div className="space-y-2">
              {newOpenEMRDoctors.map((doc) => (
                <div
                  key={doc.username}
                  className="flex items-center justify-between rounded-lg bg-white dark:bg-slate-800 border border-amber-200 dark:border-amber-800 px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <UserPlus className="h-5 w-5 text-amber-600" />
                    <div>
                      <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                        {doc.fname} {doc.lname}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {t('admin_userLabel')} <span className="font-mono">{doc.username}</span>
                        {doc.specialty && (
                          <> — {t('admin_specialtyLabel')} <span className="font-medium">{doc.specialty}</span></>
                        )}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setAddingDoctor(doc)
                      setShowCreateForm(true)
                      setEditingUser(null)
                      setPasswordUserId(null)
                    }}
                    className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 transition-colors"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    {t('admin_assignRole')}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Create Form */}
        {showCreateForm && (
          <CreateUserForm
            prefill={addingDoctor}
            onCreated={() => {
              setShowCreateForm(false)
              setAddingDoctor(null)
              setMessage({ type: 'success', text: t('admin_userCreated') })
              void fetchUsers()
              void syncOpenEMR()
            }}
            onCancel={() => {
              setShowCreateForm(false)
              setAddingDoctor(null)
            }}
          />
        )}

        {/* Edit Form */}
        {editingUser && (
          <EditUserForm
            user={editingUser}
            onUpdated={() => {
              setEditingUser(null)
              setMessage({ type: 'success', text: t('admin_userUpdated') })
              void fetchUsers()
            }}
            onCancel={() => setEditingUser(null)}
          />
        )}

        {/* Password Change Form */}
        {passwordUserId !== null && (
          <PasswordChangeForm
            userId={passwordUserId}
            username={users.find((u) => u.id === passwordUserId)?.username ?? ''}
            onChanged={() => {
              setPasswordUserId(null)
              setMessage({ type: 'success', text: t('admin_passwordChanged') })
            }}
            onCancel={() => setPasswordUserId(null)}
          />
        )}

        {/* User List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400 dark:text-slate-500" />
          </div>
        ) : (
          <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900">
                  <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">{t('admin_col_user')}</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">{t('admin_col_displayName')}</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">{t('admin_col_role')}</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600 dark:text-slate-300">{t('admin_col_specialty')}</th>
                  <th className="px-4 py-3 text-right font-medium text-slate-600 dark:text-slate-300">{t('admin_col_actions')}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-slate-50 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-700/50  dark:hover:bg-slate-800/60">
                    <td className="px-4 py-3 font-mono text-slate-800 dark:text-slate-100">{u.username}</td>
                    <td className="px-4 py-3 text-slate-700 dark:text-slate-200">{u.display_name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                          u.role === 'admin'
                            ? 'bg-purple-50 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300'
                            : 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300'
                        )}
                      >
                        {roleLabel(u.role)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {u.brans ? (
                        <span
                          className={cn(
                            'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                            u.brans === 'dahiliye'
                              ? 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300'
                              : 'bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                          )}
                        >
                          {bransLabel(u.brans)}
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-slate-500">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.username === currentUser?.username ? (
                        <span className="text-xs text-slate-400 dark:text-slate-500 italic">{t('admin_currentAccount')}</span>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => {
                              setEditingUser(u)
                              setShowCreateForm(false)
                              setPasswordUserId(null)
                            }}
                            className="rounded p-1.5 text-slate-400 dark:text-slate-500 hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:text-blue-600 transition-colors"
                            title={t('admin_edit')}
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setPasswordUserId(u.id)
                              setEditingUser(null)
                              setShowCreateForm(false)
                            }}
                            className="rounded p-1.5 text-slate-400 dark:text-slate-500 hover:bg-amber-50 dark:hover:bg-amber-900/30 hover:text-amber-600 transition-colors"
                            title={t('admin_changePassword')}
                          >
                            <KeyRound className="h-4 w-4" />
                          </button>
                          <button
                            onClick={async () => {
                              const accepted = await confirm({
                                title: t('confirm_deleteUserTitle'),
                                message: t('confirm_deleteUserMessage', { username: u.username }),
                                confirmText: t('confirm_delete'),
                                variant: 'danger',
                              })
                              if (!accepted) return
                              try {
                                await apiClient.delete(`/api/v1/admin/users/${u.id}`)
                                setMessage({ type: 'success', text: t('admin_deleted', { username: u.username }) })
                                void fetchUsers()
                              } catch {
                                setMessage({ type: 'error', text: t('admin_deleteFailed') })
                              }
                            }}
                            className="rounded p-1.5 text-slate-400 dark:text-slate-500 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-600 transition-colors"
                            title={t('admin_delete')}
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
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
  )
}

/* ---- Create User Form ---- */

function CreateUserForm({
  prefill,
  onCreated,
  onCancel,
}: {
  prefill?: OpenEMRDoctor | null
  onCreated: () => void
  onCancel: () => void
}): React.JSX.Element {
  const t = useT()
  const [username, setUsername] = useState(prefill?.username ?? '')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState(
    prefill ? `Dr. ${prefill.fname} ${prefill.lname}`.trim() : ''
  )
  const [role, setRole] = useState('doctor')
  const [brans, setBrans] = useState(() => {
    if (!prefill?.specialty) return 'dahiliye'
    const spec = prefill.specialty.toLowerCase()
    if (spec.includes('ortop')) return 'ortopedi'
    if (spec.includes('dahil') || spec.includes('internal')) return 'dahiliye'
    return 'dahiliye'
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const bransOptions = [
    { value: 'dahiliye', label: t('admin_internalMed') },
    { value: 'ortopedi', label: t('admin_ortho') },
  ]

  const roleOptions = [
    { value: 'admin', label: t('admin_role_admin') },
    { value: 'doctor', label: t('admin_role_doctor') },
  ]

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await apiClient.post('/api/v1/admin/users', {
        username,
        password,
        display_name: displayName,
        role,
        brans: role === 'admin' ? '' : brans,
      })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin_createFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-slate-200/60 dark:ring-slate-700/60 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {prefill
            ? t('admin_addOpenEMR', { name: `${prefill.fname} ${prefill.lname}` })
            : t('admin_createUser')}
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-200 ">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_username')}</label>
            <input
              type="text"
              required
              minLength={3}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder="ornek: doktor3"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_password')}</label>
            <input
              type="password"
              required
              minLength={3}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_displayName')}</label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder="Dr. Mehmet Oz"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_role')}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {roleOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {role === 'doctor' && (
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_specialty')}</label>
              <select
                value={brans}
                onChange={(e) => setBrans(e.target.value)}
                className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {bransOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          )}
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 "
          >
            {t('admin_cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            {t('admin_create')}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ---- Edit User Form ---- */

function EditUserForm({
  user,
  onUpdated,
  onCancel,
}: {
  user: UserData
  onUpdated: () => void
  onCancel: () => void
}): React.JSX.Element {
  const t = useT()
  const [displayName, setDisplayName] = useState(user.display_name)
  const [role, setRole] = useState(user.role)
  const [brans, setBrans] = useState(user.brans)
  const [isActive, setIsActive] = useState(user.is_active)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const bransOptions = [
    { value: 'dahiliye', label: t('admin_internalMed') },
    { value: 'ortopedi', label: t('admin_ortho') },
  ]

  const roleOptions = [
    { value: 'admin', label: t('admin_role_admin') },
    { value: 'doctor', label: t('admin_role_doctor') },
  ]

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await apiClient.patch(`/api/v1/admin/users/${user.id}`, {
        display_name: displayName,
        role,
        brans: role === 'admin' ? '' : brans,
        is_active: isActive,
      })
      onUpdated()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin_updateFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-blue-200 dark:ring-blue-800 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {t('admin_editUser')} <span className="font-mono text-blue-600">{user.username}</span>
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-200 ">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_displayName')}</label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_role')}</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {roleOptions.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {role === 'doctor' && (
            <div>
              <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_specialty')}</label>
              <select
                value={brans}
                onChange={(e) => setBrans(e.target.value)}
                className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {bransOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_status')}</label>
            <select
              value={isActive ? 'active' : 'inactive'}
              onChange={(e) => setIsActive(e.target.value === 'active')}
              className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              <option value="active">{t('settings_active')}</option>
              <option value="inactive">{t('settings_inactive')}</option>
            </select>
          </div>
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 "
          >
            {t('admin_cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            {t('admin_save')}
          </button>
        </div>
      </form>
    </div>
  )
}

/* ---- Password Change Form ---- */

function PasswordChangeForm({
  userId,
  username,
  onChanged,
  onCancel,
}: {
  userId: number
  username: string
  onChanged: () => void
  onCancel: () => void
}): React.JSX.Element {
  const t = useT()
  const [newPassword, setNewPassword] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      await apiClient.patch(`/api/v1/admin/users/${userId}/password`, {
        new_password: newPassword,
      })
      onChanged()
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin_passwordFailed'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white dark:bg-slate-800 shadow-sm ring-1 ring-amber-200 dark:ring-amber-800 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          {t('admin_changePasswordTitle')} <span className="font-mono text-amber-600">{username}</span>
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-200 ">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 dark:text-slate-300 mb-1">{t('admin_form_newPassword')}</label>
          <input
            type="password"
            required
            minLength={3}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-300 dark:border-slate-600 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50 "
          >
            {t('admin_cancel')}
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
            {t('admin_change')}
          </button>
        </div>
      </form>
    </div>
  )
}
