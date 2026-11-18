package com.floorwars.realtime

import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import kotlin.math.min
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

// Plan 7.2.1 and Cristea's decision of 2026-11-17.
const val PING_INTERVAL_S = 30L
const val RECONNECT_BASE_MS = 1_000L
const val RECONNECT_CAP_MS = 60_000L
const val RECONNECT_RESET_AFTER_MS = 60_000L

// Who keeps the socket open: the app in the foreground, and the service during a check-in.
enum class Holder { FOREGROUND, SESSION }

// Exponential backoff with full jitter: uniform in [0, min(cap, base * 2^attempt)).
fun reconnectDelayMs(attempt: Int, random: Double): Long {
    val ceiling = min(RECONNECT_CAP_MS, RECONNECT_BASE_MS shl min(attempt, 6))
    return (random * ceiling).toLong()
}

fun realtimeHttpClient(): OkHttpClient =
    OkHttpClient.Builder().pingInterval(PING_INTERVAL_S, TimeUnit.SECONDS).build()

private val reconnectExecutor by lazy {
    Executors.newSingleThreadScheduledExecutor { Thread(it, "realtime").apply { isDaemon = true } }
}

// The one WebSocket of the process. Open while a holder holds it and a token is known. Native
// never refreshes: JS hands every new access token over, and a 401 waits for a different one.
class RealtimeClient(
    private val http: OkHttpClient,
    // Read once per connect, as since; the pipeline's startRun.
    private val lastEventId: () -> Long,
    private val onMessage: (String) -> Unit,
    private val onState: (String) -> Unit,
    private val nowMs: () -> Long = { System.nanoTime() / 1_000_000 },
    private val random: () -> Double = Math::random,
    private val schedule: (delayMs: Long, task: () -> Unit) -> Unit = { delayMs, task ->
        reconnectExecutor.schedule(task, delayMs, TimeUnit.MILLISECONDS)
    }
) {
    private var url: String? = null
    private var token: String? = null

    // The token a 401 refused; the client waits until JS brings another.
    private var rejectedToken: String? = null
    private val holders = mutableSetOf<Holder>()
    private var socket: WebSocket? = null
    private var reconnectPending = false
    private var attempt = 0
    private var openedAtMs: Long? = null

    @get:Synchronized
    var state = "closed"
        private set

    @Synchronized
    fun configure(wsUrl: String, accessToken: String?) {
        url = wsUrl
        token = accessToken
        update()
    }

    @Synchronized
    fun hold(holder: Holder) {
        holders += holder
        update()
    }

    @Synchronized
    fun release(holder: Holder) {
        holders -= holder
        update()
    }

    // Sign-out: close and forget the token. The holders stay; with no token nothing opens.
    @Synchronized
    fun clear() {
        token = null
        rejectedToken = null
        attempt = 0
        update()
    }

    private fun authNeeded() = token != null && token == rejectedToken

    private fun wanted() = holders.isNotEmpty() && url != null && token != null && !authNeeded()

    private fun update() {
        if (wanted()) {
            if (socket == null && !reconnectPending) connect()
            return
        }
        socket?.close(NORMAL_CLOSURE, null)
        socket = null
        openedAtMs = null
        setState(if (authNeeded()) "auth_needed" else "closed")
    }

    private fun connect() {
        val request = Request.Builder()
            .url("$url?since=${lastEventId()}")
            .header("Authorization", "Bearer $token")
            .build()
        setState("connecting")
        socket = http.newWebSocket(request, Listener())
    }

    private fun setState(next: String) {
        if (next == state) return
        state = next
        onState(next)
    }

    @Synchronized
    private fun lost(ws: WebSocket, httpCode: Int?) {
        if (ws !== socket) return
        socket = null
        val opened = openedAtMs
        openedAtMs = null
        if (httpCode == HTTP_UNAUTHORIZED) {
            rejectedToken = token
            setState("auth_needed")
            return
        }
        if (opened != null && nowMs() - opened >= RECONNECT_RESET_AFTER_MS) attempt = 0
        if (!wanted()) {
            setState("closed")
            return
        }
        val delay = reconnectDelayMs(attempt++, random())
        reconnectPending = true
        setState("connecting")
        schedule(delay) {
            synchronized(this) {
                reconnectPending = false
                update()
            }
        }
    }

    @Synchronized
    private fun isCurrent(ws: WebSocket) = ws === socket

    private inner class Listener : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            synchronized(this@RealtimeClient) {
                if (webSocket !== socket) return
                openedAtMs = nowMs()
                setState("open")
            }
        }

        // Messages from a socket already let go (sign-out, release) are not handled.
        override fun onMessage(webSocket: WebSocket, text: String) {
            if (isCurrent(webSocket)) onMessage(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            webSocket.close(NORMAL_CLOSURE, null)
        }

        override fun onClosed(webSocket: WebSocket, code: Int, reason: String) =
            lost(webSocket, null)

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) =
            lost(webSocket, response?.code)
    }

    private companion object {
        const val NORMAL_CLOSURE = 1000
        const val HTTP_UNAUTHORIZED = 401
    }
}
