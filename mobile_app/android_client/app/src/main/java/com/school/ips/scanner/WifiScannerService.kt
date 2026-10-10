package com.school.ips.scanner

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.wifi.ScanResult
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import androidx.core.content.ContextCompat

data class WifiReading(
    val bssid: String,
    val ssid: String,
    val rssi: Int,
    val frequency: Int
)

/**
 * Gestor de Escaneo Activo de Redes Wi-Fi mediante WifiManager de Android.
 * Notifica a través de un listener cada vez que una nueva ráfaga de resultados esté disponible.
 */
class WifiScannerService(
    private val context: Context,
    /**
     * Recibe la ráfaga y la marca de tiempo del escaneo del sistema (microsegundos desde el
     * arranque). Android limita los escaneos a 4 cada 2 minutos: cuando deniega uno, seguimos
     * leyendo `scanResults`, que devuelve la ráfaga anterior en caché. La marca de tiempo es
     * lo único que distingue una medición nueva de una repetida.
     */
    private val onScanCompleted: (List<WifiReading>, Long) -> Unit
) {
    private val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
    private val handler = Handler(Looper.getMainLooper())
    private var isScanning = false
    private val scanIntervalMs = 1500L // Intervalo entre escaneos

    private val wifiScanReceiver = object : BroadcastReceiver() {
        override fun onReceive(c: Context?, intent: Intent?) {
            val success = intent?.getBooleanExtra(WifiManager.EXTRA_RESULTS_UPDATED, false) ?: false
            if (success) {
                processScanResults()
            }
        }
    }

    fun startContinuousScanning() {
        if (isScanning) return
        isScanning = true

        val intentFilter = IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.registerReceiver(
                context,
                wifiScanReceiver,
                intentFilter,
                ContextCompat.RECEIVER_EXPORTED
            )
        } else {
            context.registerReceiver(wifiScanReceiver, intentFilter)
        }

        triggerScan()
    }

    fun stopScanning() {
        if (!isScanning) return
        isScanning = false
        handler.removeCallbacksAndMessages(null)
        try {
            context.unregisterReceiver(wifiScanReceiver)
        } catch (e: Exception) {
            Log.w("WifiScanner", "Receiver ya desregistrado")
        }
    }

    private fun triggerScan() {
        if (!isScanning) return
        try {
            @Suppress("DEPRECATION")
            val started = wifiManager.startScan()
            if (!started) {
                // Si el SO bloqueó el escaneo por throttling, leer resultados almacenados en caché
                processScanResults()
            }
        } catch (e: SecurityException) {
            Log.e("WifiScanner", "Faltan permisos de ubicación fina: ${e.message}")
        }

        // Programar siguiente escaneo
        handler.postDelayed({ triggerScan() }, scanIntervalMs)
    }

    private fun processScanResults() {
        try {
            val rawResults: List<ScanResult> = wifiManager.scanResults ?: emptyList()
            val readings = rawResults.map { result ->
                WifiReading(
                    bssid = result.BSSID.lowercase(),
                    ssid = result.SSID,
                    rssi = result.level,
                    frequency = result.frequency
                )
            }
            // Cada ScanResult trae cuándo se vio ese AP por última vez; la más reciente de la
            // ráfaga identifica el escaneo al que pertenece.
            val scanTimestampUs = rawResults.maxOfOrNull { it.timestamp } ?: 0L
            onScanCompleted(readings, scanTimestampUs)
        } catch (e: SecurityException) {
            Log.e("WifiScanner", "Error leyendo scanResults: ${e.message}")
        }
    }
}
