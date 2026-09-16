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
 *
 * `onStatusChanged` recibe el estado de conexión y, cuando se pierde, el motivo, para que la
 * interfaz pueda mostrar algo más útil que "desconectado".
 */
class WebSocketClientManager(
    private val serverWsUrl: String,
    private val studentId: String,
    private val onFeedbackReceived: (MobileNavigationFeedback) -> Unit,
    private val onStatusChanged: (Boolean, String?) -> Unit,
    /**
     * Token entregado al dar de alta el dispositivo. Mientras el servidor no tenga ningún
     * dispositivo registrado acepta conexiones sin él; en cuanto se registra el primero, pasa a
     * ser obligatorio y la identidad del alumno se toma de la credencial, no de la ruta.
     */
    private val deviceToken: String = ""
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
        val cleanBase = serverWsUrl.trim().removeSuffix("/")
        val fullUrl = "$cleanBase/ws/mobile/$studentId"
        Log.i("WSClient", "Iniciando conexión WebSocket a: $fullUrl")

        // Descartar cualquier socket previo antes de abrir uno nuevo.
        webSocket?.cancel()

        try {
            val builder = Request.Builder().url(fullUrl)
            if (deviceToken.isNotBlank()) {
                builder.addHeader(DEVICE_TOKEN_HEADER, deviceToken)
            }
            val request = builder.build()

            webSocket = client.newWebSocket(request, object : WebSocketListener() {
                override fun onOpen(ws: WebSocket, response: Response) {
                    isConnected = true
                    reconnectAttempts = 0
                    handler.post { onStatusChanged(true, null) }
                    Log.i("WSClient", "Conectado al Cerebro IPS en: $fullUrl")
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
                    val errorMsg = t.localizedMessage ?: t.message
                        ?: (if (response != null) "HTTP ${response.code}" else "Error de red")
                    handler.post { onStatusChanged(false, errorMsg) }

                    // Un 403 en el handshake indica rechazo del servidor, no un fallo de red.
                    if (response?.code == HTTP_FORBIDDEN) {
                        reportRejectedIdentifier("el servidor rechazó el handshake (HTTP 403)")
                        return
                    }

                    Log.w("WSClient", "Fallo en conexión WS a $fullUrl: $errorMsg")
                    scheduleReconnect(errorMsg)
                }

                override fun onClosing(ws: WebSocket, code: Int, reason: String) {
                    // 4400: el identificador no cumple el formato. 4401: falta la credencial del
                    // dispositivo o no es válida. En ambos casos reintentar con los mismos datos
                    // no puede funcionar, así que se inhibe la reconexión automática.
                    if (code == WS_CLOSE_INVALID_IDENTIFIER) {
                        isClosedByUser = true
                        reportRejectedIdentifier(reason)
                    } else if (code == WS_CLOSE_UNAUTHORIZED) {
                        isClosedByUser = true
                        val mensaje = if (deviceToken.isBlank()) {
                            "Este servidor exige registrar el dispositivo. Pide al docente que lo " +
                                "dé de alta y anota el token en la configuración."
                        } else {
                            "El token de este dispositivo no es válido o fue revocado: $reason"
                        }
                        Log.e("WSClient", mensaje)
                        handler.post { onStatusChanged(false, mensaje) }
                    }
                }

                override fun onClosed(ws: WebSocket, code: Int, reason: String) {
                    isConnected = false
                    val motivo = if (reason.isNotEmpty()) reason else "Desconectado ($code)"
                    handler.post { onStatusChanged(false, motivo) }
                    if (code == WS_CLOSE_INVALID_IDENTIFIER || code == WS_CLOSE_UNAUTHORIZED) return
                    scheduleReconnect(motivo)
                }
            })
        } catch (e: Exception) {
            isConnected = false
            handler.post { onStatusChanged(false, e.localizedMessage ?: "URL inválida") }
            Log.e("WSClient", "Error creando WebSocket request: ${e.message}")
        }
    }

    /** Reintento con retroceso exponencial y tope, en lugar de cada 3 s indefinidamente. */
    private fun scheduleReconnect(cause: String?) {
        if (isClosedByUser) return

        if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
            Log.w("WSClient", "Agotados los $MAX_RECONNECT_ATTEMPTS reintentos de conexión. Se detiene.")
            handler.post { onStatusChanged(false, "Sin conexión tras $MAX_RECONNECT_ATTEMPTS intentos") }
            return
        }

        val delayMs = minOf(
            INITIAL_RECONNECT_DELAY_MS shl reconnectAttempts,
            MAX_RECONNECT_DELAY_MS
        )
        reconnectAttempts++
        Log.w("WSClient", "Reintento $reconnectAttempts en ${delayMs}ms (causa: $cause)")
        handler.postDelayed({ connect() }, delayMs)
    }

    private fun reportRejectedIdentifier(reason: String) {
        val mensaje = "Identificador '$studentId' rechazado: $reason"
        Log.e("WSClient", "$mensaje. Debe cumplir [A-Za-z0-9_-]{1,32}.")
        handler.post { onStatusChanged(false, mensaje) }
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
                put("student_id", studentId)
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

        /** Codigo con el que el backend rechaza una conexion sin credencial de dispositivo. */
        private const val WS_CLOSE_UNAUTHORIZED = 4401

        /** Cabecera por la que el movil presenta su token de dispositivo. */
        private const val DEVICE_TOKEN_HEADER = "X-Device-Token"

        /** Respuesta del handshake si el servidor cierra la conexión sin llegar a aceptarla. */
        private const val HTTP_FORBIDDEN = 403

        private const val INITIAL_RECONNECT_DELAY_MS = 1000L
        private const val MAX_RECONNECT_DELAY_MS = 60_000L
        private const val MAX_RECONNECT_ATTEMPTS = 8
    }
}
