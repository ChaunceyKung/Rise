import { createHash } from 'node:crypto'
import { appendFileSync, openSync, closeSync, fsyncSync, writeFileSync } from 'node:fs'

export function canonical(v) {
  if (v === null || typeof v === 'boolean') return JSON.stringify(v)
  if (typeof v === 'number' && Number.isSafeInteger(v)) return JSON.stringify(v)
  if (typeof v === 'string') {
    if (!v.isWellFormed()) throw new Error('unpaired surrogate')
    return JSON.stringify(v)
  }
  if (Array.isArray(v)) return '[' + v.map(canonical).join(',') + ']'
  if (v && Object.getPrototypeOf(v) === Object.prototype) return '{' + Object.keys(v).sort().map(k => canonical(k)+':'+canonical(v[k])).join(',') + '}'
  throw new Error('restricted JSON only')
}
export const hash = v => createHash('sha256').update(canonical(v)).digest('hex')
export const bytesHash = b => createHash('sha256').update(b).digest('hex')
export function freeze(v) { if (v && typeof v === 'object') { Object.values(v).forEach(freeze); Object.freeze(v) }; return v }
export function writer(path, limits) {
  let count = 0, total = 0
  return row => {
    const text = JSON.stringify(row)+'\n', size = Buffer.byteLength(text)
    if (++count > limits.count || size > limits.item || (total += size) > limits.total) {
      writeFileSync(path+'.limit', 'data_limit_exceeded')
      throw new Error('data_limit_exceeded')
    }
    appendFileSync(path, text)
    const fd = openSync(path, 'r+')
    try { fsyncSync(fd) } finally { closeSync(fd) }
  }
}
