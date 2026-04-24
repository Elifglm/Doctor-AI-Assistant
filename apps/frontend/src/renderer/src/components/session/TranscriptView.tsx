import { useRef, useEffect, useState, useCallback } from 'react'
import { ArrowDown } from 'lucide-react'
import { TranscriptSegmentItem } from './TranscriptSegment'
import { useT } from '../../hooks/useT'
import type { TranscriptionSegment } from '../../types/transcription'

interface TranscriptViewProps {
  segments: TranscriptionSegment[]
}

export function TranscriptView({ segments }: TranscriptViewProps): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [isScrolledUp, setIsScrolledUp] = useState(false)
  const t = useT()

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Track scroll position
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const handleScroll = (): void => {
      const { scrollTop, scrollHeight, clientHeight } = container
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 60
      setIsScrolledUp(!isNearBottom)
    }

    container.addEventListener('scroll', handleScroll)
    return () => container.removeEventListener('scroll', handleScroll)
  }, [])

  // Auto-scroll on new segments if already at bottom
  useEffect(() => {
    if (!isScrolledUp) {
      scrollToBottom()
    }
  }, [segments.length, isScrolledUp, scrollToBottom])

  if (segments.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center text-slate-400">
        <p className="text-sm">{t('transcript_empty')}</p>
      </div>
    )
  }

  return (
    <div className="relative flex-1 overflow-hidden">
      <div ref={containerRef} className="h-full overflow-y-auto">
        <div className="divide-y divide-slate-100">
          {segments.map((segment, index) => (
            <TranscriptSegmentItem key={segment.id} segment={segment} index={index} />
          ))}
        </div>
        <div ref={bottomRef} />
      </div>

      {isScrolledUp && (
        <button
          onClick={scrollToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-slate-800 px-4 py-2 text-xs font-medium text-white shadow-lg transition-colors hover:bg-slate-700"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          {t('transcript_backToLive')}
        </button>
      )}
    </div>
  )
}
