const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'content-length',
])

function getBackendBaseUrl() {
  const baseUrl = process.env.BACKEND_URL
  if (!baseUrl) {
    return null
  }

  return baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
}

function readRequestBody(req) {
  if (req.method === 'GET' || req.method === 'HEAD') {
    return Promise.resolve(undefined)
  }

  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', (chunk) => {
      chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
    })
    req.on('end', () => {
      resolve(chunks.length ? Buffer.concat(chunks) : undefined)
    })
    req.on('error', reject)
  })
}

export default async function handler(req, res) {
  const backendBaseUrl = getBackendBaseUrl()
  if (!backendBaseUrl) {
    res.statusCode = 500
    res.setHeader('Content-Type', 'application/json')
    res.end(JSON.stringify({ detail: 'BACKEND_URL is not configured.' }))
    return
  }

  const incomingUrl = new URL(req.url || '/', 'http://localhost')
  const backendPath = incomingUrl.pathname.replace(/^\/api/, '') || '/'
  const targetUrl = new URL(`${backendPath}${incomingUrl.search}`, backendBaseUrl)

  const headers = new Headers()
  Object.entries(req.headers).forEach(([key, value]) => {
    const lowerKey = key.toLowerCase()
    if (value == null || HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey === 'host') {
      return
    }

    if (Array.isArray(value)) {
      value.forEach((item) => headers.append(key, item))
      return
    }

    headers.set(key, value)
  })

  const body = await readRequestBody(req)
  const response = await fetch(targetUrl, {
    method: req.method,
    headers,
    body,
  })

  res.statusCode = response.status
  response.headers.forEach((value, key) => {
    if (!HOP_BY_HOP_HEADERS.has(key.toLowerCase())) {
      res.setHeader(key, value)
    }
  })

  const responseBuffer = Buffer.from(await response.arrayBuffer())
  res.end(responseBuffer)
}

