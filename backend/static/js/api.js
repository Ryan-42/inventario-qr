// API client — all calls to the FastAPI backend
const BASE = '/api'

async function apiFetch(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  if (res.status === 204) return null
  return res.json()
}

// ── Admin token (localStorage, chave compartilhada com index.html) ──
const _ADMIN_KEY = 'inviq_admin_tokens'
export function getAdminToken(sessaoId) {
  try { return JSON.parse(localStorage.getItem(_ADMIN_KEY) || '{}')[sessaoId] || '' } catch { return '' }
}
export function setAdminToken(sessaoId, token) {
  try {
    const t = JSON.parse(localStorage.getItem(_ADMIN_KEY) || '{}')
    t[sessaoId] = token
    localStorage.setItem(_ADMIN_KEY, JSON.stringify(t))
  } catch {}
}

// ── Sessions ────────────────────────────────────────────────────────
export const listarSessoes = () => apiFetch('/sessoes')
export const criarSessao = (nome) => apiFetch('/sessoes', { method: 'POST', body: JSON.stringify({ nome }) })
export const buscarSessao = (id) => apiFetch(`/sessoes/${id}`)
export const statsSessao = (id) => apiFetch(`/sessoes/${id}/stats`)
export const concluirSessao = (id, adminToken) =>
  apiFetch(`/sessoes/${id}/concluir?token_admin=${encodeURIComponent(adminToken || getAdminToken(id))}`, { method: 'PATCH' })
export const cancelarSessao = (id, adminToken) =>
  apiFetch(`/sessoes/${id}/cancelar?token_admin=${encodeURIComponent(adminToken || getAdminToken(id))}`, { method: 'PATCH' })
export const deletarSessao = (id, adminToken) =>
  apiFetch(`/sessoes/${id}?token_admin=${encodeURIComponent(adminToken || getAdminToken(id))}`, { method: 'DELETE' })
export const rodadasSessao = (id) => apiFetch(`/sessoes/${id}/rodadas`)

// ── Items ────────────────────────────────────────────────────────────
export const listarItens = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/itens`)
export const buscarItem = (sessaoId, codigo) => apiFetch(`/sessoes/${sessaoId}/buscar/${encodeURIComponent(codigo)}`)
export const listarContagens = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/contagens`)
export const registrarContagem = (sessaoId, payload) =>
  apiFetch(`/sessoes/${sessaoId}/contagens`, { method: 'POST', body: JSON.stringify(payload) })

// ── Upload ──────────────────────────────────────────────────────────
export async function uploadPlanilha(sessaoId, file) {
  const form = new FormData()
  form.append('file', file)
  const tok = encodeURIComponent(getAdminToken(sessaoId))
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/upload?token_admin=${tok}`,
    { method: 'POST', body: form })
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
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/validar-planilha`, { method: 'POST', body: form })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || detail } catch {}
    throw Object.assign(new Error(detail), { status: res.status })
  }
  return res.json()
}

// ── Agents ──────────────────────────────────────────────────────────
export const analisarSessao = (sessaoId) => apiFetch(`/agentes/analisar-sessao/${sessaoId}`, { method: 'POST' })
export const chatSessao = (sessaoId, mensagem, historico = []) =>
  apiFetch(`/agentes/chat/${sessaoId}`, { method: 'POST', body: JSON.stringify({ mensagem, historico }) })
export const alertaSessao = (sessaoId, payload) =>
  apiFetch(`/agentes/alerta/${sessaoId}`, { method: 'POST', body: JSON.stringify(payload) })

// ── Export URLs (open in new tab / download) ────────────────────────
export const valorEstoqueSessao = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/valor-estoque`)
export const progressoSessao   = (sessaoId) => apiFetch(`/sessoes/${sessaoId}/progresso`)

// token_admin vai no corpo do POST — nunca na URL — para não aparecer em logs nem histórico
async function _exportFetch(sessaoId, path, filename) {
  const tok = getAdminToken(sessaoId)
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/exportar/${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token_admin: tok }),
  })
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
