import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../services/apiClient'
import type { Session, SessionListResponse, VisitType } from '../types/session'

interface SessionListParams {
  limit?: number
  page?: number
  sort?: string
  status?: string
}

interface CreateSessionPayload {
  patient_id?: string
  visit_type: VisitType
  doctor_name: string
  pre_diagnosis?: string
  location?: string
  kvkk_consent: boolean
}

export function useSessionList(params: SessionListParams = {}) {
  const searchParams = new URLSearchParams()
  if (params.limit) searchParams.set('limit', params.limit.toString())
  if (params.page) searchParams.set('page', params.page.toString())
  if (params.sort) searchParams.set('sort', params.sort)
  if (params.status) searchParams.set('status', params.status)

  const queryString = searchParams.toString()
  const path = `/api/v1/sessions${queryString ? `?${queryString}` : ''}`

  return useQuery<SessionListResponse>({
    queryKey: ['sessions', params],
    queryFn: () => apiClient.get<SessionListResponse>(path),
  })
}

export function useSession(id: number | null) {
  return useQuery<Session>({
    queryKey: ['session', id],
    queryFn: () => apiClient.get<Session>(`/api/v1/sessions/${id}`),
    enabled: id !== null,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()

  return useMutation<Session, Error, CreateSessionPayload>({
    mutationFn: (payload) => apiClient.post<Session>('/api/v1/sessions', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
