import { describe, it, expect } from 'vitest'
import { fftInPlace, spectrumMagnitudes, dominantHz } from './fft'

function sine(freq: number, fs: number, n: number): number[] {
  const out = new Array<number>(n)
  for (let i = 0; i < n; i++) out[i] = Math.sin((2 * Math.PI * freq * i) / fs)
  return out
}

describe('spectrumMagnitudes — window + FFT of the accel window', () => {
  it('returns `out` non-negative bins spanning 0..Nyquist', () => {
    const mags = spectrumMagnitudes(sine(3.8, 100, 100), 512, 256)
    expect(mags).toHaveLength(256)
    for (const m of mags) expect(m).toBeGreaterThanOrEqual(0)
  })

  it('recovers a Z24 3.8 Hz tone near its bin (~19-20 of 256)', () => {
    const mags = spectrumMagnitudes(sine(3.8, 100, 100), 512, 256)
    const hz = dominantHz(mags)
    expect(hz).toBeGreaterThan(3.4)
    expect(hz).toBeLessThan(4.2)
  })

  it('recovers the Z24 second mode 15.2 Hz (4 × f1)', () => {
    const mags = spectrumMagnitudes(sine(15.2, 100, 100), 512, 256)
    const hz = dominantHz(mags)
    expect(hz).toBeGreaterThan(14.5)
    expect(hz).toBeLessThan(16.0)
  })

  it('DC (constant) input concentrates at bin 0; dominantHz stays near-zero', () => {
    const mags = spectrumMagnitudes(new Array<number>(100).fill(1), 512, 256)
    // The DC bin dominates the spectrum (FFT correctness)...
    expect(mags[0]).toBeGreaterThan(mags[1])
    for (let k = 2; k < mags.length; k++) expect(mags[0]).toBeGreaterThan(mags[k])
    // ...but `dominantHz` deliberately starts at bin 1 so a constant offset can
    // never drive the vibration-mode readout — only leakage energy remains.
    expect(dominantHz(mags)).toBeLessThanOrEqual(1)
  })

  it('is deterministic', () => {
    const a = spectrumMagnitudes(sine(3.8, 100, 100), 512, 256)
    const b = spectrumMagnitudes(sine(3.8, 100, 100), 512, 256)
    expect(a).toEqual(b)
  })
})

describe('fftInPlace — radix-2 spot checks', () => {
  it('concentrates a DC signal at index 0', () => {
    const n = 8
    const re = new Float64Array(n)
    const im = new Float64Array(n)
    re.fill(1)
    fftInPlace(re, im)
    expect(re[0]).toBeCloseTo(8, 5) // sum of 8 ones
    for (let k = 1; k < n; k++) {
      expect(Math.hypot(re[k], im[k])).toBeLessThan(1e-9)
    }
  })

  it('places a bin-2 cosine at ±2 with amplitude N/2', () => {
    const n = 16
    const re = new Float64Array(n)
    const im = new Float64Array(n)
    for (let i = 0; i < n; i++) re[i] = Math.cos((2 * Math.PI * 2 * i) / n)
    fftInPlace(re, im)
    expect(Math.hypot(re[2], im[2])).toBeCloseTo(8, 5) // N/2
    expect(Math.hypot(re[n - 2], im[n - 2])).toBeCloseTo(8, 5) // conjugate symmetric
  })
})
