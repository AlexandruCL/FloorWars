package com.floorwars.realtime

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

// Debug builds only. Runs one WsEvent through the pipeline, as if the socket had sent it:
// adb shell am broadcast -n com.floorwars/.realtime.DebugGameEventReceiver \
//   --es team AC --es json '{"type":"building_flipped","event_id":1,...}'
// Optional extras team and names ([{id,name}] JSON) set the realtime context first.
class DebugGameEventReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val realtime = Realtime.get(context)
        intent.getStringExtra("team")?.let { team ->
            realtime.prefs.setContext(team, intent.getStringExtra("names") ?: "[]")
        }
        intent.getStringExtra("json")?.let(realtime.pipeline::onMessage)
    }
}
