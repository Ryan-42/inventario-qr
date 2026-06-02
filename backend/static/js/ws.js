// WebSocket client for real-time session updates
export class SessionWS {
  constructor(sessaoId, onEvent) {
    this._sessaoId = sessaoId
    this._onEvent = onEvent
    this._ws = null
    this._reconnectTimer = null
    this._heartbeatTimer = null
    this._intentionalClose = false
    this._connected = false
    this._reconnectDelay = 2000
  }

  get connected() { return this._connected }

  connect() {
    this._intentionalClose = false
    this._reconnectDelay = 2000
    this._open()
  }

  disconnect() {
    this._intentionalClose = true
    clearTimeout(this._reconnectTimer)
    clearInterval(this._heartbeatTimer)
    if (this._ws) { this._ws.close(); this._ws = null }
    this._connected = false
  }

  _startHeartbeat() {
    clearInterval(this._heartbeatTimer)
    this._heartbeatTimer = setInterval(() => {
      if (this._ws && this._ws.readyState === WebSocket.OPEN) {
        try { this._ws.send(JSON.stringify({ tipo: 'ping' })) } catch {}
      }
    }, 25000) // ping a cada 25s para manter conexão viva
  }

  _open() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/api/ws/${this._sessaoId}`
    try { this._ws = new WebSocket(url) } catch { this._scheduleReconnect(); return }

    this._ws.onopen = () => {
      this._connected = true
      this._reconnectDelay = 2000
      this._startHeartbeat()
      this._onEvent({ tipo: '_connected' })
    }
    this._ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.tipo === 'pong') return
        this._onEvent(data)
      } catch (err) {
        console.error('[INVIQ WS] Falha ao parsear mensagem:', err.message, '| raw:', e.data?.slice?.(0, 200))
        // Notifica o handler sem quebrar o fluxo
        this._onEvent({ tipo: '_parse_error', message: 'Mensagem inválida recebida do servidor' })
      }
    }
    this._ws.onclose = (ev) => {
      this._connected = false
      clearInterval(this._heartbeatTimer)
      this._onEvent({ tipo: '_disconnected', code: ev.code })
      if (!this._intentionalClose) this._scheduleReconnect()
    }
    this._ws.onerror = (err) => {
      console.warn('[INVIQ WS] Erro na conexão WebSocket:', err)
    }
  }

  _scheduleReconnect() {
    clearTimeout(this._reconnectTimer)
    this._reconnectTimer = setTimeout(() => {
      this._reconnectDelay = Math.min(this._reconnectDelay * 1.5, 15000)
      this._open()
    }, this._reconnectDelay)
  }

  // Reconecta manualmente (ex: ao voltar do background no mobile)
  reconnect() {
    if (this._connected) return
    clearTimeout(this._reconnectTimer)
    this._reconnectDelay = 2000
    this._open()
  }
}
