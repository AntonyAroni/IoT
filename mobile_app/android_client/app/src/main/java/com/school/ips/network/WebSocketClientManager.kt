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

    // Estado de reconexión. Antes se reintentaba cada 3 s de forma indefinida y sin cancelar el
    // socket anterior, de modo que con el servidor caído se acumulaban sockets y se martilleaba
    // la red sin tregua.
    private var reconnectAttempts = 0
    private var isClosedByUser = false

    fun connect() {
        isClosedByUser = false
        val fullUrl = "$serverWsUrl/ws/mobile/$studentId"
        val request = Request.Builder().url(fullUrl).build()

        // Descartar cualquier socket previo antes de abrir uno nuevo.
        webSocket?.cancel()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                isConnected = true
                reconnectAttempts = 0
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

                // El servidor cierra con 4400 cuando el identificador no cumple su formato.
                // Reintentar con el mismo identificador no puede funcionar nunca.
                if (response?.code == WS_CLOSE_INVALID_IDENTIFIER) {
                    Log.e("WSClient", "El servidor rechazó el identificador '$studentId'. Revísalo en la configuración.")
                    return
                }

                scheduleReconnect(t.message)
            }

            override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                isConnected = false
                handler.post { onStatusChanged(false) }
                if (code == WS_CLOSE_INVALID_IDENTIFIER) {
                    Log.e("WSClient", "Identificador rechazado por el servidor: $reason")
                    return
                }
                scheduleReconnect("cierre remoto ($code)")
            }
        })
    }

    /** Reintento con retroceso exponencial y tope, en lugar de cada 3 s indefinidamente. */
    private fun scheduleReconnect(cause: String?) {
        if (isClosedByUser) return

        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            Log.w("WSClient", "Agotados los $MAX_RECONNECT_ATTEMPTS reintentos de conexión. Se detiene.")
            return
        }

        val delayMs = minOf(
            INITIAL_RECONNECT_DELAY_MS shl reconnectAttempts,
            MAX_RECONNECT_DELAY_MS
        )
        reconnectAttempts++
        Log.w("WSClient", "Fallo en conexión WS: $cause. Reintento $reconnectAttempts en ${delayMs}ms")
        handler.postDelayed({ connect() }, delayMs)
    }

    /**
     * Envía un vector de lecturas Wi-Fi al servidor.
     *
     * @param roomApRssi potencia medida del AP del aula destino, o null si no se detectó. El
     *   servidor solo puede tratar el RSSI como medición cuando este campo viaja; si falta, lo
     *   deriva de la posición estimada y lo marca como estimado.
     */
    fun sendScanVector(
        readingsMap: Map<String, Double>,
        targetRoomId: String,
        roomApRssi: Double? = null
    ) {
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
                if (roomApRssi != null) {
                    put("room_ap_rssi", roomApRssi)
                }
            }
            webSocket?.send(json.toString())
        } catch (e: Exception) {
            Log.e("WSClient", "Error enviando scan: ${e.message}")
        }
    }

    fun disconnect() {
        isClosedByUser = true
        handler.removeCallbacksAndMessages(null)
        webSocket?.close(1000, "Cerrado por usuario")
        webSocket = null
        isConnected = false
        reconnectAttempts = 0
    }

    companion object {
        /** Código con el que el backend rechaza un identificador mal formado. */
        private const val WS_CLOSE_INVALID_IDENTIFIER = 4400

        private const val INITIAL_RECONNECT_DELAY_MS = 1000L
        private const val MAX_RECONNECT_DELAY_MS = 60_000L
        private const val MAX_RECONNECT_ATTEMPTS = 8
    }
}
