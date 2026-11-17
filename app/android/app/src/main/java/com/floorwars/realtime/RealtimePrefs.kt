package com.floorwars.realtime

import android.content.Context
import org.json.JSONArray
import org.json.JSONException

// Realtime state that must outlive the process: the last event id (the socket's and the poll's
// since), the player's team code and the building names (the notifier runs without JS), and the
// time of the last notification per building. Team code and building names only, nothing personal.
class RealtimePrefs(context: Context) : LastEventIdStore {
    private val prefs =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    override var lastEventId: Long
        get() = prefs.getLong(KEY_LAST_EVENT_ID, 0)
        set(value) {
            prefs.edit().putLong(KEY_LAST_EVENT_ID, value).commit()
        }

    val teamCode: String? get() = prefs.getString(KEY_TEAM_CODE, null)

    fun setContext(teamCode: String?, buildingNamesJson: String) {
        prefs.edit()
            .putString(KEY_TEAM_CODE, teamCode)
            .putString(KEY_BUILDING_NAMES, buildingNamesJson)
            .commit()
    }

    // From the [{id, name}] list of GET /buildings; null when unknown or the list is unreadable.
    fun buildingName(id: Int): String? = try {
        val list = JSONArray(prefs.getString(KEY_BUILDING_NAMES, null) ?: return null)
        (0 until list.length())
            .mapNotNull { list.optJSONObject(it) }
            .firstOrNull { it.optInt("id") == id }
            ?.optString("name")
            ?.takeIf { it.isNotEmpty() }
    } catch (e: JSONException) {
        null
    }

    fun notifiedAtMs(buildingId: Int): Long? =
        prefs.getLong(KEY_NOTIFIED_AT + buildingId, -1).takeIf { it >= 0 }

    fun setNotifiedAtMs(buildingId: Int, atMs: Long) {
        prefs.edit().putLong(KEY_NOTIFIED_AT + buildingId, atMs).apply()
    }

    // Sign-out: everything here belongs to the leaving player.
    fun clear() {
        prefs.edit().clear().commit()
    }

    companion object {
        private const val PREFS = "floorwars_realtime"
        const val KEY_LAST_EVENT_ID = "last_event_id"
        private const val KEY_TEAM_CODE = "team_code"
        private const val KEY_BUILDING_NAMES = "building_names"
        private const val KEY_NOTIFIED_AT = "notified_at_"
    }
}
