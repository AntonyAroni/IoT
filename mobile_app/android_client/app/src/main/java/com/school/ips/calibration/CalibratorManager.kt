package com.school.ips.calibration

import com.school.ips.scanner.WifiReading
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlin.math.pow
import kotlin.math.sqrt

/**
 * Gestor del Modo Mapeo / Calibrador Offline.
 * Recolecta ráfagas de 15 muestras en el punto de referencia físico,
 * calcula promedio y varianza, y sincroniza con el backend central.
 */
class CalibratorManager(
    private val serverBaseUrl: String
) {
    private val collectedSamples = mutableListOf<List<WifiReading>>()
    private val targetSampleCount = 15
    private var lastAcceptedScanUs = 0L

    /** Resultado de intentar añadir una muestra: si entró y cuántas van acumuladas. */
    data class SampleOutcome(val accepted: Boolean, val count: Int)

    /**
     * Acumula una ráfaga solo si procede de un escaneo distinto al anterior.
     *
     * Con la limitación de escaneos de Android activa, pulsar el botón 15 veces seguidas
     * guardaba 15 copias de la misma medición: la huella parecía tener desviación típica casi
     * nula y el radio-mapa quedaba con una confianza que no se corresponde con la realidad.
     */
    fun addSample(readings: List<WifiReading>, scanTimestampUs: Long): SampleOutcome {
        if (scanTimestampUs != 0L && scanTimestampUs == lastAcceptedScanUs) {
            return SampleOutcome(accepted = false, count = collectedSamples.size)
        }
        if (collectedSamples.size < targetSampleCount) {
            collectedSamples.add(readings)
            lastAcceptedScanUs = scanTimestampUs
        }
        return SampleOutcome(accepted = true, count = collectedSamples.size)
    }

    fun isReadyToUpload(): Boolean = collectedSamples.size >= targetSampleCount

    fun reset() {
        collectedSamples.clear()
        lastAcceptedScanUs = 0L
    }

    suspend fun uploadCalibrationPoint(
        rpId: String,
        floorNumber: Int,
        x: Float,
        y: Float,
        label: String,
        roomId: String? = null,
        adminToken: String = ""
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            // Calcular estadísticas (Media y Desviación Estándar por BSSID).
            //
            // Sesgo de supervivencia: promediar solo las ráfagas en las que el AP fue detectado
            // le atribuye la media de sus lecturas más fuertes, no su potencia real. Un AP visto
            // en 2 de 15 ráfagas obtenía así una media optimista. El sesgo golpea justo a los AP
            // débiles, que son los que discriminan el piso en la clasificación jerárquica.
            //
            // Cada ráfaga en la que el AP no apareció aporta ABSENT_RSSI_DBM, coherente con el
            // `default_absent_rssi` que aplica el motor WKNN del servidor al comparar vectores.
            val totalSamples = collectedSamples.size
            val bssidMap = mutableMapOf<String, MutableList<Double>>()
            val detectionCount = mutableMapOf<String, Int>()

            for (sample in collectedSamples) {
                for (reading in sample) {
                    bssidMap.getOrPut(reading.bssid) { mutableListOf() }.add(reading.rssi.toDouble())
                    detectionCount[reading.bssid] = (detectionCount[reading.bssid] ?: 0) + 1
                }
            }

            val rssiMeans = JSONObject()
            val rssiStd = JSONObject()
            val detectionRates = JSONObject()

            for ((bssid, observed) in bssidMap) {
                val timesDetected = detectionCount[bssid] ?: 0
                val detectionRate = timesDetected.toDouble() / totalSamples

                // Un AP presente en muy pocas ráfagas es ruido, no una referencia estable:
                // incluirlo introduce más varianza de la que aporta en capacidad discriminante.
                if (detectionRate < MIN_DETECTION_RATE) continue

                // Imputar el valor suelo por cada ráfaga en la que no se detectó.
                val values = observed.toMutableList()
                repeat(totalSamples - timesDetected) { values.add(ABSENT_RSSI_DBM) }

                val mean = values.average()
                val variance = values.map { (it - mean).pow(2) }.average()
                val std = sqrt(variance)

                rssiMeans.put(bssid, Math.round(mean * 100.0) / 100.0)
                rssiStd.put(bssid, Math.round(std * 100.0) / 100.0)
                detectionRates.put(bssid, Math.round(detectionRate * 100.0) / 100.0)
            }

            // Construir payload JSON
            val jsonPayload = JSONObject().apply {
                put("rp_id", rpId)
                put("floor_number", floorNumber)
                put("x", x.toDouble())
                put("y", y.toDouble())
                put("label", label)
                if (roomId != null) put("room_id", roomId)
                put("rssi_means", rssiMeans)
                put("rssi_std", rssiStd)
                put("sample_count", collectedSamples.size)
            }

            // Enviar POST HTTP al backend
            val url = URL("$serverBaseUrl/api/v1/calibration/record")
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json")
                // Escribir en el radio-mapa es una operación de administración: desde la red
                // solo se acepta con este token. Sin él, el servidor únicamente atiende a
                // peticiones de la propia máquina y la subida se rechaza con 403.
                if (adminToken.isNotEmpty()) {
                    setRequestProperty("X-Admin-Token", adminToken)
                }
                doOutput = true
                connectTimeout = 5000
                readTimeout = 5000
            }

            OutputStreamWriter(conn.outputStream).use { writer ->
                writer.write(jsonPayload.toString())
                writer.flush()
            }

            val responseCode = conn.responseCode
            if (responseCode in 200..299) {
                reset()
                Result.success("Punto $rpId calibrado y guardado exitosamente.")
            } else if (responseCode == 401 || responseCode == 403) {
                Result.failure(Exception(
                    "El servidor rechazó la subida (HTTP $responseCode). Revisa el token de " +
                        "administrador: debe coincidir con IPS_ADMIN_TOKEN del servidor."
                ))
            } else {
                Result.failure(Exception("Error en servidor: HTTP $responseCode"))
            }

        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    companion object {
        /**
         * Valor imputado para las ráfagas en las que un AP no fue detectado.
         * Coincide con `WKNNConfig.default_absent_rssi` del servidor, de modo que el vector
         * calibrado y el vector en línea usan la misma convención para la ausencia.
         */
        private const val ABSENT_RSSI_DBM = -105.0

        /** Fracción mínima de ráfagas en las que un AP debe aparecer para entrar al radio-mapa. */
        private const val MIN_DETECTION_RATE = 0.30
    }
}
