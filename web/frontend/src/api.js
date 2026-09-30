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

  // 知识图谱（kg/api_server.py，经 web/server.py 同源代理 /api/kg）
  kgHealth: () => get('/kg/health'),
  kgDynasties: () => get('/kg/dynasties'),
  kgQuads: () => get('/kg/quads'),
  kgSearch: (body) => post('/kg/search', body),
  kgPerson: (id) => get(`/kg/person/${id}`),
  kgTopics: () => get('/kg/topics'),
  kgTopic: (body) => post('/kg/topic', body),
  // 导出：返回 CSV 文件（非 JSON），由调用方触发浏览器下载
  kgExport: (body) =>
    fetch(`${BASE}/kg/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => {
      if (!r.ok) {
        return r.json().then((e) => { throw new Error(e.error || `HTTP ${r.status}`) })
      }
      const cd = r.headers.get('Content-Disposition') || ''
      const m = cd.match(/filename="?([^"]+)"?/)
      const fname = m ? m[1] : 'cbdb_kg_export.csv'
      return r.blob().then((b) => ({ blob: b, fname }))
    }),
  // 构建（ETL）：SSE 流式。onEvent 收到每个事件 {log} / {done} / {error}
  kgBuild: (body, onEvent) =>
    fetch(`${BASE}/kg/build`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => {
      if (!r.ok) {
        return r.text().then((t) => { throw new Error(t || `HTTP ${r.status}`) })
      }
      const reader = r.body.getReader()
      const dec = new TextDecoder('utf-8')
      let buf = ''
      return new Promise((resolve, reject) => {
        const pump = () =>
          reader.read().then(({ done, value }) => {
            if (done) return resolve()
            buf += dec.decode(value, { stream: true })
            let i
            while ((i = buf.indexOf('\n\n')) !== -1) {
              const evt = buf.slice(0, i)
              buf = buf.slice(i + 2)
              const line = evt.split('\n').find((l) => l.startsWith('data:'))
              if (line) {
                try { onEvent(JSON.parse(line.slice(5).trim())) } catch (e) { /* ignore */ }
              }
            }
            return pump()
          }).catch(reject)
        pump()
      })
    }),
}
