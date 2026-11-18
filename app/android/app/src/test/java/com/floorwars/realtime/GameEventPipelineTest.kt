package com.floorwars.realtime

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

// Robolectric for org.json and SharedPreferences. SDK 34 because CI runs JDK 17.
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class GameEventPipelineTest {
    private val prefs = RealtimePrefs(RuntimeEnvironment.getApplication())
    private val emitted = mutableListOf<Long>()
    private val flips = mutableListOf<BuildingFlip>()
    private var now = SIGN_IN_MS

    private fun pipeline() = GameEventPipeline(
        prefs,
        emit = { emitted += org.json.JSONObject(it).getLong("event_id") },
        onFlip = { flips += it },
        nowMs = { now }
    )

    @After
    fun clear() = prefs.clear()

    @Test
    fun aDuplicateEventIdIsDropped() {
        prefs.lastEventId = 10
        val p = pipeline()
        p.onMessage(flipped(11))
        p.onMessage(flipped(11))
        assertEquals(listOf(11L), emitted)
        assertEquals(1, flips.size)
        assertEquals(11L, prefs.lastEventId)
    }

    @Test
    fun anIdAtOrBelowTheStoredOneIsDroppedAfterAProcessRestart() {
        prefs.lastEventId = 4
        pipeline().onMessage(flipped(5))
        emitted.clear()
        flips.clear()
        // A new pipeline over the same preferences, as after a restart.
        val restarted = pipeline()
        restarted.onMessage(flipped(4))
        restarted.onMessage(flipped(5))
        restarted.onMessage(flipped(6))
        assertEquals(listOf(6L), emitted)
        assertEquals(listOf(6), flips.map { it.buildingId })
    }

    @Test
    fun seasonStateIsEmittedButNotAFlip() {
        pipeline().onMessage(
            """{"type":"season_state","event_id":3,"paused":true,"ends_at":"2026-12-01T00:00:00Z"}"""
        )
        assertEquals(listOf(3L), emitted)
        assertEquals(emptyList<BuildingFlip>(), flips)
    }

    @Test
    fun anUnknownTypeIsSkippedAndStillAdvancesTheId() {
        val p = pipeline()
        p.onMessage("""{"type":"landmark_reached","event_id":7}""")
        p.onMessage(flipped(7))
        assertEquals(emptyList<Long>(), emitted)
        assertEquals(7L, prefs.lastEventId)
    }

    @Test
    fun malformedOrIdlessMessagesAreDropped() {
        val p = pipeline()
        p.onMessage("not json")
        p.onMessage(
            """{"type":"building_flipped","building_id":2,"from_team":"AC","to_team":"ETC"}"""
        )
        assertEquals(emptyList<Long>(), emitted)
        assertEquals(0L, prefs.lastEventId)
    }

    @Test
    fun aPolledPageRunsEachItemThroughTheSamePipeline() {
        prefs.lastEventId = 1
        val p = pipeline()
        p.onMessage(flipped(2))
        p.onPage("""{"items":[${flipped(1)},${flipped(2)},${flipped(3)}],"last_event_id":3}""")
        assertEquals(listOf(2L, 3L), emitted)
        assertEquals(BuildingFlip(3, "AC", "ETC"), flips.last())
    }

    @Test
    fun aFlipFromNobodyHasANullFromTeam() {
        prefs.lastEventId = 1
        pipeline().onMessage(
            """{"type":"building_flipped","event_id":2,"building_id":4,"from_team":null,"to_team":"AC","at":"2026-11-17T10:00:00Z"}"""
        )
        assertEquals(listOf(BuildingFlip(4, null, "AC")), flips)
    }

    @Test
    fun aTwoPagePollFromIdZeroNotifiesNone() {
        val p = pipeline()
        p.onPage("""{"items":[${flipped(1)},${flipped(2)}],"last_event_id":2}""")
        p.onPage("""{"items":[${flipped(3)},${flipped(4)}],"last_event_id":4}""")
        assertEquals(listOf(1L, 2L, 3L, 4L), emitted)
        assertEquals(emptyList<BuildingFlip>(), flips)
        assertEquals(4L, prefs.lastEventId)
        assertEquals(SIGN_IN_MS, prefs.catchUpBeforeMs)
    }

    @Test
    fun aFlipAtOrAfterTheMarkNotifies() {
        val p = pipeline()
        p.onMessage(flipped(1))
        p.onMessage(flipped(2, at = "2026-11-17T12:00:00Z"))
        p.onMessage(flipped(3, at = "2026-11-17T14:00:00.250+02:00"))
        assertEquals(listOf(2, 3), flips.map { it.buildingId })
    }

    @Test
    fun aMissingOrUnreadableAtIsSilentWhileAMarkExists() {
        val p = pipeline()
        p.onMessage(flipped(1))
        p.onMessage(
            """{"type":"building_flipped","event_id":2,"building_id":2,"from_team":"AC","to_team":"ETC"}"""
        )
        p.onMessage(flipped(3, at = "yesterday"))
        assertEquals(listOf(1L, 2L, 3L), emitted)
        assertEquals(emptyList<BuildingFlip>(), flips)
    }

    @Test
    fun aProcessRestartKeepsTheMark() {
        pipeline().onMessage(flipped(1))
        now += 3_600_000
        // A new pipeline over the same preferences, as after a restart: the old backlog stays
        // silent, the mark is not moved, a live flip notifies.
        val restarted = pipeline()
        restarted.onPage("""{"items":[${flipped(2)}],"last_event_id":2}""")
        restarted.onMessage(flipped(3, at = "2026-11-17T12:30:00Z"))
        assertEquals(SIGN_IN_MS, prefs.catchUpBeforeMs)
        assertEquals(listOf(3), flips.map { it.buildingId })
    }

    @Test
    fun clearRealtimeWipesTheMarkAndTheNextSignInSetsANewOne() {
        pipeline().onMessage(flipped(1))
        // Realtime.clear (clearRealtime from endSession) clears these preferences.
        prefs.clear()
        assertNull(prefs.catchUpBeforeMs)
        now += 3_600_000
        pipeline().onMessage(flipped(1, at = "2026-11-17T12:30:00Z"))
        assertEquals(SIGN_IN_MS + 3_600_000, prefs.catchUpBeforeMs)
        assertEquals(emptyList<BuildingFlip>(), flips)
    }

    @Test
    fun parsesRfc3339DateTimes() {
        assertEquals(SIGN_IN_MS, parseDateTimeMs("2026-11-17T12:00:00Z"))
        assertEquals(SIGN_IN_MS + 123, parseDateTimeMs("2026-11-17t14:00:00.123456+02:00"))
        assertNull(parseDateTimeMs("2026-11-17 12:00:00"))
        assertNull(parseDateTimeMs("2026-13-17T12:00:00Z"))
    }

    companion object {
        // The test clock at the first event after sign-in; flipped() defaults to two hours earlier.
        const val SIGN_IN_MS = 1_794_916_800_000L

        fun flipped(
            id: Int,
            building: Int = id,
            from: String = "AC",
            to: String = "ETC",
            at: String = "2026-11-17T10:00:00Z"
        ) = """{"type":"building_flipped","event_id":$id,"building_id":$building,""" +
            """"from_team":"$from","to_team":"$to","at":"$at"}"""
    }
}
