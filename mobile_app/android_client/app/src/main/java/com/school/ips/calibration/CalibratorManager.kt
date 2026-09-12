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

    fun addSample(readings: List<WifiReading>): Int {
        if (collectedSamples.size < targetSampleCount) {
            collectedSamples.add(readings)
        }
        return collectedSamples.size
    }

    fun isReadyToUpload(): Boolean = collectedSamples.size >= targetSampleCount

    fun reset() {
        collectedSamples.clear()
    }

    suspend fun uploadCalibrationPoint(
        rpId: String,
        floorNumber: Int,
        x: Float,
        y: Float,
        label: String,
        roomId: String? = null
    ): Result<String> = withContext(Dispatchers.IO) {
        try {
            // Calcular estadísticas (Media y Desviación Estándar por BSSID)
            val bssidMap = mutableMapOf<String, MutableList<Double>>()
            for (sample in collectedSamples) {
                for (reading in sample) {
                    bssidMap.getOrPut(reading.bssid) { mutableListOf() }.add(reading.rssi.toDouble())
                }
            }

            val rssiMeans = JSONObject()
            val rssiStd = JSONObject()

            for ((bssid, values) in bssidMap) {
                val mean = values.average()
                val variance = values.map { (it - mean).pow(2) }.average()
                val std = sqrt(variance)

                rssiMeans.put(bssid, Math.round(mean * 100.0) / 100.0)
                rssiStd.put(bssid, Math.round(std * 100.0) / 100.0)
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
            } else {
                Result.failure(Exception("Error en servidor: HTTP $responseCode"))
            }

        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}
