package com.floorwars.floorsensors.detection

import org.junit.Assert.assertEquals
import org.junit.Test

class GapCounterTest {
    private fun nanos(s: Double) = (s * 1e9).toLong()

    @Test
    fun countsGapsOverTheThresholdAndKeepsTheLongest() {
        val gaps = GapCounter()
        // 25 Hz for 10 s, a 4 s gap (under), 25 Hz, a 7.5 s gap, 25 Hz, a 30 s gap.
        var t = 0.0
        fun run(seconds: Double) {
            repeat((seconds * 25).toInt()) {
                gaps.onPressure(nanos(t))
                t += 0.04
            }
        }
        run(10.0)
        t += 4.0
        run(5.0)
        t += 7.5
        run(5.0)
        t += 30.0
        run(1.0)
        assertEquals(2, gaps.gapsOverThreshold)
        assertEquals(30.04, gaps.longestGapS, 1e-6)
    }

    @Test
    fun exactlyTheThresholdIsNotOver() {
        val gaps = GapCounter()
        gaps.onPressure(0)
        gaps.onPressure(nanos(GAP_THRESHOLD_S))
        assertEquals(0, gaps.gapsOverThreshold)
        assertEquals(GAP_THRESHOLD_S, gaps.longestGapS, 1e-9)
    }

    @Test
    fun outOfOrderEventsAreNotGaps() {
        val gaps = GapCounter()
        gaps.onPressure(nanos(10.0))
        gaps.onPressure(nanos(9.8)) // late
        gaps.onPressure(nanos(10.1))
        assertEquals(0, gaps.gapsOverThreshold)
        assertEquals(0.1, gaps.longestGapS, 1e-6)
    }

    @Test
    fun aFreshCounterStartsAtZero() {
        val gaps = GapCounter()
        gaps.onPressure(nanos(1.0))
        assertEquals(0.0, gaps.longestGapS, 0.0)
        assertEquals(0, gaps.gapsOverThreshold)
    }
}
