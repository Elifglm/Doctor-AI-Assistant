import { useState, useRef, useCallback, useEffect } from 'react'
import { useSessionStore } from '../stores/sessionStore'
import { useTranscriptionStore } from '../stores/transcriptionStore'
import { useUIStore } from '../stores/uiStore'
import { AudioCapture } from '../services/audioCapture'
import { WSClient } from '../services/wsClient'
import { t } from '../lib/i18n'
import type { WSProgress, WSResult, WSError } from '../types/transcription'

export function useRecording(sessionId: number | null) {
  const audioCapture = useRef<AudioCapture | null>(null)
  const wsClient = useRef<WSClient | null>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reportTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const elapsedTimeOffset = useRef(0)
  const callGeneration = useRef(0)
  const [error, setError] = useState<string | null>(null)

  const clearReportTimeout = (): void => {
    if (reportTimeoutRef.current) {
      clearTimeout(reportTimeoutRef.current)
      reportTimeoutRef.current = null
    }
  }

  const { setRecordingState, setElapsedTime, setAudioLevel, recordingState } = useSessionStore()
  const {
    setProcessing,
    setSegments,
    setAutoReportReady,
    setReportFlowDone,
    reset: resetTranscription,
  } = useTranscriptionStore()

  // Shared cleanup - releases all recording resources
  const cleanup = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    clearReportTimeout()
    audioCapture.current?.stop()
    audioCapture.current = null
    wsClient.current?.close()
    wsClient.current = null
  }, [])

  const startRecording = useCallback(async () => {
    if (!sessionId) return

    // Prevent connecting if this hook already has an active WS connection
    if (wsClient.current?.isConnected) {
      setError(t('err_recordingActive'))
      return
    }

    // Increment generation — any previous async call becomes stale
    const thisCall = ++callGeneration.current

    // Always clean up previous resources before starting
    cleanup()

    // Yield to event loop so the browser can send the WS close frame
    await new Promise((resolve) => setTimeout(resolve, 50))

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

      // Processing start handler
      wsClient.current.on('processing_start', () => {
        setRecordingState('processing')
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
        // Do NOT close the WS yet — wait for report_ready or report_warning
        // from the backend's auto-report generation step.
        // A safety timeout ensures we don't hang forever if backend fails silently.
        clearReportTimeout()
        reportTimeoutRef.current = setTimeout(() => {
          if (!useTranscriptionStore.getState().reportFlowDone) {
            setReportFlowDone()
            setRecordingState('idle')
            wsClient.current?.close()
            wsClient.current = null
          }
          reportTimeoutRef.current = null
        }, 60_000)
      })

      wsClient.current.on('report_ready', (data) => {
        const msg = data as { report_id: number; session_id: number }
        setAutoReportReady(msg.report_id)
        setRecordingState('idle')
        clearReportTimeout()
        wsClient.current?.close()
        wsClient.current = null
      })

      wsClient.current.on('report_warning', () => {
        // Auto-report failed but we can proceed without it
        setReportFlowDone()
        setRecordingState('idle')
        clearReportTimeout()
        wsClient.current?.close()
        wsClient.current = null
      })

      wsClient.current.on('error', (data) => {
        const msg = data as WSError
        console.error('WS error:', msg.message)
        setError(msg.message)
        setRecordingState('idle')
        cleanup()
      })

      wsClient.current.on('close', () => {
        // If we're still processing when WS closes, check if we have results
        if (useSessionStore.getState().recordingState === 'processing') {
          const store = useTranscriptionStore.getState()
          if (store.segments.length > 0) {
            // We have transcription results — mark report flow as done and proceed
            console.warn('WS closed during report generation, proceeding with available data')
            if (!store.reportFlowDone) {
              setReportFlowDone()
            }
            setRecordingState('idle')
          } else {
            // No results at all — something went wrong
            console.warn('WS closed while still processing with no results')
            setError(t('err_disconnected'))
            setRecordingState('idle')
          }
        }
      })

      await wsClient.current.connect()

      // If this call was superseded while connecting, bail out
      if (thisCall !== callGeneration.current) return

      // Start audio capture using the user-selected mic (falls back to default)
      audioCapture.current = new AudioCapture()
      const selectedMicId = useUIStore.getState().micDeviceId
      await audioCapture.current.start(
        (chunk) => {
          wsClient.current?.sendBinary(chunk)
        },
        (level) => {
          setAudioLevel(level)
        },
        (errorMsg) => {
          setError(errorMsg)
          setRecordingState('idle')
          cleanup()
        },
        selectedMicId,
      )

      // Check again after audio setup
      if (thisCall !== callGeneration.current) return

      setRecordingState('recording')

      // Start timer from zero
      elapsedTimeOffset.current = 0
      const startTime = Date.now()
      timerRef.current = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000))
      }, 1000)
    } catch (err: unknown) {
      // Ignore errors from stale (superseded) calls
      if (thisCall !== callGeneration.current) return

      console.error('Recording start failed:', err)
      let message: string
      if (err instanceof DOMException && err.name === 'NotAllowedError') {
        message = t('err_micDenied')
      } else if (err instanceof DOMException && err.name === 'NotFoundError') {
        message = t('err_micNotFound')
      } else if (err instanceof DOMException && err.name === 'NotSupportedError') {
        message = t('err_audioFormat')
      } else if (err instanceof Error) {
        message = err.message
      } else if (err && typeof err === 'object' && 'message' in err) {
        message = String((err as { message: unknown }).message)
      } else {
        message = t('err_recordingStartUnknown', { error: String(err) })
      }
      setError(message)
      setRecordingState('idle')
      cleanup()
    }
  }, [sessionId, cleanup, resetTranscription, setProcessing, setSegments, setAutoReportReady, setReportFlowDone, setRecordingState, setElapsedTime, setAudioLevel])

  const pauseRecording = useCallback(() => {
    // Save current elapsed time and stop the timer
    elapsedTimeOffset.current = useSessionStore.getState().elapsedTime
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    audioCapture.current?.pause()
    setRecordingState('paused')
  }, [setRecordingState])

  const resumeRecording = useCallback(() => {
    audioCapture.current?.resume()
    setRecordingState('recording')

    // Restart timer continuing from the saved offset
    const saved = elapsedTimeOffset.current
    const resumeTime = Date.now()
    timerRef.current = setInterval(() => {
      setElapsedTime(saved + Math.floor((Date.now() - resumeTime) / 1000))
    }, 1000)
  }, [setRecordingState, setElapsedTime])

  const stopRecording = useCallback(() => {
    // Stop timer
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }

    // Stop audio capture but keep WS open for progress/result messages
    audioCapture.current?.stop()
    audioCapture.current = null

    // Send stop signal to backend
    wsClient.current?.sendJSON({ type: 'stop' })

    setRecordingState('processing')
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
