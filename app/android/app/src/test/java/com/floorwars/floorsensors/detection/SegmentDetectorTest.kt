package com.floorwars.floorsensors.detection

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.outbox.OutboxSegment
import com.floorwars.floorsensors.outbox.SegmentOutbox
import com.floorwars.floorsensors.segmenter.SegmenterParams
import kotlin.math.exp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SegmentDetectorTest {
    private class FakeOutbox : SegmentOutbox {
        val rows = mutableListOf<OutboxSegment>()
        override fun insert(segment: OutboxSegment) {
            rows += segment
        }
    }

    private val checkin = ActiveCheckin("c-1", 7, "Rectorat", validUntilMs = Long.MAX_VALUE)
    private val offsetMs = 1_700_000_000_000L

    private fun event(nanos: Long, value: Float) = RawSensorEvent(0, nanos, floatArrayOf(value))

    // Flat 20 s, then a climb for climbS at speedMps with stepsPerM steps per metre, then 40 s flat; 25 Hz.
    private fun run(
        detector: SegmentDetector,
        climbS: Double,
        speedMps: Double,
        stepsPerM: Double
    ) {
        val start = 5_000_000_000L
        val pressure = (0..((60 + climbS) * 25).toInt()).map { i ->
            val t = i / 25.0
            val alt = speedMps * (t - 20).coerceIn(0.0, climbS)
            event(
                start + (t * 1e9).toLong(),
                (1000.0 * exp(-alt / SegmenterParams.SCALE_HEIGHT_M)).toFloat()
            )
        }
        val steps = if (stepsPerM == 0.0) {
            emptyList()
        } else {
            generateSequence(20.0) {
                it + 1 / (speedMps * stepsPerM)
            }.takeWhile { it < 20 + climbS }
                .map { event(start + (it * 1e9).toLong(), 1f) }.toList()
        }
        detector.add(pressure, steps)
        detector.stop()
    }

    @Test
    fun stairsClimbIsStoredWithCheckinAndWallClock() {
        val outbox = FakeOutbox()
        val detector = SegmentDetector(outbox, offsetMs, true, { checkin }, newId = { "id-1" })
        run(detector, climbS = 30.0, speedMps = 0.2, stepsPerM = 6.0)
        val row = outbox.rows.single()
        assertEquals("c-1", row.checkinId)
        assertEquals(7, row.buildingId)
        assertEquals(1.0, row.stairProb, 0.0)
        assertEquals("rules-1", row.classifierVersion)
        assertEquals(true, row.pressureStepsMatch)
        // Elapsed nanos plus the one offset: 5 s after boot, climb starting about 20 s later.
        assertEquals(offsetMs + 25_000.0, row.startMs.toDouble(), 2_500.0)
        assertEquals(row.durationS * 1000, (row.endMs - row.startMs).toDouble(), 1.0)
        assertEquals(row.endMs, detector.lastSegmentMs)
        assertEquals(0, detector.rejectedCount)
    }

    @Test
    fun elevatorAndSmallClimbsAreCountedNotStored() {
        val outbox = FakeOutbox()
        val lift = SegmentDetector(outbox, offsetMs, true, { checkin })
        run(lift, climbS = 15.0, speedMps = 0.8, stepsPerM = 0.0)
        // 1.5 m: the segmenter keeps climbs from 1 m, the contract starts at 2.0 m.
        val small = SegmentDetector(outbox, offsetMs, true, { checkin })
        run(small, climbS = 10.0, speedMps = 0.15, stepsPerM = 6.0)
        assertEquals(emptyList<OutboxSegment>(), outbox.rows)
        assertEquals(1, lift.rejectedCount)
        assertEquals(1, small.rejectedCount)
        assertNull(lift.lastSegmentMs)
    }

    @Test
    fun climbWithoutCheckinIsCountedNotStored() {
        val outbox = FakeOutbox()
        val detector = SegmentDetector(outbox, offsetMs, true, { null })
        run(detector, climbS = 30.0, speedMps = 0.2, stepsPerM = 6.0)
        assertEquals(emptyList<OutboxSegment>(), outbox.rows)
        assertEquals(1, detector.noCheckinCount)
    }
}
