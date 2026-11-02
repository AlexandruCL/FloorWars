package com.floorwars.floorsensors.segmenter

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.TraceCsv
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SegmenterTest {
    private class Trace(val name: String, val pressure: List<RawSensorEvent>, val steps: List<RawSensorEvent>)

    // Gradle runs unit tests from app/android/app.
    private fun fixtures(label: String): List<Trace> {
        val files = File("../../../fixtures/synthetic").listFiles { f -> f.name.startsWith("synthetic_${label}_") }!!
        assertTrue("no fixtures for $label", files.isNotEmpty())
        return files.sortedBy { it.name }.map { file ->
            val trace = TraceCsv.read(file.readLines())
            Trace(file.name, trace.pressure, trace.steps)
        }
    }

    private fun event(nanos: Long, value: Float) = RawSensorEvent(0, nanos, floatArrayOf(value))

    // One step every periodS over the span of the pressure readings.
    private fun stepsEvery(periodS: Double, pressure: List<RawSensorEvent>): List<RawSensorEvent> {
        val first = pressure.first().timestampNanos
        val last = pressure.last().timestampNanos
        return generateSequence(first) { it + (periodS * 1e9).toLong() }.takeWhile { it <= last }.map { event(it, 1f) }.toList()
    }

    private val segmenter = Segmenter()

    @Test
    fun flatWalkHasNoAscent() {
        for (trace in fixtures("walk_flat")) {
            assertTrue(trace.name, trace.steps.isNotEmpty())
            assertEquals(trace.name, emptyList<Segment>(), segmenter.segment(trace.pressure, trace.steps))
        }
    }

    @Test
    fun stairClimbMatchesWithStepsLateAndOutOfOrder() {
        for (trace in fixtures("stairs_up")) {
            // Worst lag seen on a real phone (240 ms), delivered in reverse order.
            val lateSteps = trace.steps.map { event(it.timestampNanos + 240_000_000, 1f) }.reversed()
            val segments = segmenter.segment(trace.pressure.shuffled(java.util.Random(1)), lateSteps)
            assertEquals(trace.name, 1, segments.size)
            val climb = segments.single()
            assertTrue("${trace.name}: $climb", climb.pressureStepsMatch)
            // Some traces start with a few flat steps to the stairs; those are not part of the climb.
            assertTrue("${trace.name}: $climb", climb.steps in trace.steps.size - 3..trace.steps.size)
            assertTrue("${trace.name}: $climb", climb.vertSpeedMps in 0.1..0.9)
        }
    }

    @Test
    fun elevatorRampDoesNotMatch() {
        for (trace in fixtures("elevator_up")) {
            // A few steps while riding, as in StepScoringTest.elevatorScoresZero.
            val segments = segmenter.segment(trace.pressure, stepsEvery(2.0, trace.pressure))
            assertEquals(trace.name, 1, segments.size)
            val ride = segments.single()
            assertTrue("${trace.name}: $ride", ride.steps > 0 && ride.ascentM > 5.0)
            assertFalse("${trace.name}: $ride", ride.pressureStepsMatch)
        }
    }

    @Test
    fun shakeGivesStepsButNoAscent() {
        for (trace in fixtures("shake")) {
            // The synthetic shake traces carry no step rows; shaking a real phone triggers the step detector.
            val segments = segmenter.segment(trace.pressure, stepsEvery(0.4, trace.pressure))
            assertEquals(trace.name, emptyList<Segment>(), segments)
        }
    }

    @Test
    fun blowSpikesAreNotAscent() {
        for (trace in fixtures("blow")) {
            assertTrue(trace.name, trace.steps.isEmpty())
            assertEquals(trace.name, emptyList<Segment>(), segmenter.segment(trace.pressure, trace.steps))
        }
    }

    @Test
    fun weatherDriftIsNotAscent() {
        // 20 minutes at 10 Hz while pressure falls 3 hPa per hour (a fast storm), walking the whole time.
        val pressure = (0 until 12_000).map { i -> event(i * 100_000_000L, (1013.0 - 3.0 * i / 36_000).toFloat()) }
        assertEquals(emptyList<Segment>(), segmenter.segment(pressure, stepsEvery(0.5, pressure)))
    }
}
