package com.floorwars.realtime

import android.content.Context
import android.util.Log

// Process-wide: the module (foreground holder) and the service (session holder) share one socket,
// one pipeline and one notifier, and the service can outlive the JS runtime.
class Realtime private constructor(context: Context) {
    val prefs = RealtimePrefs(context)
    private val notifier = LossNotifier(context, prefs)
    val pipeline = GameEventPipeline(
        prefs,
        emit = { json -> eventListener?.invoke(json) },
        onFlip = notifier::onFlip
    )
    val client = RealtimeClient(
        realtimeHttpClient(),
        lastEventId = { prefs.lastEventId },
        onMessage = pipeline::onMessage,
        onState = { state ->
            Log.i(TAG, "state=$state")
            stateListener?.invoke(state)
        }
    )

    // Sign-out: close the socket, forget the token, team, names and the last event id.
    fun clear() {
        client.clear()
        prefs.clear()
    }

    companion object {
        private const val TAG = "Realtime"

        @Volatile
        private var instance: Realtime? = null

        // Set by the module while JS is alive.
        @Volatile
        var eventListener: ((String) -> Unit)? = null

        @Volatile
        var stateListener: ((String) -> Unit)? = null

        fun get(context: Context): Realtime = instance ?: synchronized(this) {
            instance ?: Realtime(context.applicationContext).also { instance = it }
        }
    }
}
