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

    // UI Elements - Identidad de Alumno
    private lateinit var tvStudentInfo: TextView
    private lateinit var tvTargetRoomInfo: TextView
    private lateinit var btnConfigUser: Button

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
    // SharedPreferences igual que la IP del servidor.
    //
    // El token del dispositivo es lo que convierte esa identidad en verificable: lo entrega el
    // servidor al dar de alta el móvil y se presenta en el handshake. Mientras el servidor no
    // tenga ningún dispositivo registrado puede quedar vacío; en cuanto se registra el primero,
    // conectar sin él devuelve un cierre 4401.
    private var currentStudentId: String = DEFAULT_STUDENT_ID
    private var currentDeviceToken: String = ""
    private var currentTargetRoomId: String = DEFAULT_ROOM_ID

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
        currentStudentId = prefs.getString("student_id", DEFAULT_STUDENT_ID) ?: DEFAULT_STUDENT_ID
        currentTargetRoomId = prefs.getString("target_room_id", DEFAULT_ROOM_ID) ?: DEFAULT_ROOM_ID
        currentDeviceToken = prefs.getString("device_token", "") ?: ""
    }

    private fun initViews() {
        tvServerInfo = findViewById(R.id.tvServerInfo)
        tvConnectionStatus = findViewById(R.id.tvConnectionStatus)
        btnConfigServer = findViewById(R.id.btnConfigServer)

        tvStudentInfo = findViewById(R.id.tvStudentInfo)
        tvTargetRoomInfo = findViewById(R.id.tvTargetRoomInfo)
        btnConfigUser = findViewById(R.id.btnConfigUser)

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

        updateUserUI()

        val floorAdapter = ArrayAdapter(
            this,
            android.R.layout.simple_spinner_dropdown_item,
            arrayOf("Piso 1", "Piso 2", "Piso 3", "Piso 4")
        )
        spinnerFloor.adapter = floorAdapter

        btnConfigServer.setOnClickListener {
            showServerConfigDialog(isFirstRun = false)
        }

        btnConfigUser.setOnClickListener {
            showUserConfigDialog()
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

    private fun updateUserUI() {
        tvStudentInfo.text = "Alumno: $currentStudentId"
        tvTargetRoomInfo.text = "Destino: Aula $currentTargetRoomId"
    }

    private fun initServices() {
        wifiScanner = WifiScannerService(this) { readings ->
            latestWifiReadings = readings
            val readingsMap = readings.associate { it.bssid to it.rssi.toDouble() }

            // Potencia del AP del aula destino. Sin este dato el servidor deriva el RSSI de la
            // posición estimada y el tablero del docente acaba mostrando un valor calculado
            // como si fuera una medición de radio.
            val roomApRssi = strongestRssiForRoom(readings, currentTargetRoomId)

            // Enviar telemetría en vivo si el WebSocket está conectado
            wsClient?.sendScanVector(readingsMap, currentTargetRoomId, roomApRssi)
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

            val posX = etCoordX.text.toString().trim().toFloatOrNull() ?: 10.0f
            val posY = etCoordY.text.toString().trim().toFloatOrNull() ?: 2.0f

            CoroutineScope(Dispatchers.Main).launch {
                val result = cal.uploadCalibrationPoint(
                    rpId = rpId,
                    floorNumber = floor,
                    x = posX,
                    y = posY,
                    label = "Punto Calibrado $rpId (${posX}m, ${posY}m)"
                )
                if (result.isSuccess) {
                    tvSampleCounter.text = "Muestras recolectadas: 0 / 15"
                    Toast.makeText(this@MainActivity, "✅ Calibración guardada en servidor ($posX m, $posY m)", Toast.LENGTH_LONG).show()
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

        tvServerInfo.text = "Servidor: $currentServerIp"
        tvConnectionStatus.text = "● Conectando..."
        tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_orange_dark))

        var cleanHost = currentServerIp.trim()
        if (cleanHost.contains("/")) {
            val prefix = if (cleanHost.startsWith("https://")) "https://" else if (cleanHost.startsWith("http://")) "http://" else ""
            val withoutPrefix = cleanHost.removePrefix("https://").removePrefix("http://")
            val hostPart = withoutPrefix.split("/")[0]
            cleanHost = prefix + hostPart
        }

        val serverHttpUrl: String
        val serverWsUrl: String

        if (cleanHost.startsWith("https://")) {
            serverHttpUrl = cleanHost
            serverWsUrl = cleanHost.replaceFirst("https://", "wss://")
        } else if (cleanHost.startsWith("http://")) {
            serverHttpUrl = cleanHost
            serverWsUrl = cleanHost.replaceFirst("http://", "ws://")
        } else if (cleanHost.contains(".trycloudflare.com") || cleanHost.contains(".ngrok")) {
            serverHttpUrl = "https://$cleanHost"
            serverWsUrl = "wss://$cleanHost"
        } else if (cleanHost.contains(":")) {
            serverHttpUrl = "http://$cleanHost"
            serverWsUrl = "ws://$cleanHost"
        } else {
            serverHttpUrl = "http://$cleanHost:$currentServerPort"
            serverWsUrl = "ws://$cleanHost:$currentServerPort"
        }

        tvServerInfo.text = "Servidor: ${serverHttpUrl.replace("http://", "").replace("https://", "")}"
        tvConnectionStatus.text = "● Conectando..."
        tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_orange_dark))

        calibrator = CalibratorManager(serverHttpUrl)

        wsClient?.disconnect()
        wsClient = WebSocketClientManager(
            serverWsUrl = serverWsUrl,
            studentId = currentStudentId,
            deviceToken = currentDeviceToken,
            onFeedbackReceived = { feedback ->
                tvCurrentFloor.text = "Piso ${feedback.floorNumber}"
                tvActiveClue.text = feedback.activeClue
                tvDistance.text = String.format(java.util.Locale.US, "%.2f m restantes", feedback.distanceMeters)
                progressBarNav.progress = feedback.progressPercentage.toInt()
                tvAttendanceStatus.text = "Estado: ${feedback.attendanceStatus}"

                if (feedback.hasArrived) {
                    tvAttendanceStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark))
                }
            },
            onStatusChanged = { isConnected, errorMsg ->
                if (isConnected) {
                    tvConnectionStatus.text = "● Conectado"
                    tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_green_dark))
                } else {
                    val detail = if (!errorMsg.isNullOrEmpty()) " ($errorMsg)" else ""
                    tvConnectionStatus.text = "● Desconectado$detail"
                    tvConnectionStatus.setTextColor(ContextCompat.getColor(this, android.R.color.holo_red_dark))
                }
            }
        )

        // Conectar el WebSocket directamente sin bloquear por permisos
        wsClient?.connect()
    }

    private fun showUserConfigDialog() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 24, 48, 24)
        }

        val etStudent = EditText(this).apply {
            hint = "ID Estudiante (ej. EST_01, EST_02, EST_08)"
            setText(currentStudentId)
            setSingleLine()
        }

        val etRoom = EditText(this).apply {
            hint = "Aula Asignada (ej. S101, S202, S302)"
            setText(currentTargetRoomId)
            setSingleLine()
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = 24 }
        }

        val etToken = EditText(this).apply {
            hint = "Token del dispositivo (lo entrega el docente al darlo de alta)"
            setText(currentDeviceToken)
            setSingleLine()
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply { topMargin = 24 }
        }

        layout.addView(etStudent)
        layout.addView(etRoom)
        layout.addView(etToken)

        AlertDialog.Builder(this)
            .setTitle("Perfil de Alumno / Dispositivo")
            .setMessage(
                "Personaliza tu usuario para conectar múltiples móviles a la vez sin " +
                    "interferencias. Si el servidor exige registro, pega aquí el token que te " +
                    "dieron al dar de alta este dispositivo."
            )
            .setView(layout)
            .setPositiveButton("Guardar") { _, _ ->
                val newStudent = etStudent.text.toString().trim()
                val newRoom = etRoom.text.toString().trim().uppercase()

                // El servidor cierra el handshake con el código 4400 si el identificador no
                // cumple [A-Za-z0-9_-]{1,32}. Validarlo aquí evita que el alumno vea una
                // desconexión sin explicación.
                if (!newStudent.matches(IDENTIFIER_REGEX) || !newRoom.matches(IDENTIFIER_REGEX)) {
                    Toast.makeText(
                        this,
                        "El ID de alumno y el aula solo admiten letras, números, guion y guion bajo (máx. 32).",
                        Toast.LENGTH_LONG
                    ).show()
                    return@setPositiveButton
                }

                if (newStudent.isNotEmpty() && newRoom.isNotEmpty()) {
                    currentStudentId = newStudent
                    currentTargetRoomId = newRoom
                    currentDeviceToken = etToken.text.toString().trim()
                    prefs.edit()
                        .putString("student_id", currentStudentId)
                        .putString("target_room_id", currentTargetRoomId)
                        .putString("device_token", currentDeviceToken)
                        .apply()
                    updateUserUI()
                    updateServerConnection()
                    Toast.makeText(this, "Conectando como $currentStudentId destino $currentTargetRoomId", Toast.LENGTH_SHORT).show()
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun showServerConfigDialog(isFirstRun: Boolean = false) {
        val input = EditText(this).apply {
            hint = "Ej. 192.168.1.50 o URL de túnel"
            setText(currentServerIp)
            setSingleLine()
            setPadding(48, 36, 48, 36)
        }

        AlertDialog.Builder(this)
            .setTitle("Servidor IPS (Laptop o Túnel)")
            .setMessage("Ingresa la IP local de tu laptop (ej. 192.168.1.50) o la URL de túnel Cloudflare/ngrok:")
            .setView(input)
            .setPositiveButton("Guardar y Conectar") { _, _ ->
                val entered = input.text.toString().trim()
                if (entered.isNotEmpty()) {
                    currentServerIp = entered
                    prefs.edit().putString("server_ip", currentServerIp).apply()
                    updateServerConnection()
                    Toast.makeText(this, "Guardado: $currentServerIp", Toast.LENGTH_SHORT).show()
                }
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
