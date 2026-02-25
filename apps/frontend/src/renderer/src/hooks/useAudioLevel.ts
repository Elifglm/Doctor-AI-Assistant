import { useSessionStore } from '../stores/sessionStore'

export function useAudioLevel(): number {
  const audioLevel = useSessionStore((s) => s.audioLevel)
  return audioLevel
}
