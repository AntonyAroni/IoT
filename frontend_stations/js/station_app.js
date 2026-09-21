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
    this.calibrationPoints = [];
    this.pointsFloorFilter = 'all';
    this.pointsSearchQuery = '';
    this.currentRoomData = null;

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

    // Botón y Filtros de Puntos de Calibración
    const btnManagePoints = document.getElementById('btnManagePoints');
    if (btnManagePoints) {
      btnManagePoints.addEventListener('click', () => this.openPointsModal());
    }

    const filterContainer = document.getElementById('pointsFloorFilter');
    if (filterContainer) {
      filterContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('pill-btn')) {
          filterContainer.querySelectorAll('.pill-btn').forEach(btn => btn.classList.remove('active'));
          e.target.classList.add('active');
          this.pointsFloorFilter = e.target.getAttribute('data-floor');
          this.renderCalibrationPointsTable();
        }
      });
    }

    const searchInput = document.getElementById('pointsSearchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.pointsSearchQuery = e.target.value.toLowerCase().trim();
        this.renderCalibrationPointsTable();
      });
    }

    const btnClearAll = document.getElementById('btnClearAllPoints');
    if (btnClearAll) {
      btnClearAll.addEventListener('click', () => this.confirmClearRadioMap());
    }

    const btnRestore = document.getElementById('btnRestoreBaseline');
    if (btnRestore) {
      btnRestore.addEventListener('click', () => this.confirmRestoreBaseline());
    }

    // Botones de Mapeo de Aula
    const btnAssignRp = document.getElementById('btnAssignRpToRoom');
    if (btnAssignRp) {
      btnAssignRp.addEventListener('click', () => this.assignSelectedRpToRoom());
    }

    const btnSaveManualCoords = document.getElementById('btnSaveManualRoomCoords');
    if (btnSaveManualCoords) {
      btnSaveManualCoords.addEventListener('click', () => this.saveManualRoomCoords());
    }

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
    this._fetchRoomCoordinates();

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

  async _fetchRoomCoordinates() {
    try {
      const res = await fetch(`/api/v1/building/room/${this.currentRoom}`);
      if (res.ok) {
        const data = await res.json();
        this.currentRoomData = data;
        const coordsElem = document.getElementById('roomCoordsText');
        if (coordsElem && data.center) {
          coordsElem.textContent = `(${Number(data.center.x).toFixed(2)}, ${Number(data.center.y).toFixed(2)}) m`;
        }
      }
    } catch (e) {
      console.warn("No se pudieron cargar coordenadas del aula:", e);
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
      if (msg.room_position) {
        const coordsElem = document.getElementById('roomCoordsText');
        if (coordsElem) {
          coordsElem.textContent = `(${Number(msg.room_position.x).toFixed(2)}, ${Number(msg.room_position.y).toFixed(2)}) m`;
        }
      }
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

  showConfirmDialog({ title, message, warningText = '', confirmText = 'Confirmar', isDanger = false, onConfirm }) {
    const modal = document.getElementById('modalConfirm');
    const titleEl = document.getElementById('confirmModalTitle');
    const messageEl = document.getElementById('confirmModalMessage');
    const warningEl = document.getElementById('confirmModalWarning');
    const btnOk = document.getElementById('btnConfirmOk');
    const btnCancel = document.getElementById('btnConfirmCancel');

    if (!modal) return;

    titleEl.textContent = title;
    messageEl.textContent = message;
    if (warningText) {
      warningEl.textContent = warningText;
      warningEl.style.display = 'block';
    } else {
      warningEl.style.display = 'none';
    }

    btnOk.textContent = confirmText;
    btnOk.style.background = isDanger ? '#dc2626' : '#0284c7';

    modal.style.display = 'flex';

    const cleanup = () => {
      modal.style.display = 'none';
      btnOk.replaceWith(btnOk.cloneNode(true));
      btnCancel.replaceWith(btnCancel.cloneNode(true));
    };

    // Usar nuevo elemento para no acumular listeners
    const freshBtnOk = document.getElementById('btnConfirmOk');
    const freshBtnCancel = document.getElementById('btnConfirmCancel');

    freshBtnCancel.addEventListener('click', () => {
      cleanup();
    }, { once: true });

    freshBtnOk.addEventListener('click', async () => {
      cleanup();
      if (onConfirm) await onConfirm();
    }, { once: true });
  }

  async openPointsModal() {
    const modal = document.getElementById('modalPoints');
    if (modal) modal.style.display = 'flex';
    await this.loadCalibrationPoints();
  }

  closePointsModal() {
    const modal = document.getElementById('modalPoints');
    if (modal) modal.style.display = 'none';
  }

  async loadCalibrationPoints() {
    try {
      const res = await fetch('/api/v1/calibration/radio-map');
      if (res.ok) {
        this.calibrationPoints = await res.json();
        this.renderCalibrationPointsTable();
      }
    } catch (e) {
      console.error("Error al cargar puntos de calibración:", e);
    }
  }

  renderCalibrationPointsTable() {
    const tbody = document.getElementById('pointsTableBody');
    const totalBadge = document.getElementById('pointsTotalBadge');
    if (!tbody) return;

    let filtered = this.calibrationPoints || [];
    if (this.pointsFloorFilter !== 'all') {
      const floor = parseInt(this.pointsFloorFilter, 10);
      filtered = filtered.filter(p => p.floor_number === floor);
    }

    if (this.pointsSearchQuery) {
      const q = this.pointsSearchQuery;
      filtered = filtered.filter(p =>
        (p.id && p.id.toLowerCase().includes(q)) ||
        (p.label && p.label.toLowerCase().includes(q)) ||
        (p.room_id && p.room_id.toLowerCase().includes(q))
      );
    }

    if (totalBadge) {
      totalBadge.textContent = `${filtered.length} / ${this.calibrationPoints.length} puntos`;
    }

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#94a3b8; padding: 24px;">No se encontraron puntos de control.</td></tr>`;
      return;
    }

    // Ordenar por piso ascendente, luego por ID
    const sorted = [...filtered].sort((a, b) => a.floor_number - b.floor_number || a.id.localeCompare(b.id));

    const fragment = document.createDocumentFragment();
    sorted.forEach(p => {
      const tr = document.createElement('tr');

      const isTest = p.id.toUpperCase().includes('TEST') || p.id.toUpperCase().includes('PRUEBA');

      // ID
      const tdId = document.createElement('td');
      tdId.innerHTML = `<strong style="color: ${isTest ? '#f87171' : '#38bdf8'}">${p.id}</strong>${isTest ? ' <span style="background: rgba(239,68,68,0.2); color: #fca5a5; font-size: 0.68rem; padding: 1px 5px; border-radius: 4px; font-weight: 700;">TEST</span>' : ''}`;
      tr.appendChild(tdId);

      // Piso
      const tdFloor = document.createElement('td');
      tdFloor.innerHTML = `<span style="background: #1e293b; border: 1px solid #334155; padding: 2px 8px; border-radius: 4px; font-weight: 600;">Piso ${p.floor_number}</span>`;
      tr.appendChild(tdFloor);

      // Posición X, Y (lectura robusta de p.position.x o p.x)
      const posX = (p.position && p.position.x !== undefined) ? p.position.x : (p.x !== undefined ? p.x : 0);
      const posY = (p.position && p.position.y !== undefined) ? p.position.y : (p.y !== undefined ? p.y : 0);
      const tdPos = document.createElement('td');
      tdPos.style.fontFamily = 'monospace';
      tdPos.textContent = `(${Number(posX).toFixed(2)}, ${Number(posY).toFixed(2)})`;
      tr.appendChild(tdPos);

      // Salón / Etiqueta
      const tdLabel = document.createElement('td');
      if (p.room_id) {
        tdLabel.innerHTML = `<span style="background: rgba(14, 165, 233, 0.15); color: #38bdf8; border: 1px solid rgba(14, 165, 233, 0.3); padding: 1px 6px; border-radius: 4px; font-weight: 700; font-size: 0.72rem; margin-right: 6px;">Aula ${p.room_id}</span>${p.label}`;
      } else {
        tdLabel.textContent = p.label;
      }
      tr.appendChild(tdLabel);

      // APs / Muestras
      const tdAps = document.createElement('td');
      const apCount = p.rssi_means ? Object.keys(p.rssi_means).length : 0;
      tdAps.innerHTML = `<span style="color: #94a3b8;">${apCount} APs (${p.sample_count || 15} m.)</span>`;
      tr.appendChild(tdAps);

      // Acción: Botón Asignar a Aula + Botón Eliminar
      const tdAction = document.createElement('td');
      tdAction.style.whiteSpace = 'nowrap';

      const btnAssign = document.createElement('button');
      btnAssign.className = 'btn-delete-point';
      btnAssign.style.background = 'rgba(56, 189, 248, 0.12)';
      btnAssign.style.color = '#38bdf8';
      btnAssign.style.borderColor = 'rgba(56, 189, 248, 0.3)';
      btnAssign.style.marginRight = '6px';
      btnAssign.innerHTML = '📍 Aula';
      btnAssign.title = `Asignar ${p.id} como centro del aula activa (${this.currentRoom})`;
      btnAssign.addEventListener('click', () => this.quickAssignPointToRoom(p.id));
      tdAction.appendChild(btnAssign);

      const btnDelete = document.createElement('button');
      btnDelete.className = 'btn-delete-point';
      btnDelete.innerHTML = '🗑️';
      btnDelete.title = `Eliminar punto ${p.id}`;
      btnDelete.addEventListener('click', () => this.confirmDeleteCalibrationPoint(p.id));
      tdAction.appendChild(btnDelete);
      tr.appendChild(tdAction);

      fragment.appendChild(tr);
    });

    tbody.replaceChildren(fragment);
  }

  confirmDeleteCalibrationPoint(rpId) {
    this.showConfirmDialog({
      title: '⚠️ Eliminar Punto de Control',
      message: `¿Estás seguro de que deseas eliminar el punto de control "${rpId}" del radio-mapa?`,
      warningText: 'Esta acción borrará la huella de señal de forma permanente para evitar contaminación de pruebas.',
      confirmText: 'Sí, Eliminar Punto',
      isDanger: true,
      onConfirm: async () => {
        try {
          const res = await fetch(`/api/v1/calibration/point/${encodeURIComponent(rpId)}`, {
            method: 'DELETE'
          });
          if (res.ok) {
            this.logAudit(`🗑️ Punto de calibración '${rpId}' eliminado exitosamente.`);
            await this.loadCalibrationPoints();
          } else {
            const err = await res.json().catch(() => ({}));
            alert(`Error al eliminar: ${err.detail || res.statusText}`);
          }
        } catch (e) {
          console.error("Error al eliminar punto de calibración:", e);
        }
      }
    });
  }

  confirmClearRadioMap() {
    this.showConfirmDialog({
      title: '🚨 ALERTA DE SEGURIDAD: Vaciar Radio-Mapa',
      message: '¿Estás completamente seguro de que deseas ELIMINAR TODOS los puntos de control y lecturas RSSI? El mapa quedará completamente vacío (0 puntos) para iniciar un mapeo general desde cero.',
      warningText: '⚠️ Acción destructiva de alto impacto. Se creará automáticamente un respaldo (.backup) para que puedas restaurarlo cuando gustes.',
      confirmText: 'Sí, Vaciar Todo (0 Puntos)',
      isDanger: true,
      onConfirm: async () => {
        try {
          const res = await fetch('/api/v1/calibration/radio-map', { method: 'DELETE' });
          if (res.ok) {
            this.logAudit('🚨 Radio-mapa vaciado por completo. Base de datos en 0 puntos para mapeo inicial.');
            await this.loadCalibrationPoints();
          } else {
            const err = await res.json().catch(() => ({}));
            alert(`Error al vaciar radio-mapa: ${err.detail || res.statusText}`);
          }
        } catch (e) {
          console.error("Error al vaciar radio-mapa:", e);
        }
      }
    });
  }

  confirmRestoreBaseline() {
    this.showConfirmDialog({
      title: '🔄 Restaurar Respaldo del Radio-Mapa',
      message: '¿Deseas restaurar el radio-mapa desde la copia de respaldo guardada?',
      warningText: 'Esta acción reemplazará los puntos actuales con el respaldo previo.',
      confirmText: 'Restaurar Puntos',
      isDanger: false,
      onConfirm: async () => {
        try {
          const res = await fetch('/api/v1/calibration/restore-baseline', { method: 'POST' });
          const data = await res.json();
          if (res.ok && data.status === 'success') {
            this.logAudit(`🔄 ${data.message}`);
            await this.loadCalibrationPoints();
          } else {
            alert(data.message || 'No se encontró copia de respaldo previa.');
          }
        } catch (e) {
          console.error("Error al restaurar respaldo:", e);
        }
      }
    });
  }

  resetRoomAttendance() {
    this.showConfirmDialog({
      title: `Reiniciar Asistencia - Aula ${this.currentRoom}`,
      message: `¿Estás seguro de reiniciar los registros de asistencia del aula ${this.currentRoom}? Todos los alumnos matriculados volverán al estado Ausente y se limpiarán los radares.`,
      warningText: 'Esta acción descartará las asistencias registradas en la sesión activa.',
      confirmText: 'Sí, Reiniciar Aula',
      isDanger: true,
      onConfirm: async () => {
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
    });
  }

  openMapRoomModal() {
    const modal = document.getElementById('modalMapRoom');
    if (!modal) return;
    const titleSpan = document.getElementById('mapRoomModalId');
    if (titleSpan) titleSpan.textContent = this.currentRoom;

    // Poblar select con los puntos calibrados existentes
    const select = document.getElementById('selectRpToRoom');
    if (select) {
      select.innerHTML = '<option value="">-- Selecciona un punto de control --</option>';
      (this.calibrationPoints || []).forEach(p => {
        const posX = (p.position && p.position.x !== undefined) ? p.position.x : (p.x !== undefined ? p.x : 0);
        const posY = (p.position && p.position.y !== undefined) ? p.position.y : (p.y !== undefined ? p.y : 0);
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = `${p.id} (${Number(posX).toFixed(2)}, ${Number(posY).toFixed(2)}) - ${p.label}`;
        select.appendChild(opt);
      });
    }

    // Pre-poblar inputs manuales con las coordenadas actuales del aula
    if (this.currentRoomData) {
      const cx = document.getElementById('inputRoomCenterX');
      const cy = document.getElementById('inputRoomCenterY');
      const ex = document.getElementById('inputRoomEntranceX');
      const ey = document.getElementById('inputRoomEntranceY');
      if (cx && this.currentRoomData.center) cx.value = this.currentRoomData.center.x;
      if (cy && this.currentRoomData.center) cy.value = this.currentRoomData.center.y;
      if (ex && this.currentRoomData.entrance) ex.value = this.currentRoomData.entrance.x;
      if (ey && this.currentRoomData.entrance) ey.value = this.currentRoomData.entrance.y;
    }

    modal.style.display = 'flex';
  }

  closeMapRoomModal() {
    const modal = document.getElementById('modalMapRoom');
    if (modal) modal.style.display = 'none';
  }

  async assignSelectedRpToRoom() {
    const select = document.getElementById('selectRpToRoom');
    const roleSelect = document.getElementById('selectRpRole');
    const rpId = select ? select.value : '';
    const role = roleSelect ? roleSelect.value : 'center';

    if (!rpId) {
      alert("Por favor selecciona un punto de control para asignar.");
      return;
    }

    try {
      const res = await fetch(`/api/v1/building/room/${this.currentRoom}/position`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ from_rp_id: rpId, rp_role: role })
      });
      if (res.ok) {
        const roleLabel = role === 'entrance' ? 'Puerta' : 'Centro / Laptop';
        this.logAudit(`📍 Punto '${rpId}' asignado como ${roleLabel} del aula ${this.currentRoom}.`);
        await this._fetchRoomCoordinates();
        await this.loadCalibrationPoints();
        this.closeMapRoomModal();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Error al asignar punto: ${err.detail || res.statusText}`);
      }
    } catch (e) {
      console.error("Error al asignar punto a aula:", e);
    }
  }

  async saveManualRoomCoords() {
    const cx = parseFloat(document.getElementById('inputRoomCenterX')?.value);
    const cy = parseFloat(document.getElementById('inputRoomCenterY')?.value);
    const ex = parseFloat(document.getElementById('inputRoomEntranceX')?.value);
    const ey = parseFloat(document.getElementById('inputRoomEntranceY')?.value);

    const payload = {};
    if (!isNaN(cx) && !isNaN(cy)) {
      payload.center_x = cx;
      payload.center_y = cy;
    }
    if (!isNaN(ex) && !isNaN(ey)) {
      payload.entrance_x = ex;
      payload.entrance_y = ey;
    }

    if (Object.keys(payload).length === 0) {
      alert("Ingresa al menos un par de coordenadas válidas (X, Y).");
      return;
    }

    try {
      const res = await fetch(`/api/v1/building/room/${this.currentRoom}/position`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        this.logAudit(`📐 Coordenadas físicas del aula ${this.currentRoom} actualizadas.`);
        await this._fetchRoomCoordinates();
        this.closeMapRoomModal();
      } else {
        const err = await res.json().catch(() => ({}));
        alert(`Error al guardar coordenadas: ${err.detail || res.statusText}`);
      }
    } catch (e) {
      console.error("Error al guardar coordenadas:", e);
    }
  }

  quickAssignPointToRoom(rpId) {
    this.showConfirmDialog({
      title: `📍 Asignar a Aula ${this.currentRoom}`,
      message: `¿Deseas fijar el punto "${rpId}" como la posición de referencia (Centro / Laptop) del aula ${this.currentRoom}?`,
      warningText: 'Las distancias en tiempo real y el radar se calcularán con respecto a este punto calibrado.',
      confirmText: 'Sí, Fijar como Centro',
      isDanger: false,
      onConfirm: async () => {
        try {
          const res = await fetch(`/api/v1/building/room/${this.currentRoom}/position`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ from_rp_id: rpId, rp_role: 'center' })
          });
          if (res.ok) {
            this.logAudit(`📍 Punto '${rpId}' asignado como Centro de ${this.currentRoom}.`);
            await this._fetchRoomCoordinates();
            await this.loadCalibrationPoints();
          } else {
            const err = await res.json().catch(() => ({}));
            alert(`Error: ${err.detail || res.statusText}`);
          }
        } catch (e) {
          console.error("Error en asignación rápida:", e);
        }
      }
    });
  }
}

// Exponer helpers para onclick inline de HTML
window.openPointsModal = () => window.app?.openPointsModal();
window.closePointsModal = () => window.app?.closePointsModal();
window.openMapRoomModal = () => window.app?.openMapRoomModal();
window.closeMapRoomModal = () => window.app?.closeMapRoomModal();

document.addEventListener('DOMContentLoaded', () => {
  window.app = new StationDashboardApp();
});
