/**
 * Cliente WebSocket Resiliente con Auto-Reconexión y Medición de Latencia.
 */
export class StationWebSocketClient {
  constructor(roomId, onMessageCallback, onStatusChangeCallback) {
    this.roomId = roomId;
    this.onMessage = onMessageCallback;
    this.onStatusChange = onStatusChangeCallback;
    this.ws = null;
    this.pingInterval = null;
    this.reconnectTimeout = null;
    this.lastPingTime = 0;
    this.latency = 0;
    this.isClosedManually = false;
  }

  connect() {
    this.isClosedManually = false;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host || 'localhost:8000';
    const url = `${protocol}//${host}/ws/laptop/${this.roomId}`;

    if (this.onStatusChange) this.onStatusChange('CONNECTING', 0);

    try {
      this.ws = new WebSocket(url);

      this.ws.onopen = () => {
        if (this.onStatusChange) this.onStatusChange('ONLINE', this.latency);
        this._startHeartbeat();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.event === 'pong') {
            this.latency = Math.round(performance.now() - this.lastPingTime);
            if (this.onStatusChange) this.onStatusChange('ONLINE', this.latency);
            return;
          }
          if (this.onMessage) this.onMessage(data);
        } catch (e) {
          console.error("Error parseando mensaje WS:", e);
        }
      };

      this.ws.onclose = () => {
        this._stopHeartbeat();
        if (this.onStatusChange) this.onStatusChange('OFFLINE', 0);
        if (!this.isClosedManually) {
          this.reconnectTimeout = setTimeout(() => this.connect(), 2500);
        }
      };

      this.ws.onerror = (err) => {
        console.warn("WebSocket error en estación:", err);
      };

    } catch (e) {
      console.error("No se pudo iniciar WebSocket:", e);
      if (this.onStatusChange) this.onStatusChange('OFFLINE', 0);
    }
  }

  changeRoom(newRoomId) {
    this.disconnect();
    this.roomId = newRoomId;
    this.connect();
  }

  _startHeartbeat() {
    this._stopHeartbeat();
    this.pingInterval = setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.lastPingTime = performance.now();
        this.ws.send(JSON.stringify({ action: 'ping' }));
      }
    }, 5000);
  }

  _stopHeartbeat() {
    if (this.pingInterval) clearInterval(this.pingInterval);
    if (this.reconnectTimeout) clearTimeout(this.reconnectTimeout);
  }

  disconnect() {
    this.isClosedManually = true;
    this._stopHeartbeat();
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}
