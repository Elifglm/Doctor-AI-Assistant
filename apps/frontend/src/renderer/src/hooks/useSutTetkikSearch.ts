import { useState, useEffect } from 'react'
import { apiClient } from '../services/apiClient'
import type { SUTItem, SUTSearchResponse } from '../types/sut_tetkik'

export function useSutTetkikSearch(query: string, brans?: string, debounceMs = 300) {
  const [results, setResults] = useState<SUTItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // Locale-aware lowercase + Unicode NFC: ensures "İdrar"/"IDRAR"/"idrar"
    // produce the same query string and the same TanStack/HTTP cache key.
    const trimmed = query.trim().normalize('NFC').toLocaleLowerCase('tr-TR')
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
        let url = `/api/v1/sut-tetkik/search?q=${encodeURIComponent(trimmed)}&limit=20`
        if (brans) {
          url += `&brans=${encodeURIComponent(brans)}`
        }
        const data = await apiClient.get<SUTSearchResponse>(url, { signal: controller.signal })
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
  }, [query, brans, debounceMs])

  return { results, isLoading, error }
}
