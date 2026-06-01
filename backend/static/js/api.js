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

// ── Sessions ────────────────────────────────────────────────────────
export const listarSessoes = () => apiFetch('/sessoes')
export const criarSessao = (nome) => apiFetch('/sessoes', { method: 'POST', body: JSON.stringify({ nome }) })
export const buscarSessao = (id) => apiFetch(`/sessoes/${id}`)
export const statsSessao = (id) => apiFetch(`/sessoes/${id}/stats`)
export const concluirSessao = (id) => apiFetch(`/sessoes/${id}/concluir`, { method: 'PATCH' })
export const cancelarSessao = (id) => apiFetch(`/sessoes/${id}/cancelar`, { method: 'PATCH' })
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
  const res = await fetch(`${BASE}/sessoes/${sessaoId}/upload`, { method: 'POST', body: form })
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

export const exportarCompleto = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/completo`
export const exportarDivergencias = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/divergencias`
export const exportarPDF = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/pdf`
export const exportarEtiquetas = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/etiquetas`
export const exportarRelatorioFinalPDF = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/relatorio-final-pdf`
export const exportarRelatorioFinalExcel = (sessaoId) => `${BASE}/sessoes/${sessaoId}/exportar/relatorio-final-excel`
