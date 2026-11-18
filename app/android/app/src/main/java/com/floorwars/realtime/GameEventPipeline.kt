package com.floorwars.realtime

import java.text.ParseException
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.TimeZone
import org.json.JSONException
import org.json.JSONObject

// The building_flipped fields the notifier needs (contract BuildingFlip; teams are codes).
data class BuildingFlip(val buildingId: Int, val fromTeam: String?, val toTeam: String)

// The highest event_id handled and the catch-up mark, kept across process restarts.
interface LastEventIdStore {
    var lastEventId: Long
    var catchUpBeforeMs: Long?
}

// One path for socket messages and polled pages (plan 7.2.1). Delivery is at least once, so each
// event_id passes once; ids only grow, so anything at or below the stored one has been handled.
// Silent catch-up (Cristea, 2026-11-17 and 2026-11-18): a socket connection or a poll that starts
// from since=0 (sign-in, reinstall) records the mark "now" once, before any event arrives. The
// backlog spans many socket messages and poll pages, so a flip is judged by its own `at`: before
// the mark (or no readable `at`) it reaches JS but notifies nothing; at or after the mark it goes
// to the notifier.
class GameEventPipeline(
    private val store: LastEventIdStore,
    private val emit: (json: String) -> Unit,
    private val onFlip: (BuildingFlip) -> Unit,
    private val nowMs: () -> Long = System::currentTimeMillis
) {
    // The since of a new socket connection or poll. A run from 0 sets the catch-up mark first.
    @Synchronized
    fun startRun(): Long {
        val since = store.lastEventId
        if (since <= 0 && store.catchUpBeforeMs == null) store.catchUpBeforeMs = nowMs()
        return since
    }

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
                if (isLive(event)) flipOf(event)?.let(onFlip)
            }
            "season_state" -> emit(event.toString())
            // An unknown type is skipped; its id still counts as handled.
        }
    }

    private fun isLive(event: JSONObject): Boolean {
        val mark = store.catchUpBeforeMs ?: return true
        val at = parseDateTimeMs(event.optString("at")) ?: return false
        return at >= mark
    }

    private fun flipOf(event: JSONObject): BuildingFlip? {
        val buildingId = event.optInt("building_id", 0)
        val toTeam = event.optString("to_team")
        if (buildingId <= 0 || toTeam.isEmpty() || event.isNull("to_team")) return null
        val fromTeam = if (event.isNull("from_team")) null else event.optString("from_team")
        return BuildingFlip(buildingId, fromTeam, toTeam)
    }
}

private val DATE_TIME = Regex("""(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)""")

// RFC 3339 date-time to epoch ms, null when unreadable. java.time needs API 26; minSdk is 24.
internal fun parseDateTimeMs(text: String): Long? {
    val m = DATE_TIME.matchEntire(text.uppercase(Locale.US)) ?: return null
    val (seconds, fraction, zone) = m.destructured
    val format = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ssXXX", Locale.US).apply {
        isLenient = false
        timeZone = TimeZone.getTimeZone("UTC")
    }
    return try {
        format.parse(seconds + zone)!!.time + fraction.padEnd(3, '0').take(3).toLong()
    } catch (e: ParseException) {
        null
    }
}
