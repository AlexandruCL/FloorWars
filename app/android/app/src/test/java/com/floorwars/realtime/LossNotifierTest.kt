package com.floorwars.realtime

import android.app.Notification
import android.app.NotificationManager
import android.net.Uri
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class LossNotifierTest {
    private val context = RuntimeEnvironment.getApplication()
    private val prefs = RealtimePrefs(context)
    private var now = 1_800_000_000_000L
    private val notifier = LossNotifier(context, prefs) { now }
    private val manager = context.getSystemService(NotificationManager::class.java)
    private val pipeline = GameEventPipeline(prefs, emit = {}, onFlip = notifier::onFlip)
    private var nextId = 1

    @Before
    fun context() {
        prefs.setContext("AC", """[{"id":7,"name":"Politehnica"}]""")
        // Past the silent catch-up: an id is stored, so losses notify.
        prefs.lastEventId = 100
        nextId = 101
    }

    @After
    fun clear() {
        prefs.clear()
        manager.cancelAll()
    }

    private fun flip(building: Int, from: String?, to: String) {
        val fromJson = if (from == null) "null" else "\"$from\""
        pipeline.onMessage(
            """{"type":"building_flipped","event_id":${nextId++},"building_id":$building,""" +
                """"from_team":$fromJson,"to_team":"$to","at":"2026-11-17T10:00:00Z"}"""
        )
    }

    private fun posted() = shadowOf(manager).allNotifications

    private val Notification.title get() = extras.getString(Notification.EXTRA_TITLE)
    private val Notification.text get() = extras.getString(Notification.EXTRA_TEXT)

    @Test
    fun aLossNotifiesWithTheApprovedTextAndTheDeepLink() {
        flip(7, from = "AC", to = "ETC")
        val n = posted().single()
        assertEquals("ETC took Politehnica", n.title)
        assertEquals("Your team lost it. Tap to see the standings.", n.text)
        assertEquals(GAME_EVENTS_CHANNEL_ID, n.channelId)
        val channel = manager.getNotificationChannel(GAME_EVENTS_CHANNEL_ID)
        assertEquals("Building alerts", channel.name)
        assertEquals(
            Uri.parse("floorwars://building/7"),
            shadowOf(n.contentIntent).savedIntent.data
        )
    }

    @Test
    fun aWinDoesNotNotify() {
        flip(7, from = "ETC", to = "AC")
        assertEquals(0, posted().size)
    }

    @Test
    fun anotherTeamsFlipAndAnUnownedBuildingDoNotNotify() {
        flip(7, from = "ETC", to = "MEC")
        flip(8, from = null, to = "ETC")
        assertEquals(0, posted().size)
    }

    @Test
    fun seasonStateDoesNotNotify() {
        pipeline.onMessage(
            """{"type":"season_state","event_id":${nextId++},"paused":true,"ends_at":"2026-12-01T00:00:00Z"}"""
        )
        assertEquals(0, posted().size)
    }

    @Test
    fun aSecondLossInTheSameBuildingWithinTenMinutesDoesNotNotify() {
        flip(7, from = "AC", to = "ETC")
        manager.cancelAll()
        now += NOTIFY_MIN_INTERVAL_MS - 1
        flip(7, from = "AC", to = "MEC")
        assertEquals(0, posted().size)
    }

    @Test
    fun aSecondLossAfterTenMinutesNotifies() {
        flip(7, from = "AC", to = "ETC")
        manager.cancelAll()
        now += NOTIFY_MIN_INTERVAL_MS
        flip(7, from = "AC", to = "MEC")
        assertEquals("MEC took Politehnica", posted().single().title)
    }

    @Test
    fun theLimitIsPerBuilding() {
        flip(7, from = "AC", to = "ETC")
        flip(8, from = "AC", to = "ETC")
        assertEquals(2, posted().size)
    }

    @Test
    fun anUnknownBuildingNameUsesTheFallbackTitle() {
        flip(9, from = "AC", to = "ETC")
        assertEquals("ETC took building 9", posted().single().title)
    }

    @Test
    fun noTeamCodeNoNotification() {
        prefs.clear()
        prefs.lastEventId = 100
        flip(7, from = "AC", to = "ETC")
        assertEquals(0, posted().size)
    }
}
