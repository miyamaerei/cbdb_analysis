// 开发态走 Vite proxy (/api → 127.0.0.1:8787)
// 生产态由 web/server.py 同源托管，直接相对路径即可
const BASE = '/api'

async function get(path, params = {}) {
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  const res = await fetch(`${BASE}${path}${qs ? '?' + qs : ''}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
  return data
}

export const api = {
  stats: () => get('/stats'),
  views: () => get('/views'),
  view: (name, payload) => post(`/view/${name}`, payload),
  search: (q, limit = 30) => get('/search', { q, limit }),
  person: (pid) => get(`/person/${pid}`),
  timeline: (pid, opts = {}) =>
    get(`/person/${pid}/timeline`, {
      stage: opts.stages?.join(',') || '',
      prec: opts.precs?.join(',') || '',
      limit: opts.limit || 2000,
    }),
  relations: (pid) => get(`/person/${pid}/relations`),
  graph: (pid, depth = 1, limit = 120) => get(`/person/${pid}/graph`, { depth, limit }),
  presets: () => get('/presets'),
  preset: (key, pid) => get(`/preset/${key}`, { pid }),
  sql: (sql) => post('/sql', { sql }),
}
