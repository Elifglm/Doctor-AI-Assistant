import { useState, useRef, useCallback, useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { useTranscriptionStore } from '../stores/transcriptionStore'
import { AudioCapture } from '../services/audioCapture'
import { WSClient } from '../services/wsClient'
import type { WSProgress, WSResult, WSError } from '../types/transcription'

export function useRecording(sessionId: number | null) {
  const audioCapture = useRef<AudioCapture | null>(null)
  const wsClient = useRef<WSClient | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { setRecordingState, setElapsedTime, setAudioLevel, recordingState } = useSessionStore()
  const { setProcessing, setSegments, reset: resetTranscription } = useTranscriptionStore()

  // Shared cleanup - releases all recording resources
  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    audioCapture.current?.stop()
    audioCapture.current = null
    wsClient.current?.close()
    wsClient.current = null
  }, [])

  const startRecording = useCallback(async () => {
    if (!sessionId) return

    // Always clean up previous resources before starting
    cleanup()

    setError(null)
    setElapsedTime(0)
    setAudioLevel(0)
    resetTranscription()

    try {
      // Connect WebSocket
      const baseUrl =
        (typeof window !== 'undefined' && window.electronAPI?.getBackendUrl()) ||
        'http://127.0.0.1:8700'
      const wsUrl = baseUrl.replace('http', 'ws') + `/api/v1/sessions/ws/${sessionId}`
      wsClient.current = new WSClient(wsUrl)

      // Listen for messages
      wsClient.current.on('progress', (data) => {
        const msg = data as WSProgress
        setProcessing(msg.stage, msg.message, msg.progress)
      })

      wsClient.current.on('result', (data) => {
        const msg = data as WSResult
        const segments = msg.segments.map((seg, i) => ({
          id: i,
          session_id: msg.session_id,
          segment_index: seg.segment_index,
          text: seg.text,
          speaker: seg.speaker,
          speaker_label: seg.speaker_label,
          start_time: seg.start_time,
          end_time: seg.end_time,
          confidence: seg.confidence ?? null,
          words: seg.words || null,
          is_edited: false,
        }))
        setSegments(segments)
      })

      wsClient.current.on('error', (data) => {
        const msg = data as WSError
        console.error('WS error:', msg.message)
        setError(msg.message)
      })

      await wsClient.current.connect()

      // Start audio capture
      audioCapture.current = new AudioCapture()
      await audioCapture.current.start(
        (chunk) => {
          wsClient.current?.sendBinary(chunk)
        },
        (level) => {
          setAudioLevel(level)
        }
      )

      setRecordingState('recording')

      // Start timer from zero
      const startTime = Date.now()
      timerRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
      }, 1000)
    } catch (err: unknown) {
      console.error('Recording start failed:', err)
      let message: string
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        message = 'Mikrofon erisimi reddedildi. Lutfen mikrofon iznini kontrol edin.'
      } else if (err instanceof DOMException && err.name === 'NotFoundError') {
        message = 'Mikrofon bulunamadi. Lutfen bir mikrofon baglayip tekrar deneyin.'
      } else if (err instanceof DOMException && err.name === 'NotSupportedError') {
        message = 'Ses kayit formati desteklenmiyor.'
      } else if (err instanceof Error) {
        message = err.message
      } else if (err && typeof err === 'object' && 'message' in err) {
        message = String((err as { message: unknown }).message)
      } else {
        message = `Kayit baslatilirken beklenmeyen hata: ${String(err)}`
      }
      setError(message)
      setRecordingState('idle')
      cleanup()
    }
  }, [sessionId, cleanup, resetTranscription, setProcessing, setSegments, setRecordingState, setElapsedTime, setAudioLevel])

  const pauseRecording = useCallback(() => {
    audioCapture.current?.pause()
    setRecordingState('paused')
  }, [setRecordingState])

  const resumeRecording = useCallback(() => {
    audioCapture.current?.resume()
    setRecordingState('recording')
  }, [setRecordingState])

  const stopRecording = useCallback(() => {
    // Stop timer
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    // Stop audio capture
    audioCapture.current?.stop()
    audioCapture.current = null

    // Send stop signal to backend
    wsClient.current?.sendJSON({ type: 'stop' })

    setRecordingState('idle')
    setAudioLevel(0)
  }, [setRecordingState, setAudioLevel])

  // Cleanup on unmount OR when sessionId changes
  useEffect(() => {
    return () => {
      cleanup()
      setRecordingState('idle')
      setElapsedTime(0)
      setAudioLevel(0)
    }
  }, [sessionId, cleanup, setRecordingState, setElapsedTime, setAudioLevel])

  return {
    startRecording,
    pauseRecording,
    resumeRecording,
    stopRecording,
    recordingState,
    error,
  }
}
