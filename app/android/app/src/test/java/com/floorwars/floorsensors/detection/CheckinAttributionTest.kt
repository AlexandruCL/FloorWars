package com.floorwars.floorsensors.detection

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.classifier.ClassifierThresholds
import com.floorwars.floorsensors.outbox.OutboxSegment
import com.floorwars.floorsensors.outbox.SegmentOutbox
import com.floorwars.floorsensors.segmenter.LiveSegmenterParams
import com.floorwars.floorsensors.segmenter.Segmenter
import com.floorwars.floorsensors.segmenter.SegmenterParams
import kotlin.math.exp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

// Plan section 2: a segment belongs to the check-in active when the climb started.
class CheckinAttributionTest {
    private class FakeOutbox : SegmentOutbox {
        val rows = mutableListOf<OutboxSegment>()
        override fun insert(segment: OutboxSegment) {
            rows += segment
        }
    }

    // Wall ms = elapsed ms + OFFSET_MS. The stream starts at elapsed 0.
    private val offsetMs = 1_700_000_000_000L
    private fun wall(s: Double) = offsetMs + (s * 1000).toLong()

    private fun checkin(id: String, untilS: Double) = ActiveCheckin(id, 3, null, wall(untilS))

    private fun event(nanos: Long, value: Float) = RawSensorEvent(0, nanos, floatArrayOf(value))

    // 25 Hz pressure over totalS; climbs at 0.2 m/s with 6 steps per metre, as (start s, length s).
    private fun stream(
        totalS: Double,
        climbs: List<Pair<Double, Double>>
    ): Pair<List<RawSensorEvent>, List<RawSensorEvent>> {
        val pressure = (0..(totalS * 25).toInt()).map { i ->
            val t = i / 25.0
            val alt = climbs.sumOf { (start, len) -> 0.2 * (t - start).coerceIn(0.0, len) }
            event(
                (t * 1e9).toLong(),
                (1000.0 * exp(-alt / SegmenterParams.SCALE_HEIGHT_M)).toFloat()
            )
        }
        val steps = climbs.flatMap { (start, len) ->
            generateSequence(start) { it + 1 / 1.2 }.takeWhile { it < start + len }
                .map { event((it * 1e9).toLong(), 1f) }.toList()
        }
        return pressure to steps
    }

    // Feeds 1 s chunks; before each chunk starting at t, onSecond(t) can swap the check-in.
    private fun feed(
        detector: SegmentDetector,
        data: Pair<List<RawSensorEvent>, List<RawSensorEvent>>,
        untilS: Double = Double.MAX_VALUE,
        onSecond: (Int) -> Unit = {}
    ) {
        val (pressure, steps) = data
        val p = pressure.groupBy { (it.timestampNanos / 1_000_000_000).toInt() }
        val s = steps.groupBy { (it.timestampNanos / 1_000_000_000).toInt() }
        for (second in 0..p.keys.max()) {
            if (second >= untilS) break
            onSecond(second)
            detector.add(p[second].orEmpty(), s[second].orEmpty())
        }
        detector.stop()
    }

    private fun detector(outbox: FakeOutbox, history: CheckinHistory) =
        SegmentDetector(outbox, offsetMs, true, history::at)

    @Test
    fun climbStartingInsideAndEndingAfterValidUntilCounts() {
        val outbox = FakeOutbox()
        val history = CheckinHistory().apply { set(checkin("a", untilS = 30.0), wall(0.0)) }
        val d = detector(outbox, history)
        feed(d, stream(100.0, listOf(20.0 to 30.0)))
        val row = outbox.rows.single()
        assertEquals("a", row.checkinId)
        assertEquals(3, row.buildingId)
        assertTrue("ends after valid_until", row.endMs > wall(30.0))
    }

    @Test
    fun climbStartingAfterValidUntilIsNotStored() {
        val outbox = FakeOutbox()
        val history = CheckinHistory().apply { set(checkin("a", untilS = 15.0), wall(0.0)) }
        val d = detector(outbox, history)
        feed(d, stream(100.0, listOf(20.0 to 30.0)))
        assertEquals(emptyList<OutboxSegment>(), outbox.rows)
        assertEquals(1, d.noCheckinCount)
    }

    @Test
    fun swapsInTheMiddleOfARecordingKeepEachClimbOnItsStartCheckin() {
        val outbox = FakeOutbox()
        val history = CheckinHistory().apply { set(checkin("a", 5400.0), wall(0.0)) }
        val d = detector(outbox, history)
        val emittedBeforeSwap = mutableListOf<Int>()
        feed(d, stream(200.0, listOf(20.0 to 30.0, 120.0 to 30.0))) { second ->
            // During climb 1, then between the climbs, before climb 1 has been emitted.
            if (second == 35) history.set(checkin("b", 5400.0), wall(35.0))
            if (second == 60) {
                emittedBeforeSwap += outbox.rows.size
                history.set(checkin("c", 5400.0), wall(60.0))
            }
        }
        assertEquals(listOf(0), emittedBeforeSwap)
        assertEquals(listOf("a", "c"), outbox.rows.map { it.checkinId })
    }

    @Test
    fun climbStartingJustBeforeExpiryIsStoredWholeWithinTheGrace() {
        val climbs = listOf(90.0 to 150.0) // ends 140 s after valid_until
        val data = stream(400.0, climbs)
        val expected = Segmenter().segment(data.first, data.second).single()
        val outbox = FakeOutbox()
        val history = CheckinHistory().apply { set(checkin("a", untilS = 100.0), wall(0.0)) }
        val d = detector(outbox, history)
        // The service stops detecting at detectionEndMs(valid_until).
        val stopS = (detectionEndMs(wall(100.0)) - offsetMs) / 1000.0
        feed(d, data, untilS = stopS)
        val row = outbox.rows.single()
        assertEquals("a", row.checkinId)
        assertEquals(expected.durationS, row.durationS, 0.0)
        assertEquals(expected.steps, row.steps)
        assertTrue(
            EXPIRY_GRACE_S >= ClassifierThresholds.MAX_STAIRS_WINDOW_S + LiveSegmenterParams.CLOSE_S
        )
    }
}
