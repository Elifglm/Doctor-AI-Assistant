import { useState, useEffect } from 'react'
import { apiClient } from '../services/apiClient'
import type { ICD10Item, ICD10SearchResponse } from '../types/icd10'

export function useICD10Search(query: string, debounceMs = 300) {
  const [results, setResults] = useState<ICD10Item[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setResults([])
      setIsLoading(false)
      return
    }

    const controller = new AbortController()
    let cancelled = false
    setIsLoading(true)

    const timer = setTimeout(async () => {
      try {
        const data = await apiClient.get<ICD10SearchResponse>(
          `/api/v1/icd10/search?q=${encodeURIComponent(trimmed)}&limit=20`,
          { signal: controller.signal },
        )
        if (cancelled) return
        setResults(data.results)
        setError(null)
      } catch (err) {
        if (cancelled) return
        if (err instanceof Error && err.name !== 'AbortError') {
          setError(err.message)
          setResults([])
        }
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }, debounceMs)

    return () => {
      cancelled = true
      clearTimeout(timer)
      controller.abort()
    }
  }, [query, debounceMs])

  return { results, isLoading, error }
}
