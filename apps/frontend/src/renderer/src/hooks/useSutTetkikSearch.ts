import { useState, useEffect, useRef } from 'react'
import { apiClient } from '../services/apiClient'
import type { SUTItem, SUTSearchResponse } from '../types/sut_tetkik'

export function useSutTetkikSearch(query: string, brans?: string, debounceMs = 300) {
  const [results, setResults] = useState<SUTItem[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < 2) {
      setResults([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    const timer = setTimeout(async () => {
      abortRef.current?.abort()
      abortRef.current = new AbortController()

      try {
        let url = `/api/v1/sut-tetkik/search?q=${encodeURIComponent(trimmed)}&limit=20`
        if (brans) {
          url += `&brans=${encodeURIComponent(brans)}`
        }
        const data = await apiClient.get<SUTSearchResponse>(url)
        setResults(data.results)
        setError(null)
      } catch (err) {
        if (err instanceof Error && err.name !== 'AbortError') {
          setError(err.message)
          setResults([])
        }
      } finally {
        setIsLoading(false)
      }
    }, debounceMs)

    return () => clearTimeout(timer)
  }, [query, brans, debounceMs])

  return { results, isLoading, error }
}
