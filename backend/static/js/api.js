// API client — all calls to the FastAPI backend
const BASE = '/api'

function _jwtHeader() {
  const token = typeof getToken === 'function' ? getToken() : sessionStorage.getItem('inviq_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ..._jwtHeader(), ...options.headers },
    ...options,
  })
  if (res.status === 401) {
    sessionStorage.removeItem('inviq_token')
    sessionStorage.removeItem('inviq_admin')
    window.location.replace('/login')
    return null
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  if (res.status === 204) return null
  return res.json()
}

// ── Sessions ────────────────────────────────────────────────────────
export const listarSessoes = () => apiFetch('/sessoes')
export const criarSessao = (nome, webhookUrl) => apiFetch('/sessoes', { method: 'POST', body: JSON.stringify({ nome, webhook_url: webhookUrl || null }) })
export const buscarSessao = (id) => apiFetch(`/sessoes/${id}`)
export const statsSessao = (id) => apiFetch(`/sessoes/${id}/stats`)
export const concluirSessao = (id) => apiFetch(`/sessoes/${id}/concluir`, { method: 'PATCH' })
export const cancelarSessao = (id) => apiFetch(`/sessoes/${id}/cancelar`, { method: 'PATCH' })
export const deletarSessao = (id) => apiFetch(`/sessoes/${id}`, { method: 'DELETE' })
export const reabrirSessao = (id) => apiFetch(`/sessoes/${id}/reabrir`, { method: 'PATCH' })
export const rodadasSessao = (id) => apiFetch(`/sessoes/${id}/rodadas`)

// ── Grupos de operadores ─────────────────────────────────────────────
export const listarGrupos = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/grupos`)
export const criarGrupo = (sessaoId, payload) =>
  apiFetch(`/sessoes/${sessaoId}/grupos`, { method: 'POST', body: JSON.stringify(payload) })
export const deletarGrupo = (sessaoId, grupoId) =>
  apiFetch(`/sessoes/${sessaoId}/grupos/${grupoId}`, { method: 'DELETE' })
export const regenerarTokenGrupo = (sessaoId, grupoId) =>
  apiFetch(`/sessoes/${sessaoId}/grupos/${grupoId}/regenerar-token`, { method: 'POST' })

// ── Items ────────────────────────────────────────────────────────────
export const listarItens = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/itens`)
// token: operador mobile envia o token de acesso (admin JWT dispensa o token)
export const buscarItem = (sessaoId, codigo, token = '') => {
  const qs = token ? `?token=${encodeURIComponent(token)}` : ''
  return apiFetch(`/sessoes/${sessaoId}/buscar/${encodeURIComponent(codigo)}${qs}`)
}
export const listarContagens = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/contagens`)
// token: operador token (token_acesso, supervisor ou grupo) — obrigatório para operadores mobile
export const registrarContagem = (sessaoId, payload, token = '') => {
  const qs = token ? `?token=${encodeURIComponent(token)}` : ''
  return apiFetch(`/sessoes/${sessaoId}/contagens${qs}`, { method: 'POST', body: JSON.stringify(payload) })
}

// ── Upload ──────────────────────────────────────────────────────────
export async function uploadPlanilha(sessaoId, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/upload`, {
    method: 'POST',
    headers: _jwtHeader(),
    body: form,
  })
  if (res.status === 401) {
    sessionStorage.removeItem('inviq_token')
    window.location.replace('/login')
    return null
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return res.json()
}

export async function validarPlanilha(sessaoId, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/validar-planilha`, {
    method: 'POST',
    headers: _jwtHeader(),
    body: form,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return res.json()
}

// ── Agents ──────────────────────────────────────────────────────────
export const analisarSessao = (sessaoId) => apiFetch(`/agentes/analisar-sessao/${sessaoId}`, { method: 'POST' })
export const alertaSessao = (sessaoId, payload) =>
  apiFetch(`/agentes/alerta/${sessaoId}`, { method: 'POST', body: JSON.stringify(payload) })

// ── Stats ────────────────────────────────────────────────────────────
export const valorEstoqueSessao = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/valor-estoque`)
export const progressoSessao   = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/progresso`)

// ── Exports — JWT no header, sem body ──────────────────────────────
async function _exportFetch(sessaoId, path, filename) {
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/exportar/${path}`, {
    method: 'POST',
    headers: _jwtHeader(),
  })
  if (res.status === 401) {
    sessionStorage.removeItem('inviq_token')
    window.location.replace('/login')
    return
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}
export const exportarCompleto          = (sessaoId, nome) => _exportFetch(sessaoId, 'completo', nome || 'inventario_completo.xlsx')
export const exportarDivergencias      = (sessaoId, nome) => _exportFetch(sessaoId, 'divergencias', nome || 'divergencias.xlsx')
export const exportarPDF               = (sessaoId, nome) => _exportFetch(sessaoId, 'pdf', nome || 'relatorio.pdf')
export const exportarEtiquetas         = (sessaoId, nome) => _exportFetch(sessaoId, 'etiquetas', nome || 'etiquetas.pdf')
export const exportarRelatorioFinalPDF = (sessaoId, nome) => _exportFetch(sessaoId, 'relatorio-final-pdf', nome || 'relatorio_final.pdf')
export const exportarRelatorioFinalExcel = (sessaoId, nome) => _exportFetch(sessaoId, 'relatorio-final-excel', nome || 'relatorio_final.xlsx')

// Compat: getAdminToken / setAdminToken retornam string vazia (JWT substituiu)
export const getAdminToken = () => ''
export const setAdminToken = () => {}
