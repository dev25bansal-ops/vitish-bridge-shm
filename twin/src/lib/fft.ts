// Lightweight in-place radix-2 FFT (no dependencies, no CDN).
// Used to turn the 100-sample accel window into a 256-point magnitude
// spectrum for the popup chart. Zero-padded + Hann-windowed.

export function fftInPlace(re: Float64Array, im: Float64Array): void {
  const n = re.length
  // bit-reversal permutation
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1
    for (; j & bit; bit >>= 1) j ^= bit
    j ^= bit
    if (i < j) {
      const tr = re[i]
      re[i] = re[j]
      re[j] = tr
      const ti = im[i]
      im[i] = im[j]
      im[j] = ti
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len
    const wRe = Math.cos(ang)
    const wIm = Math.sin(ang)
    for (let i = 0; i < n; i += len) {
      let cRe = 1
      let cIm = 0
      const half = len / 2
      for (let k = 0; k < half; k++) {
        const uRe = re[i + k]
        const uIm = im[i + k]
        const vRe = re[i + k + half] * cRe - im[i + k + half] * cIm
        const vIm = re[i + k + half] * cIm + im[i + k + half] * cRe
        re[i + k] = uRe + vRe
        im[i + k] = uIm + vIm
        re[i + k + half] = uRe - vRe
        im[i + k + half] = uIm - vIm
        const ncRe = cRe * wRe - cIm * wIm
        cIm = cRe * wIm + cIm * wRe
        cRe = ncRe
      }
    }
  }
}

/**
 * Hann-windowed magnitude spectrum of `samples`, zero-padded to `n` (power of
 * two) and returned as `out` magnitude bins spanning 0..Nyquist.
 */
export function spectrumMagnitudes(samples: number[], n = 512, out = 256): number[] {
  const re = new Float64Array(n)
  const im = new Float64Array(n)
  for (let i = 0; i < n; i++) {
    const x = i < samples.length ? samples[i] : 0
    const hann = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (n - 1))
    re[i] = x * hann
  }
  fftInPlace(re, im)
  const mags = new Array<number>(out)
  const scale = 2 / n
  for (let k = 0; k < out; k++) {
    const bin = Math.floor((k * n) / (2 * out))
    mags[k] = Math.sqrt(re[bin] * re[bin] + im[bin] * im[bin]) * scale
  }
  return mags
}

/** Dominant frequency in Hz given a 256-bin spectrum over 0..50 Hz. */
export function dominantHz(mags: number[], fs = 100): number {
  let peak = 0
  let peakBin = 0
  for (let k = 1; k < mags.length; k++) {
    if (mags[k] > peak) {
      peak = mags[k]
      peakBin = k
    }
  }
  const binHz = (fs / 2) / mags.length
  return Math.round(peakBin * binHz * 100) / 100
}
