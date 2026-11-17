package com.floorwars.realtime

import org.junit.After
import org.junit.Assert.assertEquals
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

    private fun pipeline() = GameEventPipeline(
        prefs,
        emit = { emitted += org.json.JSONObject(it).getLong("event_id") },
        onFlip = { flips += it }
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
    fun theFirstMessageWithNoStoredIdDoesNotNotify() {
        pipeline().onMessage(flipped(1))
        assertEquals(listOf(1L), emitted)
        assertEquals(emptyList<BuildingFlip>(), flips)
        assertEquals(1L, prefs.lastEventId)
    }

    @Test
    fun theNextLaterEventNotifies() {
        val p = pipeline()
        p.onMessage(flipped(1))
        p.onMessage(flipped(2))
        assertEquals(listOf(2), flips.map { it.buildingId })
    }

    @Test
    fun aFirstPolledPageIsSilentAsAWholeAndTheNextPageNotifies() {
        val p = pipeline()
        p.onPage("""{"items":[${flipped(1)},${flipped(2)},${flipped(3)}],"last_event_id":3}""")
        assertEquals(listOf(1L, 2L, 3L), emitted)
        assertEquals(emptyList<BuildingFlip>(), flips)
        p.onPage("""{"items":[${flipped(4)}],"last_event_id":4}""")
        assertEquals(listOf(4), flips.map { it.buildingId })
    }

    @Test
    fun aProcessRestartAfterTheCatchUpStillNotifiesNewEvents() {
        pipeline().onMessage(flipped(1))
        // A new pipeline over the same preferences, as after a restart.
        pipeline().onMessage(flipped(2))
        assertEquals(listOf(2), flips.map { it.buildingId })
    }

    companion object {
        fun flipped(id: Int, building: Int = id, from: String = "AC", to: String = "ETC") =
            """{"type":"building_flipped","event_id":$id,"building_id":$building,""" +
                """"from_team":"$from","to_team":"$to","at":"2026-11-17T10:00:00Z"}"""
    }
}
