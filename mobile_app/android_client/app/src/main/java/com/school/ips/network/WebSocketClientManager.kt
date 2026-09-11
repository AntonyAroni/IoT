package com.school.ips.network

import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.*
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class MobileNavigationFeedback(
    val floorNumber: Int,
    val floorConfidence: Double,
    val activeClue: String,
    val progressPercentage: Double,
    val distanceMeters: Double,
    val hasArrived: Boolean,
    val attendanceStatus: String
)

/**
 * Cliente WebSocket Android con OkHttp.
 * Envía vectores Wi-Fi en vivo al backend y recibe pistas de navegación en tiempo real.
 */
class WebSocketClientManager(
    private val serverWsUrl: String,
    private val studentId: String,
    private val onFeedbackReceived: (MobileNavigationFeedback) -> Unit,
    private val onStatusChanged: (Boolean) -> Unit
) {
    private var webSocket: WebSocket? = null
    private val client = OkHttpClient.Builder()
        .pingInterval(10, TimeUnit.SECONDS)
        .connectTimeout(5, TimeUnit.SECONDS)
        .build()

    private val handler = Handler(Looper.getMainLooper())
    private var isConnected = false

    fun connect() {
        val fullUrl = "$serverWsUrl/ws/mobile/$studentId"
        val request = Request.Builder().url(fullUrl).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isConnected = true
                handler.post { onStatusChanged(true) }
                Log.i("WSClient", "Conectado al Cerebro IPS.")
            }

            override fun onMessage(ws: WebSocket, text: String) {
                try {
                    val json = JSONObject(text)
                    if (json.optString("event") == "location_update") {
                        val feedback = MobileNavigationFeedback(
                            floorNumber = json.optInt("floor_number", 1),
                            floorConfidence = json.optDouble("floor_confidence", 1.0),
                            activeClue = json.optString("active_clue", "Sigue avanzando..."),
                            progressPercentage = json.optDouble("progress_percentage", 0.0),
                            distanceMeters = json.optDouble("distance_meters", 0.0),
                            hasArrived = json.optBoolean("has_arrived", false),
                            attendanceStatus = json.optString("attendance_status", "ABSENT")
                        )
                        handler.post { onFeedbackReceived(feedback) }
                    }
                } catch (e: Exception) {
                    Log.e("WSClient", "Error parseando feedback: ${e.message}")
                }
            }

            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                isConnected = false
                handler.post { onStatusChanged(false) }
                Log.w("WSClient", "Fallo en conexión WS: ${t.message}. Reintentando...")
                handler.postDelayed({ connect() }, 3000)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                isConnected = false
                handler.post { onStatusChanged(false) }
            }
        })
    }

    fun sendScanVector(readingsMap: Map<String, Double>, targetRoomId: String) {
        if (!isConnected || webSocket == null) return

        try {
            val json = JSONObject().apply {
                put("timestamp", System.currentTimeMillis() / 1000.0)
                put("target_room_id", targetRoomId)
                val readingsObj = JSONObject()
                for ((bssid, rssi) in readingsMap) {
                    readingsObj.put(bssid, rssi)
                }
                put("readings", readingsObj)
            }
            webSocket?.send(json.toString())
        } catch (e: Exception) {
            Log.e("WSClient", "Error enviando scan: ${e.message}")
        }
    }

    fun disconnect() {
        webSocket?.close(1000, "Cerrado por usuario")
        webSocket = null
        isConnected = false
    }
}
