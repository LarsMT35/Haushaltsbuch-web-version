// Schmaler API-Client – Fachlogik liegt ausschließlich im Backend (Prinzip 6).
const BASE = '/api/v1'

export function getToken() {
  return localStorage.getItem('token')
}

export function setToken(token) {
  if (token) localStorage.setItem('token', token)
  else localStorage.removeItem('token')
}

async function request(method, path, { json, form, params } = {}) {
  const url = new URL(BASE + path, window.location.origin)
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v === null || v === undefined || v === '') continue
      // Arrays -> wiederholter Query-Key (FastAPI list[...]-Parameter, z.B.
      // mehrere Konten/Kategorien gleichzeitig filtern)
      if (Array.isArray(v)) {
        for (const item of v) url.searchParams.append(k, item)
      } else {
        url.searchParams.set(k, v)
      }
    }
  }
  const headers = {}
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  let body
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  } else if (form !== undefined) {
    body = form // FormData – Content-Type setzt der Browser
  }
  const res = await fetch(url, { method, headers, body })
  if (res.status === 401) {
    setToken(null)
    window.location.hash = '#/login'
    throw new Error('Sitzung abgelaufen')
  }
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch { /* leer */ }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  const type = res.headers.get('content-type') || ''
  return type.includes('application/json') ? res.json() : res.text()
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, json) => request('POST', path, { json }),
  postForm: (path, form) => request('POST', path, { form }),
  put: (path, json) => request('PUT', path, { json }),
  del: (path, params) => request('DELETE', path, { params }),
}

export async function login(username, password) {
  const body = new URLSearchParams({ username, password })
  const res = await fetch(BASE + '/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  if (!res.ok) {
    let detail = 'Anmeldung fehlgeschlagen'
    try { detail = (await res.json()).detail || detail } catch { /* leer */ }
    throw new Error(detail)
  }
  const data = await res.json()
  setToken(data.access_token)
  return data
}

export function exportUrl(params) {
  const url = new URL(BASE + '/transactions/export.csv', window.location.origin)
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== null && v !== undefined && v !== '') url.searchParams.set(k, v)
  }
  return url.toString()
}

export function fmtAmount(value) {
  return Number(value).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' })
}

export function fmtDate(iso) {
  if (!iso) return ''
  const [y, m, d] = iso.split('-')
  return `${d}.${m}.${y}`
}
