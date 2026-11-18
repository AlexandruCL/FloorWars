package com.floorwars.realtime

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.floorwars.R

const val NOTIFY_MIN_INTERVAL_MS = 600_000L
const val GAME_EVENTS_CHANNEL_ID = "game_events"

// Posts a local notification when the player's team loses a building (plan 7.2.1): never for a
// win or a season_state, at most once per building per 10 minutes. Runs without the JS runtime.
class LossNotifier(
    private val context: Context,
    private val prefs: RealtimePrefs,
    private val nowMs: () -> Long = System::currentTimeMillis
) {
    @Synchronized
    fun onFlip(flip: BuildingFlip) {
        val myTeam = prefs.teamCode ?: return
        if (flip.fromTeam != myTeam) return
        val now = nowMs()
        val last = prefs.notifiedAtMs(flip.buildingId)
        // A clock set back (now before last) does not silence the building.
        if (last != null && now - last in 0 until NOTIFY_MIN_INTERVAL_MS) return
        if (post(flip)) prefs.setNotifiedAtMs(flip.buildingId, now)
    }

    private fun post(flip: BuildingFlip): Boolean {
        val manager = NotificationManagerCompat.from(context)
        if (!manager.areNotificationsEnabled()) return false
        // High: a loss shows a heads-up banner (Cristea, 2026-11-18). Android keeps a channel's
        // importance once it is created, so changing it later needs a new channel id.
        manager.createNotificationChannel(
            NotificationChannelCompat
                .Builder(GAME_EVENTS_CHANNEL_ID, NotificationManagerCompat.IMPORTANCE_HIGH)
                .setName(context.getString(R.string.game_events_channel_name))
                .build()
        )
        val name = prefs.buildingName(flip.buildingId)
        val title = if (name != null) {
            context.getString(R.string.building_lost_title, flip.toTeam, name)
        } else {
            context.getString(R.string.building_lost_title_unnamed, flip.toTeam, flip.buildingId)
        }
        val open = PendingIntent.getActivity(
            context,
            flip.buildingId,
            Intent(Intent.ACTION_VIEW, Uri.parse(deepLink(flip.buildingId)))
                .setPackage(context.packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val notification = NotificationCompat.Builder(context, GAME_EVENTS_CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_sensors)
            .setContentTitle(title)
            .setContentText(context.getString(R.string.building_lost_text))
            // API 24-25 (minSdk 24) have no channels; there the priority makes it heads-up.
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        return try {
            // One per building: a later loss replaces the earlier one.
            manager.notify(NOTIFICATION_TAG, flip.buildingId, notification)
            true
        } catch (e: SecurityException) {
            false
        }
    }

    companion object {
        const val NOTIFICATION_TAG = "building_lost"

        fun deepLink(buildingId: Int) = "floorwars://building/$buildingId"
    }
}
