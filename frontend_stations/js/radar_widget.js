/**
 * Radar Sonar Widget (Canvas 2D).
 * Visualiza la proximidad física y de radiofrecuencia (RSSI) del estudiante
 * en anillos concéntricos en tiempo real.
 */
export class RadarWidget {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.sweepAngle = 0;
    this.targets = new Map(); // student_id -> { rssi, status, name, angle, distanceNorm, alpha }
    this.animationId = null;

    this._resizeCanvas();
    window.addEventListener('resize', () => this._resizeCanvas());
    this._startLoop();
  }

  _resizeCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const size = Math.min(rect.width, 360);
    this.canvas.width = size * window.devicePixelRatio;
    this.canvas.height = size * window.devicePixelRatio;
    this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);
    this.size = size;
    this.center = size / 2;
    this.maxRadius = (size / 2) - 15;
  }

  updateTarget(studentId, name, status, rssi, distanceMeters) {
    let target = this.targets.get(studentId);
    if (!target) {
      target = {
        name: name,
        angle: Math.random() * Math.PI * 2,
        alpha: 1.0
      };
      this.targets.set(studentId, target);
    }

    target.status = status;
    target.rssi = rssi;
    target.name = name;

    // Normalizar distancia métrica o RSSI a radio visual (0 = centro del aula, 1 = borde exterior)
    if (status === 'PRESENT_CONFIRMED') {
      target.distanceNorm = 0.15; // Dentro del aula
    } else if (status === 'AT_DOOR') {
      target.distanceNorm = 0.35; // Umbral de puerta
    } else if (status === 'APPROACHING') {
      target.distanceNorm = 0.65; // Pasillo
    } else {
      target.distanceNorm = 0.92; // Zona lejana
    }
  }

  clearTarget(studentId) {
    this.targets.delete(studentId);
  }

  _startLoop() {
    const render = () => {
      this._draw();
      this.sweepAngle = (this.sweepAngle + 0.03) % (Math.PI * 2);
      this.animationId = requestAnimationFrame(render);
    };
    render();
  }

  _draw() {
    const ctx = this.ctx;
    const c = this.center;
    const maxR = this.maxRadius;

    ctx.clearRect(0, 0, this.size, this.size);

    // 1. Dibujar Anillos Concéntricos
    const rings = [
      { r: maxR * 0.3, label: 'Aula (≥ -55 dBm)', color: 'rgba(16, 185, 129, 0.25)' },
      { r: maxR * 0.65, label: 'Pasillo (-70 dBm)', color: 'rgba(59, 130, 246, 0.2)' },
      { r: maxR * 0.95, label: 'Lejano', color: 'rgba(107, 114, 128, 0.15)' }
    ];

    rings.forEach(ring => {
      ctx.beginPath();
      ctx.arc(c, c, ring.r, 0, Math.PI * 2);
      ctx.strokeStyle = ring.color;
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });

    // 2. Líneas cruzadas de orientación
    ctx.beginPath();
    ctx.moveTo(c - maxR, c);
    ctx.lineTo(c + maxR, c);
    ctx.moveTo(c, c - maxR);
    ctx.lineTo(c, c + maxR);
    ctx.strokeStyle = 'rgba(55, 65, 81, 0.4)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // 3. Haz de Sonar Giratorio
    const gradient = ctx.createRadialGradient(c, c, 0, c, c, maxR);
    gradient.addColorStop(0, 'rgba(6, 182, 212, 0)');
    gradient.addColorStop(1, 'rgba(6, 182, 212, 0.15)');

    ctx.save();
    ctx.beginPath();
    ctx.moveTo(c, c);
    ctx.arc(c, c, maxR, this.sweepAngle - 0.4, this.sweepAngle);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();
    ctx.restore();

    // 4. Centro: Estación / Laptop
    ctx.beginPath();
    ctx.arc(c, c, 6, 0, Math.PI * 2);
    ctx.fillStyle = '#06b6d4';
    ctx.fill();
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.stroke();

    // 5. Dibujar Objetivos (Alumnos detectados)
    this.targets.forEach((t, id) => {
      const r = maxR * (t.distanceNorm || 0.85);
      const x = c + Math.cos(t.angle) * r;
      const y = c + Math.sin(t.angle) * r;

      let color = '#9ca3af'; // Absent
      if (t.status === 'APPROACHING') color = '#3b82f6';
      if (t.status === 'AT_DOOR') color = '#f59e0b';
      if (t.status === 'PRESENT_CONFIRMED') color = '#10b981';

      // Pulso exterior
      ctx.beginPath();
      ctx.arc(x, y, 10, 0, Math.PI * 2);
      ctx.fillStyle = color + '44';
      ctx.fill();

      // Punto central
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Etiqueta de Nombre y RSSI
      ctx.fillStyle = '#f3f4f6';
      ctx.font = '10px system-ui';
      ctx.textAlign = 'center';
      const label = `${t.name.split(' ')[0]} (${t.rssi ? t.rssi + ' dBm' : '--'})`;
      ctx.fillText(label, x, y - 12);
    });
  }
}
