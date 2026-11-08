package com.floorwars.floorsensors

import android.content.Context
import com.floorwars.floorsensors.detection.ActiveCheckin

// The active check-in, kept natively: the service can outlive the JS runtime, and the value must
// survive an app restart. Ids and the expiry only, no location.
object ActiveCheckinStore {
    private const val PREFS = "floor_sensors_checkin"
    private const val ID = "checkin_id"
    private const val BUILDING_ID = "building_id"
    private const val BUILDING_NAME = "building_name"
    private const val VALID_UNTIL_MS = "valid_until_ms"

    private fun prefs(context: Context) =
        context.applicationContext.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun save(context: Context, checkin: ActiveCheckin) {
        prefs(context).edit()
            .putString(ID, checkin.id)
            .putInt(BUILDING_ID, checkin.buildingId)
            .putString(BUILDING_NAME, checkin.buildingName)
            .putLong(VALID_UNTIL_MS, checkin.validUntilMs)
            .commit() // on disk before returning, so a kill right after cannot lose it
    }

    // Null when none is stored or it has expired; an expired one is removed.
    fun load(context: Context, nowMs: Long = System.currentTimeMillis()): ActiveCheckin? {
        val p = prefs(context)
        val id = p.getString(ID, null) ?: return null
        val checkin = ActiveCheckin(
            id = id,
            buildingId = p.getInt(BUILDING_ID, 0),
            buildingName = p.getString(BUILDING_NAME, null),
            validUntilMs = p.getLong(VALID_UNTIL_MS, 0)
        )
        if (!checkin.isValidAt(nowMs)) {
            clear(context)
            return null
        }
        return checkin
    }

    fun clear(context: Context) {
        prefs(context).edit().clear().commit()
    }
}
