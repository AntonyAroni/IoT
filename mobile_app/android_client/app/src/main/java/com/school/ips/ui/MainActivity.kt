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
    private lateinit var spinnerFloor: Spinner

    // Configuración y Persistencia
    private val prefs by lazy { getSharedPreferences("ips_config", Context.MODE_PRIVATE) }
    private var currentServerIp: String = ""
    private val currentServerPort: Int = 8000
    private val studentId = "EST_08"
    private val targetRoomId = "S302"

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

            // Enviar telemetría en vivo si el WebSocket está conectado
            wsClient?.sendScanVector(readingsMap, targetRoomId)
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

            val cal = calibrator
            if (cal == null) {
                Toast.makeText(this, "Servicio de calibración no inicializado", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }

            CoroutineScope(Dispatchers.Main).launch {
                val result = cal.uploadCalibrationPoint(
                    rpId = rpId,
                    floorNumber = floor,
                    x = 10.0f,
                    y = 2.0f,
                    label = "Punto Calibrado $rpId"
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
        val input = EditText(this).apply {
            hint = "Ej. 192.168.1.50"
            setText(currentServerIp)
            setSingleLine()
            setPadding(48, 36, 48, 36)
        }

        AlertDialog.Builder(this)
            .setTitle("IP del Servidor (Laptop)")
            .setMessage("Ingresa la dirección IP local de tu laptop en la red actual:")
            .setView(input)
            .setPositiveButton("Guardar y Conectar") { _, _ ->
                val entered = input.text.toString().trim()
                if (entered.isNotEmpty()) {
                    // Limpiar posibles prefijos http:// o puertos accidentales
                    currentServerIp = entered.replace("http://", "").replace("https://", "").split(":")[0]
                    prefs.edit().putString("server_ip", currentServerIp).apply()
                    updateServerConnection()
                    Toast.makeText(this, "Conectando a $currentServerIp...", Toast.LENGTH_SHORT).show()
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
}
