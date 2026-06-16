/**
 * auth.js — utilitários de autenticação JWT para o dashboard INVIQ.
 * Carregue antes de qualquer fetch autenticado.
 */

const AUTH_TOKEN_KEY = 'inviq_token'
const AUTH_ADMIN_KEY = 'inviq_admin'
const LOGIN_PATH     = '/login'

/** Retorna o JWT armazenado ou null. */
function getToken() {
  return sessionStorage.getItem(AUTH_TOKEN_KEY)
}

/** Retorna os dados do admin logado ou null. */
function getAdmin() {
  try {
    return JSON.parse(sessionStorage.getItem(AUTH_ADMIN_KEY) || 'null')
  } catch {
    return null
  }
}

/**
 * Verifica se o usuário está autenticado. Se não estiver, redireciona para /login.
 * Retorna o token caso esteja autenticado.
 */
function checkAuth() {
  const token = getToken()
  if (!token || _tokenExpirado(token)) {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    sessionStorage.removeItem(AUTH_ADMIN_KEY)
    window.location.replace(LOGIN_PATH)
    return null
  }
  return token
}

/** Decodifica o payload do JWT (sem verificar assinatura) para ler exp. */
function _tokenExpirado(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return payload.exp && Date.now() / 1000 > payload.exp
  } catch {
    return true
  }
}

/** Retorna o objeto de headers Authorization para usar no fetch. */
function authHeaders(extra = {}) {
  const token = getToken()
  if (!token) return extra
  return { Authorization: `Bearer ${token}`, ...extra }
}

/**
 * Wrapper sobre fetch que injeta o header Authorization automaticamente.
 * Redireciona para /login em caso de 401.
 */
async function fetchAuth(url, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) }
  const res = await fetch(url, { ...options, headers })
  if (res.status === 401) {
    sessionStorage.removeItem(AUTH_TOKEN_KEY)
    sessionStorage.removeItem(AUTH_ADMIN_KEY)
    window.location.replace(LOGIN_PATH)
    return res
  }
  return res
}

/** Faz logout: revoga o token no servidor e limpa o sessionStorage. */
async function logout() {
  try {
    await fetchAuth('/auth/logout', { method: 'POST' })
  } catch { /* ignora erros de rede no logout */ }
  sessionStorage.removeItem(AUTH_TOKEN_KEY)
  sessionStorage.removeItem(AUTH_ADMIN_KEY)
  window.location.replace(LOGIN_PATH)
}

/** Inicia aviso de expiração: alerta quando faltam < 15 min, desconecta ao expirar. */
function iniciarAvisoToken() {
  setInterval(() => {
    const token = getToken()
    if (!token) return
    try {
      const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
      const restante = payload.exp - Date.now() / 1000
      if (restante <= 0) {
        logout()
      } else if (restante < 900) {
        // Avisa só uma vez por sessão
        if (!sessionStorage.getItem('inviq_aviso_exp')) {
          sessionStorage.setItem('inviq_aviso_exp', '1')
          const min = Math.ceil(restante / 60)
          if (confirm(`Sua sessão expira em ${min} minuto(s). Deseja continuar logado?`)) {
            sessionStorage.removeItem('inviq_aviso_exp')
          } else {
            logout()
          }
        }
      }
    } catch { /* token malformado */ }
  }, 60_000)
}
