import { useState, useEffect, useCallback } from 'react'
import { Users, Plus, Pencil, Trash2, KeyRound, Loader2, X, Check, ShieldCheck, RotateCcw, RefreshCw, UserPlus, AlertTriangle } from 'lucide-react'
import { cn } from '../lib/utils'
import { apiClient } from '../services/apiClient'
import { useAuthStore } from '../stores/authStore'

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

const BRANS_OPTIONS = [
  { value: '', label: 'Yok (Admin)' },
  { value: 'dahiliye', label: 'Dahiliye' },
  { value: 'ortopedi', label: 'Ortopedi' },
]

const ROLE_OPTIONS = [
  { value: 'admin', label: 'Admin' },
  { value: 'doctor', label: 'Doktor' },
]

function bransLabel(brans: string): string {
  if (brans === 'dahiliye') return 'Dahiliye'
  if (brans === 'ortopedi') return 'Ortopedi'
  return '-'
}

function roleLabel(role: string): string {
  if (role === 'admin') return 'Admin'
  return 'Doktor'
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

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiClient.get<UserListResponse>('/api/v1/admin/users')
      setUsers(data.users)
    } catch {
      setMessage({ type: 'error', text: 'Kullanici listesi alinamadi' })
    } finally {
      setLoading(false)
    }
  }, [])

  const syncOpenEMR = useCallback(async () => {
    setIsSyncing(true)
    try {
      const data = await apiClient.get<OpenEMRSyncResponse>('/api/v1/admin/openemr-doctors')
      const newDocs = data.doctors.filter((d) => !d.already_in_system)
      setNewOpenEMRDoctors(newDocs)
      if (newDocs.length === 0) {
        setMessage({ type: 'success', text: 'OpenEMR ile senkronize edildi — yeni doktor yok' })
      }
    } catch {
      setMessage({ type: 'error', text: 'OpenEMR baglantisi basarisiz' })
    } finally {
      setIsSyncing(false)
    }
  }, [])

  useEffect(() => {
    void fetchUsers()
    void syncOpenEMR() // startup check
  }, [fetchUsers, syncOpenEMR])

  useEffect(() => {
    if (message) {
      const timer = setTimeout(() => setMessage(null), 4000)
      return () => clearTimeout(timer)
    }
  }, [message])

  return (
    <div className="flex-1 overflow-auto bg-slate-50 p-6">
      <div className="mx-auto max-w-4xl space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-7 w-7 text-blue-600" />
            <div>
              <h1 className="text-xl font-bold text-slate-800">Kullanici Yonetimi</h1>
              <p className="text-sm text-slate-500">Doktor ve admin hesaplarini yonetin</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => void syncOpenEMR()}
              disabled={isSyncing}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
            >
              {isSyncing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="h-4 w-4" />
              )}
              OpenEMR Senkronize Et
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
              Yeni Kullanici
            </button>
          </div>
        </div>

        {/* Message */}
        {message && (
          <div
            className={cn(
              'rounded-lg border px-4 py-3 text-sm',
              message.type === 'success'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-red-200 bg-red-50 text-red-700'
            )}
          >
            {message.text}
          </div>
        )}

        {/* New OpenEMR Doctors Banner */}
        {newOpenEMRDoctors.length > 0 && (
          <div className="rounded-xl border-2 border-amber-300 bg-amber-50 p-4 space-y-3">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              <h3 className="text-sm font-semibold text-amber-800">
                {newOpenEMRDoctors.length} yeni doktor OpenEMR'de bulundu
              </h3>
            </div>
            <p className="text-xs text-amber-700">
              Bu doktorlar henuz sisteme eklenmedi. Rol ve brans atayarak ekleyin.
            </p>
            <div className="space-y-2">
              {newOpenEMRDoctors.map((doc) => (
                <div
                  key={doc.username}
                  className="flex items-center justify-between rounded-lg bg-white border border-amber-200 px-4 py-3"
                >
                  <div className="flex items-center gap-3">
                    <UserPlus className="h-5 w-5 text-amber-600" />
                    <div>
                      <p className="text-sm font-medium text-slate-800">
                        {doc.fname} {doc.lname}
                      </p>
                      <p className="text-xs text-slate-500">
                        Kullanici: <span className="font-mono">{doc.username}</span>
                        {doc.specialty && (
                          <> — Uzmanlik: <span className="font-medium">{doc.specialty}</span></>
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
                    Rol Ata ve Ekle
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
              setMessage({ type: 'success', text: 'Kullanici olusturuldu' })
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
              setMessage({ type: 'success', text: 'Kullanici guncellendi' })
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
              setMessage({ type: 'success', text: 'Sifre degistirildi' })
            }}
            onCancel={() => setPasswordUserId(null)}
          />
        )}

        {/* User List */}
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          </div>
        ) : (
          <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200/60 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 bg-slate-50/50">
                  <th className="px-4 py-3 text-left font-medium text-slate-600">Kullanici</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600">Gorunen Ad</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600">Rol</th>
                  <th className="px-4 py-3 text-left font-medium text-slate-600">Brans</th>
                  <th className="px-4 py-3 text-right font-medium text-slate-600">Islemler</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="px-4 py-3 font-mono text-slate-800">{u.username}</td>
                    <td className="px-4 py-3 text-slate-700">{u.display_name}</td>
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          'inline-flex rounded-full px-2 py-0.5 text-xs font-medium',
                          u.role === 'admin'
                            ? 'bg-purple-50 text-purple-700'
                            : 'bg-blue-50 text-blue-700'
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
                              ? 'bg-emerald-50 text-emerald-700'
                              : 'bg-amber-50 text-amber-700'
                          )}
                        >
                          {bransLabel(u.brans)}
                        </span>
                      ) : (
                        <span className="text-slate-400">-</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {u.username === currentUser?.username ? (
                        <span className="text-xs text-slate-400 italic">Mevcut hesap</span>
                      ) : (
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => {
                              setEditingUser(u)
                              setShowCreateForm(false)
                              setPasswordUserId(null)
                            }}
                            className="rounded p-1.5 text-slate-400 hover:bg-blue-50 hover:text-blue-600 transition-colors"
                            title="Duzenle"
                          >
                            <Pencil className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => {
                              setPasswordUserId(u.id)
                              setEditingUser(null)
                              setShowCreateForm(false)
                            }}
                            className="rounded p-1.5 text-slate-400 hover:bg-amber-50 hover:text-amber-600 transition-colors"
                            title="Sifre Degistir"
                          >
                            <KeyRound className="h-4 w-4" />
                          </button>
                          <button
                            onClick={async () => {
                              if (!window.confirm(`'${u.username}' kullanicisini kalici olarak silmek istediginize emin misiniz?`)) return
                              try {
                                await apiClient.delete(`/api/v1/admin/users/${u.id}`)
                                setMessage({ type: 'success', text: `'${u.username}' silindi` })
                                void fetchUsers()
                              } catch {
                                setMessage({ type: 'error', text: 'Silme islemi basarisiz' })
                              }
                            }}
                            className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                            title="Sil"
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
  const [username, setUsername] = useState(prefill?.username ?? '')
  const [password, setPassword] = useState(prefill?.username ?? '')
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
      setError(err instanceof Error ? err.message : 'Kullanici olusturulamadi')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-slate-200/60 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800">
          {prefill ? `OpenEMR Doktoru Ekle: ${prefill.fname} ${prefill.lname}` : 'Yeni Kullanici Olustur'}
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Kullanici Adi</label>
            <input
              type="text"
              required
              minLength={3}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder="ornek: doktor3"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Sifre</label>
            <input
              type="password"
              required
              minLength={3}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Gorunen Ad</label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              placeholder="Dr. Mehmet Oz"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Rol</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {role === 'doctor' && (
            <div className="col-span-2">
              <label className="block text-xs font-medium text-slate-600 mb-1">Brans</label>
              <select
                value={brans}
                onChange={(e) => setBrans(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {BRANS_OPTIONS.filter((o) => o.value !== '').map((o) => (
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
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Iptal
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Olustur
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
  const [displayName, setDisplayName] = useState(user.display_name)
  const [role, setRole] = useState(user.role)
  const [brans, setBrans] = useState(user.brans)
  const [isActive, setIsActive] = useState(user.is_active)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

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
      setError(err instanceof Error ? err.message : 'Guncelleme basarisiz')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-blue-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800">
          Kullaniciyi Duzenle: <span className="font-mono text-blue-600">{user.username}</span>
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Gorunen Ad</label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Rol</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              {ROLE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>
          {role === 'doctor' && (
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Brans</label>
              <select
                value={brans}
                onChange={(e) => setBrans(e.target.value)}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                {BRANS_OPTIONS.filter((o) => o.value !== '').map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
          )}
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Durum</label>
            <select
              value={isActive ? 'active' : 'inactive'}
              onChange={(e) => setIsActive(e.target.value === 'active')}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
            >
              <option value="active">Aktif</option>
              <option value="inactive">Pasif</option>
            </select>
          </div>
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Iptal
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Kaydet
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
      setError(err instanceof Error ? err.message : 'Sifre degistirilemedi')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="rounded-xl bg-white shadow-sm ring-1 ring-amber-200 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-800">
          Sifre Degistir: <span className="font-mono text-amber-600">{username}</span>
        </h3>
        <button onClick={onCancel} className="rounded p-1 text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <label className="block text-xs font-medium text-slate-600 mb-1">Yeni Sifre</label>
          <input
            type="password"
            required
            minLength={3}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20"
          />
        </div>
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
          >
            Iptal
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <KeyRound className="h-3.5 w-3.5" />}
            Degistir
          </button>
        </div>
      </form>
    </div>
  )
}
