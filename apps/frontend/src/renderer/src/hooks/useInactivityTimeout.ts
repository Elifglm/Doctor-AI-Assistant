/**
 * Inactivity timeout hook.
 *
 * Monitors mouse, keyboard, click and scroll events.  After
 * `timeoutMs` milliseconds of inactivity the user is logged out
 * automatically.  A warning callback fires `warningBeforeMs`
 * milliseconds before the timeout.
 */

import { useEffect, useRef, useCallback } from 'react'

/** 30 minutes in milliseconds. */
const TIMEOUT_MS = 30 * 60 * 1000

/** Show the warning 5 minutes before auto-logout. */
const WARNING_BEFORE_MS = 5 * 60 * 1000

interface UseInactivityTimeoutOptions {
  /** Whether the timeout is active (only when authenticated). */
  enabled: boolean
  /** Called when the user should be logged out. */
  onLogout: () => void
  /** Called when the warning should appear (`true` = show, `false` = hide). */
  onWarningChange: (visible: boolean) => void
}

interface UseInactivityTimeoutReturn {
  /** Reset both timers manually (e.g. when the user dismisses the warning). */
  resetTimers: () => void
}

export function useInactivityTimeout({
  enabled,
  onLogout,
  onWarningChange,
}: UseInactivityTimeoutOptions): UseInactivityTimeoutReturn {
  const logoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const warningTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const warningVisibleRef = useRef(false)

  const clearTimers = useCallback(() => {
    if (logoutTimerRef.current) {
      clearTimeout(logoutTimerRef.current)
      logoutTimerRef.current = null
    }
    if (warningTimerRef.current) {
      clearTimeout(warningTimerRef.current)
      warningTimerRef.current = null
    }
  }, [])

  const resetTimers = useCallback(() => {
    clearTimers()

    // If warning was visible, hide it on activity
    if (warningVisibleRef.current) {
      warningVisibleRef.current = false
      onWarningChange(false)
    }

    // Set the warning timer (fires 5 min before logout)
    warningTimerRef.current = setTimeout(() => {
      warningVisibleRef.current = true
      onWarningChange(true)
    }, TIMEOUT_MS - WARNING_BEFORE_MS)

    // Set the logout timer
    logoutTimerRef.current = setTimeout(() => {
      onLogout()
    }, TIMEOUT_MS)
  }, [clearTimers, onLogout, onWarningChange])

  useEffect(() => {
    if (!enabled) {
      clearTimers()
      return
    }

    // Events that indicate user activity
    const events: Array<keyof WindowEventMap> = ['mousemove', 'keydown', 'click', 'scroll']

    const handleActivity = (): void => {
      resetTimers()
    }

    // Start the timers immediately
    resetTimers()

    for (const event of events) {
      window.addEventListener(event, handleActivity, { passive: true })
    }

    return () => {
      clearTimers()
      for (const event of events) {
        window.removeEventListener(event, handleActivity)
      }
    }
  }, [enabled, resetTimers, clearTimers])

  return { resetTimers }
}
