package com.floorwars.realtime

import org.json.JSONException
import org.json.JSONObject

// The building_flipped fields the notifier needs (contract BuildingFlip; teams are codes).
data class BuildingFlip(val buildingId: Int, val fromTeam: String?, val toTeam: String)

// The highest event_id handled, kept across process restarts.
interface LastEventIdStore {
    var lastEventId: Long
}

// One path for socket messages and polled pages (plan 7.2.1). Delivery is at least once, so each
// event_id passes once; ids only grow, so anything at or below the stored one has been handled.
class GameEventPipeline(
    private val store: LastEventIdStore,
    private val emit: (json: String) -> Unit,
    private val onFlip: (BuildingFlip) -> Unit
) {
    // One socket message: a WsEvent.
    @Synchronized
    fun onMessage(text: String) {
        val event = try {
            JSONObject(text)
        } catch (e: JSONException) {
            return
        }
        handle(event)
    }

    // A GameEventPage from GET /me/events, items oldest first.
    @Synchronized
    fun onPage(text: String) {
        val items = try {
            JSONObject(text).getJSONArray("items")
        } catch (e: JSONException) {
            return
        }
        for (i in 0 until items.length()) items.optJSONObject(i)?.let(::handle)
    }

    private fun handle(event: JSONObject) {
        // Without an id an event cannot be deduplicated, so it is dropped.
        val id = event.optLong("event_id", 0)
        if (id <= 0 || id <= store.lastEventId) return
        store.lastEventId = id
        when (event.optString("type")) {
            "building_flipped" -> {
                emit(event.toString())
                flipOf(event)?.let(onFlip)
            }
            "season_state" -> emit(event.toString())
            // An unknown type is skipped; its id still counts as handled.
        }
    }

    private fun flipOf(event: JSONObject): BuildingFlip? {
        val buildingId = event.optInt("building_id", 0)
        val toTeam = event.optString("to_team")
        if (buildingId <= 0 || toTeam.isEmpty() || event.isNull("to_team")) return null
        val fromTeam = if (event.isNull("from_team")) null else event.optString("from_team")
        return BuildingFlip(buildingId, fromTeam, toTeam)
    }
}
