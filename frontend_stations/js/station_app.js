/**
 * Orquestador Principal del Dashboard de Aula en Laptop (Fase 2).
 */
import { RadarWidget } from './radar_widget.js';
import { StationWebSocketClient } from './ws_client.js';
import { audioService } from './audio_service.js';

class StationDashboardApp {
  constructor() {
    this.currentRoom = this._getRoomFromUrl() || 'S302';
    this.records = new Map(); // student_id -> record
    this.radar = null;
    this.wsClient = null;

    this._initElements();
    this._bindEvents();
    this._initDashboard();
  }

  _getRoomFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return params.get('room');
  }

  _initElements() {
    this.roomSelect = document.getElementById('roomSelect');
    this.roomTitle = document.getElementById('roomTitle');
    this.statusDot = document.getElementById('statusDot');
    this.statusText = document.getElementById('statusText');
    this.latencyBadge = document.getElementById('latencyBadge');

    // Métricas
    this.metricEnrolled = document.getElementById('metricEnrolled');
    this.metricConfirmed = document.getElementById('metricConfirmed');
    this.metricApproaching = document.getElementById('metricApproaching');
    this.metricRate = document.getElementById('metricRate');

    // Tabla y Logs
    this.tableBody = document.getElementById('attendanceTableBody');
    this.auditList = document.getElementById('auditList');
    this.lastStudentTelemetry = document.getElementById('lastStudentTelemetry');
  }

  _bindEvents() {
    this.roomSelect.value = this.currentRoom;
    this.roomSelect.addEventListener('change', (e) => {
      this.currentRoom = e.target.value;
      const url = new URL(window.location);
      url.searchParams.set('room', this.currentRoom);
      window.history.pushState({}, '', url);
      this._updateRoomView();
    });

    // Botones de Simulación Interactiva
    document.getElementById('btnSimApproaching').addEventListener('click', () => this.simulateEvent('APPROACHING', -66.0, 7.5));
    document.getElementById('btnSimDoor').addEventListener('click', () => this.simulateEvent('AT_DOOR', -53.0, 2.8));
    document.getElementById('btnSimConfirm').addEventListener('click', () => this.simulateEvent('PRESENT_CONFIRMED', -46.0, 1.2));
    document.getElementById('btnResetRoom').addEventListener('click', () => this.resetRoomAttendance());

    // Modal de Conexión Móvil
    const modal = document.getElementById('modalConnect');
    const btnConnect = document.getElementById('btnConnectMobile');
    const btnClose = document.getElementById('btnCloseModal');
    const btnOk = document.getElementById('btnModalOk');

    if (btnConnect) {
      btnConnect.addEventListener('click', async () => {
        modal.style.display = 'flex';
        try {
          const res = await fetch('/api/v1/network/info');
          if (res.ok) {
            const net = await res.json();
            document.getElementById('detectedServerIp').textContent = `${net.primary_ip}:${net.server_port}`;
            const ipItems = net.available_ips.map(item => `<span>${item.type}: <strong>${item.ip}</strong></span>`).join(' | ');
            document.getElementById('detectedAllIps').innerHTML = `IPs detectadas: ${ipItems}`;
          }
        } catch (e) {
          document.getElementById('detectedServerIp').textContent = window.location.host;
        }
      });
    }

    if (btnClose) btnClose.addEventListener('click', () => { modal.style.display = 'none'; });
    if (btnOk) btnOk.addEventListener('click', () => { modal.style.display = 'none'; });
  }

  _initDashboard() {
    this.radar = new RadarWidget('radarCanvas');
    this._updateRoomView();
  }

  _updateRoomView() {
    this.roomTitle.textContent = `Aula ${this.currentRoom}`;
    this.records.clear();
    this._renderEmptyTable('Cargando padrón del aula...');

    if (this.wsClient) {
      this.wsClient.changeRoom(this.currentRoom);
    } else {
      this.wsClient = new StationWebSocketClient(
        this.currentRoom,
        (msg) => this.handleMessage(msg),
        (status, latency) => this.handleConnectionStatus(status, latency)
      );
      this.wsClient.connect();
    }
  }

  handleConnectionStatus(status, latency) {
    if (status === 'ONLINE') {
      this.statusDot.className = 'status-dot online';
      this.statusText.textContent = 'En Línea';
      this.latencyBadge.textContent = `${latency} ms`;
    } else if (status === 'CONNECTING') {
      this.statusDot.className = 'status-dot';
      this.statusText.textContent = 'Conectando...';
      this.latencyBadge.textContent = '--';
    } else {
      this.statusDot.className = 'status-dot';
      this.statusText.textContent = 'Desconectado';
      this.latencyBadge.textContent = '--';
    }
  }

  handleMessage(msg) {
    if (msg.event === 'initial_state') {
      this._loadInitialState(msg.records || []);
    } else if (msg.event === 'student_proximity') {
      this._processProximityEvent(msg);
    }
  }

  _loadInitialState(records) {
    this.records.clear();
    records.forEach(r => this.records.set(r.student_id, r));
    this._renderTable();
    this._updateMetrics();
    this.logAudit(`📋 Padrón cargado: ${records.length} alumnos matriculados en ${this.currentRoom}.`);
  }

  _processProximityEvent(data) {
    const studentId = data.student_id;
    let rec = this.records.get(studentId);
    if (!rec) {
      rec = {
        student_id: studentId,
        student_name: data.student_name,
        room_id: this.currentRoom,
        status: data.status,
        last_seen: data.timestamp,
        last_rssi: data.rssi,
        samples_in_window: data.samples_in_window,
        confirmed_at: data.confirmed_at
      };
      this.records.set(studentId, rec);
    }

    const prevStatus = rec.status;
    rec.status = data.status;
    rec.last_seen = data.timestamp;
    rec.last_rssi = data.rssi;
    rec.samples_in_window = data.samples_in_window;
    if (data.confirmed_at) rec.confirmed_at = data.confirmed_at;

    // Actualizar Radar
    this.radar.updateTarget(studentId, data.student_name, data.status, data.rssi, data.distance_to_classroom);

    // Audio síntesis reactivo
    if (prevStatus !== data.status) {
      if (data.status === 'PRESENT_CONFIRMED') {
        audioService.playSuccessChime();
      } else if (data.status === 'APPROACHING' || data.status === 'AT_DOOR') {
        audioService.playSonarPing();
      }
    }

    // Telemetría en el pie del radar
    const distFmt = (data.distance_to_classroom !== undefined && data.distance_to_classroom !== null) 
      ? Number(data.distance_to_classroom).toFixed(2) 
      : '--';
    this.lastStudentTelemetry.textContent = `Último sensor: ${data.student_name} | RSSI: ${data.rssi} dBm | Dist: ${distFmt} m | Estado: ${data.status}`;

    // Log de auditoría
    if (data.audit_message) {
      this.logAudit(data.audit_message);
    }

    this._renderTable();
    this._updateMetrics();
  }

  _updateMetrics() {
    const total = this.records.size;
    let confirmed = 0;
    let approaching = 0;

    this.records.forEach(r => {
      if (r.status === 'PRESENT_CONFIRMED') confirmed++;
      if (r.status === 'APPROACHING' || r.status === 'AT_DOOR') approaching++;
    });

    this.metricEnrolled.textContent = total;
    this.metricConfirmed.textContent = confirmed;
    this.metricApproaching.textContent = approaching;
    const pct = total > 0 ? Math.round((confirmed / total) * 100) : 0;
    this.metricRate.textContent = `${pct}%`;
  }

  /**
   * Construye una celda de tabla insertando el texto como nodo de texto.
   *
   * Nunca usar innerHTML aquí: student_id y student_name proceden del servidor y su origen
   * último es la ruta del WebSocket del móvil, que es texto libre. Interpolarlos como HTML
   * permitía ejecutar código en la laptop del docente.
   */
  _buildCell(text, { bold = false, className = null, style = null } = {}) {
    const td = document.createElement('td');
    const target = bold ? document.createElement('strong') : td;

    if (className) {
      const span = document.createElement('span');
      span.className = className;
      span.textContent = text;
      td.appendChild(span);
      return td;
    }

    target.textContent = text;
    if (bold) td.appendChild(target);
    if (style) td.setAttribute('style', style);
    return td;
  }

  _renderEmptyTable(message) {
    this.tableBody.replaceChildren();
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 5;
    td.setAttribute('style', 'text-align: center; color: #9ca3af;');
    td.textContent = message;
    tr.appendChild(td);
    this.tableBody.appendChild(tr);
  }

  _renderTable() {
    if (this.records.size === 0) {
      this._renderEmptyTable('No hay alumnos registrados.');
      return;
    }

    const fragment = document.createDocumentFragment();

    this.records.forEach(r => {
      let badgeClass = 'tag-absent';
      let badgeLabel = 'Ausente';

      if (r.status === 'APPROACHING') {
        badgeClass = 'tag-approaching';
        badgeLabel = 'En Camino';
      } else if (r.status === 'AT_DOOR') {
        badgeClass = 'tag-at-door';
        badgeLabel = `En Puerta (${r.samples_in_window}/3)`;
      } else if (r.status === 'PRESENT_CONFIRMED') {
        badgeClass = 'tag-present';
        badgeLabel = 'Presente ✓';
      }

      const timeStr = r.confirmed_at
        ? new Date(r.confirmed_at * 1000).toLocaleTimeString()
        : (r.last_seen ? new Date(r.last_seen * 1000).toLocaleTimeString() : '--');

      // El sufijo "est." distingue una potencia medida de una derivada de la posición
      // estimada, para no presentar un valor calculado como si fuera una medición de radio.
      let rssiStr = '--';
      if (r.last_rssi !== null && r.last_rssi !== undefined) {
        rssiStr = r.rssi_is_measured === false
          ? `${r.last_rssi} dBm est.`
          : `${r.last_rssi} dBm`;
      }

      const tr = document.createElement('tr');
      tr.appendChild(this._buildCell(r.student_id, { bold: true }));
      tr.appendChild(this._buildCell(r.student_name));
      tr.appendChild(this._buildCell(badgeLabel, { className: `status-tag ${badgeClass}` }));
      tr.appendChild(this._buildCell(rssiStr, { style: 'font-family: monospace; color: #38bdf8;' }));
      tr.appendChild(this._buildCell(timeStr, { style: 'color: #9ca3af;' }));
      fragment.appendChild(tr);
    });

    this.tableBody.replaceChildren(fragment);
  }

  logAudit(msg) {
    const li = document.createElement('li');
    const time = new Date().toLocaleTimeString();
    li.textContent = `[${time}] ${msg}`;
    this.auditList.prepend(li);
  }

  async simulateEvent(status, rssi, distance) {
    // Simula evento en tiempo real en la UI y radar
    const simData = {
      event: 'student_proximity',
      timestamp: Date.now() / 1000,
      student_id: 'EST_08',
      student_name: 'Diego Ramos (Demo Player)',
      status: status,
      floor_number: parseInt(this.currentRoom.charAt(1)),
      rssi: rssi,
      distance_to_classroom: distance,
      samples_in_window: status === 'PRESENT_CONFIRMED' ? 3 : (status === 'AT_DOOR' ? 1 : 0),
      confirmed_at: status === 'PRESENT_CONFIRMED' ? Date.now() / 1000 : null,
      audit_message: `[SIMULACIÓN] Alumno Diego Ramos cambió estado a: ${status} (RSSI: ${rssi} dBm)`
    };
    this._processProximityEvent(simData);
  }

  async resetRoomAttendance() {
    try {
      const resp = await fetch(`/api/v1/attendance/room/${this.currentRoom}/reset`, { method: 'POST' });
      if (resp.ok) {
        this.records.forEach(r => {
          r.status = 'ABSENT';
          r.last_rssi = null;
          r.confirmed_at = null;
          r.samples_in_window = 0;
          this.radar.clearTarget(r.student_id);
        });
        this._renderTable();
        this._updateMetrics();
        this.logAudit(`🔄 Se ha reiniciado la asistencia para el ${this.currentRoom}.`);
      }
    } catch (e) {
      console.error("Error al reiniciar aula:", e);
    }
  }
}

document.addEventListener('DOMContentLoaded', () => {
  window.app = new StationDashboardApp();
});
