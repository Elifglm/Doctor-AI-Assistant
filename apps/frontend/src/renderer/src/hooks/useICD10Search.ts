import { useState, useEffect, useRef } from 'react'
import { apiClient } from '../services/apiClient'
import type { ICD10Item, ICD10SearchResponse } from '../types/icd10'

export function useICD10Search(query: string, debounceMs = 300) {
  const [results, setResults] = useState<ICD10Item[]>([])
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
        const data = await apiClient.get<ICD10SearchResponse>(
          `/api/v1/icd10/search?q=${encodeURIComponent(trimmed)}&limit=20`
        )
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
  }, [query, debounceMs])

  return { results, isLoading, error }
}
