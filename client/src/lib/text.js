export function toTitleCaseWords(value) {
  return String(value || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function humanizeKey(value, fallback = '') {
  const normalized = String(value || '').trim()
  if (!normalized) return fallback

  return normalized
    .replace(/_/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

export function splitSentences(text) {
  const value = String(text || '').trim()
  if (!value) return []
  const matches = value.match(/[^.!?]+[.!?]+|[^.!?]+$/g)
  return matches ? matches.map((part) => part.trim()).filter(Boolean) : [value]
}

export function buildPreviewSummary(text, sentenceCount = 2) {
  const sentences = splitSentences(text)
  if (!sentences.length) return ''
  if (sentences.length <= sentenceCount) return sentences.join(' ')
  return `${sentences.slice(0, sentenceCount).join(' ')}...`
}

export function buildSummaryBlocks(text, blockSize = 2) {
  const sentences = splitSentences(text)
  if (sentences.length <= blockSize) return [sentences.join(' ')]

  const blocks = []
  for (let index = 0; index < sentences.length; index += blockSize) {
    blocks.push(sentences.slice(index, index + blockSize).join(' '))
  }
  return blocks
}
