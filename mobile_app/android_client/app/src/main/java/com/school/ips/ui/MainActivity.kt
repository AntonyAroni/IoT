package com.school.ips.ui

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.school.ips.R
import com.school.ips.calibration.CalibratorManager
import com.school.ips.network.WebSocketClientManager
import com.school.ips.scanner.WifiReading
import com.school.ips.scanner.WifiScannerService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private val permissionRequestCode = 1001

    private lateinit var wifiScanner: WifiScannerService
    private var calibrator: CalibratorManager? = null
    private var wsClient: WebSocketClientManager? = null

    // UI Elements - Cabecera y Servidor
    private lateinit var tvServerInfo: TextView
    private lateinit var tvConnectionStatus: TextView
    private lateinit var btnConfigServer: Button

    // UI Elements - Navegación
    private lateinit var tvCurrentFloor: TextView
    private lateinit var tvActiveClue: TextView
    private lateinit var tvDistance: TextView
    private lateinit var progressBarNav: ProgressBar
    private lateinit var tvAttendanceStatus: TextView

    // UI Elements - Calibrador
    private lateinit var btnToggleCalibrator: Button
    private lateinit var layoutCalibrator: LinearLayout
    private lateinit var btnTakeSample: Button
    private lateinit var btnUploadCalibration: Button
    private lateinit var tvSampleCounter: TextView
    private lateinit var etRpId: EditText
    private lateinit var etCoordX: EditText
    private lateinit var etCoordY: EditText
    private lateinit var spinnerFloor: Spinner

    // Configuración y Persistencia
    private val prefs by lazy { getSharedPreferences("ips_config", Context.MODE_PRIVATE) }
    private var currentServerIp: String = ""
    private val currentServerPort: Int = 8000

    // Identidad del alumno y aula asignada. Estaban fijados como constantes, de modo que todo
    // dispositivo con el APK instalado se identificaba como el mismo alumno. Se persisten en
    // SharedPreferences igual que la IP del servidor, y el diálogo inicial los solicita.
    // Nota: esto identifica, no autentica. El servidor acepta cualquier identificador que se le
    // envíe; añadir un token por alumno sigue pendiente.
    private var studentId: String = DEFAULT_STUDENT_ID
    private var targetRoomId: String = DEFAULT_ROOM_ID

    // Buffer de últimas lecturas Wi-Fi recibidas
    private var latestWifiReadings: List<WifiReading> = emptyList()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        loadSavedServerConfig()
        initViews()
        initServices()
        checkAndRequestPermissions()

        // Si es la primera vez o no hay IP guardada, solicitarla al usuario
        if (currentServerIp.isEmpty()) {
            showServerConfigDialog(isFirstRun = true)
        }
    }

    private fun loadSavedServerConfig() {
        currentServerIp = prefs.getString("server_ip", "") ?: ""
        studentId = prefs.getString("student_id", DEFAULT_STUDENT_ID) ?: DEFAULT_STUDENT_ID
        targetRoomId = prefs.getString("target_room_id", DEFAULT_ROOM_ID) ?: DEFAULT_ROOM_ID
    }

    private fun initViews() {
        tvServerInfo = findViewById(R.id.tvServerInfo)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        btnConfigServer = findViewById(R.id.btnConfigServer)

        tvCurrentFloor = findViewById(R.id.tvCurrentFloor)
        tvActiveClue = findViewById(R.id.tvActiveClue)
        tvDistance = findViewById(R.id.tvDistance)
        progressBarNav = findViewById(R.id.progressBarNav)
        tvAttendanceStatus = findViewById(R.id.tvAttendanceStatus)

        btnToggleCalibrator = findViewById(R.id.btnToggleCalibrator)
        layoutCalibrator = findViewById(R.id.layoutCalibrator)
        btnTakeSample = findViewById(R.id.btnTakeSample)
        btnUploadCalibration = findViewById(R.id.btnUploadCalibration)
        tvSampleCounter = findViewById(R.id.tvSampleCounter)
        etRpId = findViewById(R.id.etRpId)
        etCoordX = findViewById(R.id.etCoordX)
        etCoordY = findViewById(R.id.etCoordY)
        spinnerFloor = findViewById(R.id.spinnerFloor)

        val floorAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            arrayOf("Piso 1", "Piso 2", "Piso 3", "Piso 4")
        )
        spinnerFloor.adapter = floorAdapter

        btnConfigServer.setOnClickListener {
            showServerConfigDialog(isFirstRun = false)
        }

        btnToggleCalibrator.setOnClickListener {
            if (layoutCalibrator.visibility == View.VISIBLE) {
                layoutCalibrator.visibility = View.GONE
                btnToggleCalibrator.text = "Modo Calibrador (Offline)"
            } else {
                layoutCalibrator.visibility = View.VISIBLE
                btnToggleCalibrator.text = "Volver a Navegación"
            }
        }
    }

    private fun initServices() {
        wifiScanner = WifiScannerService(this) { readings ->
            latestWifiReadings = readings
            val readingsMap = readings.associate { it.bssid to it.rssi.toDouble() }

            // Potencia del AP del aula destino. Sin este dato el servidor deriva el RSSI de la
            // posición estimada y el tablero del docente acaba mostrando un valor calculado
            // como si fuera una medición de radio.
            val roomApRssi = strongestRssiForRoom(readings, targetRoomId)

            // Enviar telemetría en vivo si el WebSocket está conectado
            wsClient?.sendScanVector(readingsMap, targetRoomId, roomApRssi)
        }

        updateServerConnection()

        btnTakeSample.setOnClickListener {
            if (latestWifiReadings.isEmpty()) {
                Toast.makeText(this, "Escaneando redes Wi-Fi... espera un momento e intenta de nuevo.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            val count = calibrator?.addSample(latestWifiReadings) ?: 0
            tvSampleCounter.text = "Muestras recolectadas: $count / 15"
            if (count >= 15) {
                Toast.makeText(this, "¡15 muestras listas! Ya puedes presionar 'Enviar Huella'.", Toast.LENGTH_LONG).show()
            } else {
                Toast.makeText(this, "Muestra $count / 15 registrada", Toast.LENGTH_SHORT).show()
            }
        }

        btnUploadCalibration.setOnClickListener {
            val rpId = etRpId.text.toString().trim()
            val floor = spinnerFloor.selectedItemPosition + 1
            if (rpId.isEmpty()) {
                Toast.makeText(this, "Ingresa un ID para el punto (ej. RP_S302_Center)", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (currentServerIp.isEmpty()) {
                Toast.makeText(this, "Configura primero la IP de la laptop.", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            // Las coordenadas son obligatorias: un punto de referencia sin posición real no
            // sirve para nada, ni para el WKNN ni para la validación. Antes estaban fijadas en
            // el código y las capturas de campo se guardaban todas en (10.0, 2.0).
            val coordX = etCoordX.text.toString().trim().toFloatOrNull()
            val coordY = etCoordY.text.toString().trim().toFloatOrNull()
            if (coordX == null || coordY == null) {
                Toast.makeText(
                    this,
                    "Indica las coordenadas X e Y del punto, en metros. Sin posición real la " +
                        "huella no sirve como punto de referencia.",
                    Toast.LENGTH_LONG
                ).show()
                return@setOnClickListener
            }

            val cal = calibrator
            if (cal == null) {
                Toast.makeText(this, "Servicio de calibración no inicializado", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            CoroutineScope(Dispatchers.Main).launch {
                val result = cal.uploadCalibrationPoint(
                    rpId = rpId,
                    floorNumber = floor,
                    x = coordX,
                    y = coordY,
                    label = "Punto Calibrado $rpId (${coordX}m, ${coordY}m)"
                )
                if (result.isSuccess) {
                    tvSampleCounter.text = "Muestras recolectadas: 0 / 15"
                    Toast.makeText(this@MainActivity, "✅ Calibración guardada en servidor", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@MainActivity, "❌ Error al subir: ${result.exceptionOrNull()?.message}", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }

    private fun updateServerConnection() {
        if (currentServerIp.isEmpty()) {
            tvServerInfo.text = "Servidor: Toca 'Cambiar IP'"
            tvConnectionStatus.text = "● Sin IP"
            tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_dark))
            return
        }

        tvServerInfo.text = "Servidor: $currentServerIp:$currentServerPort"
        tvConnectionStatus.text = "● Conectando..."
        tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_orange_dark))

        val serverHttpUrl = "http://$currentServerIp:$currentServerPort"
        val serverWsUrl = "ws://$currentServerIp:$currentServerPort"

        calibrator = CalibratorManager(serverHttpUrl)

        wsClient?.disconnect()
        wsClient = WebSocketClientManager(
            serverWsUrl = serverWsUrl,
            studentId = studentId,
            onFeedbackReceived = { feedback ->
                tvCurrentFloor.text = "Piso ${feedback.floorNumber}"
                tvActiveClue.text = feedback.activeClue
                tvDistance.text = "${feedback.distanceMeters} m restantes"
                progressBarNav.progress = feedback.progressPercentage.toInt()
                tvAttendanceStatus.text = "Estado: ${feedback.attendanceStatus}"

                if (feedback.hasArrived) {
                    tvAttendanceStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark))
                }
            },
            onStatusChanged = { isConnected ->
                if (isConnected) {
                    tvConnectionStatus.text = "● Conectado"
                    tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark))
                } else {
                    tvConnectionStatus.text = "● Desconectado"
                    tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_dark))
                }
            }
        )

        // Conectar si los permisos ya fueron otorgados
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
            wsClient?.connect()
        }
    }

    private fun showServerConfigDialog(isFirstRun: Boolean = false) {
        val ipInput = EditText(this).apply {
            hint = "IP del servidor, ej. 192.168.1.50"
            setText(currentServerIp)
            setSingleLine()
        }
        val studentInput = EditText(this).apply {
            hint = "Tu código de alumno, ej. EST_08"
            setText(studentId)
            setSingleLine()
        }
        val roomInput = EditText(this).apply {
            hint = "Aula asignada, ej. S302"
            setText(targetRoomId)
            setSingleLine()
        }

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 36, 48, 12)
            addView(ipInput)
            addView(studentInput)
            addView(roomInput)
        }

        AlertDialog.Builder(this)
            .setTitle("Configuración del Sensor")
            .setMessage("Dirección del servidor en la red local e identidad del alumno:")
            .setView(container)
            .setPositiveButton("Guardar y Conectar") { _, _ ->
                val enteredIp = ipInput.text.toString().trim()
                if (enteredIp.isNotEmpty()) {
                    // Limpiar posibles prefijos http:// o puertos accidentales
                    currentServerIp = enteredIp.replace("http://", "").replace("https://", "").split(":")[0]
                }

                // El servidor rechaza identificadores fuera de [A-Za-z0-9_-]{1,32}, así que se
                // descartan aquí los valores que harían fallar el handshake sin explicación.
                val enteredStudent = studentInput.text.toString().trim()
                if (enteredStudent.matches(IDENTIFIER_REGEX)) {
                    studentId = enteredStudent
                }
                val enteredRoom = roomInput.text.toString().trim()
                if (enteredRoom.matches(IDENTIFIER_REGEX)) {
                    targetRoomId = enteredRoom
                }

                prefs.edit()
                    .putString("server_ip", currentServerIp)
                    .putString("student_id", studentId)
                    .putString("target_room_id", targetRoomId)
                    .apply()

                updateServerConnection()
                Toast.makeText(
                    this,
                    "Conectando a $currentServerIp como $studentId (aula $targetRoomId)...",
                    Toast.LENGTH_SHORT
                ).show()
            }
            .setNegativeButton(if (isFirstRun) "Configurar luego" else "Cancelar") { dialog, _ ->
                dialog.dismiss()
            }
            .setCancelable(!isFirstRun)
            .show()
    }

    private fun checkAndRequestPermissions() {
        val permissions = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.ACCESS_WIFI_STATE,
            Manifest.permission.CHANGE_WIFI_STATE
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            permissions.add(Manifest.permission.NEARBY_WIFI_DEVICES)
        }

        val missing = permissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), permissionRequestCode)
        } else {
            startScanningPipeline()
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == permissionRequestCode && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) {
            startScanningPipeline()
        } else {
            Toast.makeText(this, "Los permisos de ubicación y Wi-Fi son indispensables.", Toast.LENGTH_LONG).show()
        }
    }

    private fun startScanningPipeline() {
        wifiScanner.startContinuousScanning()
        if (currentServerIp.isNotEmpty()) {
            wsClient?.connect()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        wifiScanner.stopScanning()
        wsClient?.disconnect()
    }

    /**
     * Localiza la potencia del punto de acceso del aula destino dentro de un escaneo.
     *
     * Los AP de aula siguen el convenio de nombre `AP_AULA_<numero>` en el SSID, y en el
     * radio-mapa sintético el BSSID `ap_p<piso>_room<indice>`. Se acepta cualquiera de los dos
     * para que funcione tanto con la infraestructura real como con el simulador.
     *
     * Devuelve null si el AP del aula no aparece en el escaneo, que es lo correcto: el servidor
     * marcará entonces el RSSI como estimado en lugar de presentarlo como medido.
     */
    private fun strongestRssiForRoom(readings: List<WifiReading>, roomId: String): Double? {
        // "S302" -> piso 3, aula 02
        val digits = roomId.filter { it.isDigit() }
        if (digits.length < 3) return null
        val floor = digits.first()
        val roomIndex = digits.substring(1)

        val bssidConvention = "ap_p${floor}_room${roomIndex}"
        val ssidConvention = "AP_AULA_${floor}${roomIndex}"

        return readings
            .filter { it.bssid.equals(bssidConvention, ignoreCase = true) ||
                      it.ssid.equals(ssidConvention, ignoreCase = true) }
            .maxByOrNull { it.rssi }
            ?.rssi
            ?.toDouble()
    }

    companion object {
        private const val DEFAULT_STUDENT_ID = "EST_08"
        private const val DEFAULT_ROOM_ID = "S302"

        /** Mismo alfabeto que valida el backend antes de aceptar el handshake del WebSocket. */
        private val IDENTIFIER_REGEX = Regex("^[A-Za-z0-9_-]{1,32}$")
    }
}
