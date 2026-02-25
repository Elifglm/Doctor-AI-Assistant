export class AudioCapture {
  private mediaRecorder: MediaRecorder | null = null
  private stream: MediaStream | null = null
  private analyser: AnalyserNode | null = null
  private audioContext: AudioContext | null = null
  private onChunk: ((data: Blob) => void) | null = null
  private onLevel: ((level: number) => void) | null = null
  private animFrameId: number | null = null

  async start(onChunk: (data: Blob) => void, onLevel?: (level: number) => void): Promise<void> {
    // Stop any existing recording first
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.stop()
    }

    this.onChunk = onChunk
    this.onLevel = onLevel || null

    // Check if getUserMedia is available
    if (!navigator.mediaDevices?.getUserMedia) {
      throw new Error('Tarayici ses kayit API\'sini desteklemiyor (getUserMedia)')
    }

    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000,
      },
    })

    // Audio level analysis
    if (this.onLevel) {
      this.audioContext = new AudioContext()
      const source = this.audioContext.createMediaStreamSource(this.stream)
      this.analyser = this.audioContext.createAnalyser()
      this.analyser.fftSize = 256
      source.connect(this.analyser)
      this.startLevelMonitoring()
    }

    // Find a supported MIME type for MediaRecorder
    const mimeTypes = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
      '',  // empty = browser default
    ]
    const mimeType = mimeTypes.find((t) => {
      if (t === '') return true
      return MediaRecorder.isTypeSupported(t)
    })

    const recorderOptions: MediaRecorderOptions = {}
    if (mimeType) {
      recorderOptions.mimeType = mimeType
    }

    this.mediaRecorder = new MediaRecorder(this.stream, recorderOptions)

    this.mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0 && this.onChunk) {
        this.onChunk(event.data)
      }
    }

    this.mediaRecorder.onerror = (event) => {
      console.error('MediaRecorder error:', event)
    }

    this.mediaRecorder.start(250) // 250ms chunks
  }

  private startLevelMonitoring(): void {
    if (!this.analyser || !this.onLevel) return
    const dataArray = new Uint8Array(this.analyser.frequencyBinCount)

    const tick = (): void => {
      if (!this.analyser || !this.onLevel) return
      this.analyser.getByteFrequencyData(dataArray)
      const sum = dataArray.reduce((a, b) => a + b, 0)
      const avg = sum / dataArray.length
      const normalized = Math.min(avg / 128, 1)
      this.onLevel(normalized)
      this.animFrameId = requestAnimationFrame(tick)
    }
    tick()
  }

  pause(): void {
    if (this.mediaRecorder?.state === 'recording') {
      this.mediaRecorder.pause()
    }
  }

  resume(): void {
    if (this.mediaRecorder?.state === 'paused') {
      this.mediaRecorder.resume()
    }
  }

  stop(): void {
    if (this.mediaRecorder && this.mediaRecorder.state !== 'inactive') {
      this.mediaRecorder.stop()
    }
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId)
      this.animFrameId = null
    }
    if (this.audioContext) {
      this.audioContext.close()
      this.audioContext = null
    }
    if (this.stream) {
      this.stream.getTracks().forEach((track) => track.stop())
      this.stream = null
    }
    this.analyser = null
    this.mediaRecorder = null
    this.onChunk = null
    this.onLevel = null
  }
}
