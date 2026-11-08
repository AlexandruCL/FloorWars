package com.floorwars.floorsensors.segmenter

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.TraceCsv
import com.floorwars.floorsensors.classifier.ClassifierThresholds
import java.io.File
import kotlin.math.exp
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class LiveSegmenterTest {
    private class Stream(
        val name: String,
        val pressure: List<RawSensorEvent>,
        val steps: List<RawSensorEvent>
    )

    // Gradle runs unit tests from app/android/app. labels.csv in each folder is not a trace.
    private fun traces(dir: String): List<Stream> = File("../../../$dir")
        .listFiles { f -> f.name.endsWith(".csv") && f.name != "labels.csv" }!!
        .sortedBy { it.name }
        .map { file ->
            val trace = TraceCsv.read(file.readLines())
            Stream("$dir/${file.name}", trace.pressure, trace.steps)
        }

    private val allTraces by lazy { traces("traces") + traces("fixtures/synthetic") }

    private fun event(nanos: Long, value: Float) = RawSensorEvent(0, nanos, floatArrayOf(value))

    private fun nanos(s: Double) = (s * 1e9).toLong()

    // A step reaches the app up to 240 ms after pressure with the same timestamp (trace_format 7).
    private val stepArrivalLag = nanos(0.24)

    // Delivers events in arrival order, in chunks of chunkS seconds (null: one event per call).
    private fun feed(live: LiveSegmenter, s: Stream, chunkS: Double?): List<Segment> {
        val arrivals = (
            s.pressure.map { it.timestampNanos to (it to true) } +
                s.steps.map { it.timestampNanos + stepArrivalLag to (it to false) }
            ).sortedBy { it.first }
        val out = mutableListOf<Segment>()
        if (chunkS == null) {
            for ((_, pair) in arrivals) {
                val (e, isPressure) = pair
                out +=
                    if (isPressure) {
                        live.add(
                            listOf(e),
                            emptyList()
                        )
                    } else {
                        live.add(emptyList(), listOf(e))
                    }
            }
            return out
        }
        val t0 = arrivals.first().first
        for ((_, chunk) in arrivals.groupBy { (it.first - t0) / nanos(chunkS) }.toSortedMap()) {
            out += live.add(
                chunk.filter { it.second.second }.map { it.second.first },
                chunk.filter { !it.second.second }.map { it.second.first }
            )
        }
        return out
    }

    private fun batch(s: Stream) = Segmenter().segment(s.pressure, s.steps)

    @Test
    fun chunkedReplayEqualsBatchOnEveryTrace() {
        assertEquals("21 real + 24 synthetic traces", 45, allTraces.size)
        for (chunkS in listOf(1.0, 5.0, null)) {
            for (s in allTraces) {
                val live = LiveSegmenter()
                val emitted = feed(live, s, chunkS) + live.stop()
                assertEquals("${s.name} chunk=$chunkS", batch(s), emitted)
                assertEquals("${s.name} chunk=$chunkS truncated", 0, live.truncatedCount)
            }
        }
    }

    // Every trace end to end, 30 s of flat pressure between them, so the window trims many times.
    private fun longStream(): Stream {
        val pressure = mutableListOf<RawSensorEvent>()
        val steps = mutableListOf<RawSensorEvent>()
        var nextStart = 0L
        var lastValue = 1000f
        for (s in allTraces) {
            val t0 = s.pressure.minOf { it.timestampNanos }
            val shift = nextStart - t0
            val offset = lastValue - s.pressure.minBy { it.timestampNanos }.values[0]
            s.pressure.mapTo(pressure) { event(it.timestampNanos + shift, it.values[0] + offset) }
            s.steps.mapTo(steps) { event(it.timestampNanos + shift, 1f) }
            val end = pressure.maxOf { it.timestampNanos }
            lastValue = pressure.maxBy { it.timestampNanos }.values[0]
            for (k in 1..750) pressure += event(end + k * nanos(0.04), lastValue)
            nextStart = end + nanos(30.04)
        }
        return Stream("long", pressure, steps)
    }

    @Test
    fun longStreamWithTrimmingEqualsBatch() {
        val s = longStream()
        val spanS = (s.pressure.last().timestampNanos - s.pressure.first().timestampNanos) / 1e9
        assertTrue(
            "stream $spanS s must be far longer than the window",
            spanS > 5 * LiveSegmenterParams.WINDOW_S
        )
        val expected = batch(s)
        assertTrue("need several segments, got ${expected.size}", expected.size >= 5)
        // One event per call. A pass costs the same whatever the chunk size, so one mode keeps CI fast.
        val live = LiveSegmenter()
        val whileRunning = feed(live, s, null)
        assertTrue("most segments close before stop", whileRunning.size >= expected.size - 1)
        assertEquals(expected, whileRunning + live.stop())
        assertEquals(0, live.truncatedCount)
    }

    // Flat, then a climb at speedMps for climbS with stepsPerM steps per metre, then flat; 25 Hz.
    private fun climb(
        flatS: Double,
        climbS: Double,
        afterS: Double,
        speedMps: Double = 0.2,
        stepsPerM: Double = 6.0
    ): Stream {
        val start = nanos(1000.0)
        val totalS = flatS + climbS + afterS
        val pressure = (0..(totalS * 25).toInt()).map { i ->
            val t = i / 25.0
            val alt = speedMps * (t - flatS).coerceIn(0.0, climbS)
            event(start + nanos(t), (1000.0 * exp(-alt / SegmenterParams.SCALE_HEIGHT_M)).toFloat())
        }
        val period = 1 / (speedMps * stepsPerM)
        val steps = generateSequence(flatS) { it + period }.takeWhile { it < flatS + climbS }
            .map { event(start + nanos(it), 1f) }.toList()
        return Stream("climb", pressure, steps)
    }

    private fun Stream.until(s: Double): Stream {
        val cut = pressure.first().timestampNanos + nanos(s)
        return Stream(
            name,
            pressure.filter { it.timestampNanos < cut },
            steps.filter {
                it.timestampNanos <
                    cut
            }
        )
    }

    private fun Stream.after(s: Double): Stream {
        val cut = pressure.first().timestampNanos + nanos(s)
        return Stream(
            name,
            pressure.filter { it.timestampNanos >= cut },
            steps.filter {
                it.timestampNanos >=
                    cut
            }
        )
    }

    @Test
    fun climbStartingInOneCallAndEndingInTheNextIsEmittedOnceWhenClosed() {
        val s = climb(flatS = 20.0, climbS = 30.0, afterS = 40.0)
        val expected = batch(s)
        assertEquals(1, expected.size)
        val live = LiveSegmenter()
        val first = s.until(35.0)
        assertEquals(
            "open climb is not emitted",
            emptyList<Segment>(),
            live.add(first.pressure, first.steps)
        )
        val rest = s.after(35.0)
        assertEquals(expected, live.add(rest.pressure, rest.steps))
        assertEquals("nothing left to flush", emptyList<Segment>(), live.stop())
        assertEquals(0, live.flushedCount)
    }

    @Test
    fun stopInTheMiddleOfAClimbFlushesItOnce() {
        val s = climb(flatS = 20.0, climbS = 60.0, afterS = 0.0).until(50.0)
        val live = LiveSegmenter()
        assertEquals(emptyList<Segment>(), feed(live, s, 1.0))
        assertEquals(batch(s), live.stop())
        assertEquals(1, batch(s).size)
        assertEquals(1, live.flushedCount)
        assertEquals("a second stop emits nothing", emptyList<Segment>(), live.stop())
    }

    @Test
    fun lateStepsAcrossAChunkEdgeAreCounted() {
        val s = climb(flatS = 20.0, climbS = 30.0, afterS = 40.0)
        val expected = batch(s).single()
        val edge = s.pressure.first().timestampNanos + nanos(35.0)
        val lag = nanos(0.24)
        // Steps just before the edge arrive in the next call, newest first.
        val (late, onTime) = s.steps.partition { it.timestampNanos in edge - lag until edge }
        assertTrue(late.isNotEmpty())
        val live = LiveSegmenter()
        val first = s.until(35.0)
        val rest = s.after(35.0)
        val out = live.add(first.pressure, onTime.filter { it.timestampNanos < edge }) +
            live.add(rest.pressure, late.reversed() + rest.steps) + live.stop()
        assertEquals(listOf(expected), out)
    }

    @Test
    fun noDuplicateEmissionsAcrossManyCalls() {
        val s = climb(flatS = 20.0, climbS = 30.0, afterS = 40.0)
        val live = LiveSegmenter()
        val out = feed(live, s, null).toMutableList()
        // Keep the window busy with flat pressure: the closed climb must not come out again.
        val last = s.pressure.last()
        for (k in 1..2000) {
            out +=
                live.add(
                    listOf(event(last.timestampNanos + k * nanos(0.04), last.values[0])),
                    emptyList()
                )
        }
        out += live.stop()
        assertEquals(batch(s), out)
    }

    @Test
    fun climbLongerThanTheWindowIsCountedNotEmitted() {
        val s = climb(flatS = 20.0, climbS = 300.0, afterS = 60.0, speedMps = 0.1)
        val live = LiveSegmenter()
        val out = feed(live, s, 1.0) + live.stop()
        assertEquals(emptyList<Segment>(), out)
        assertEquals(1, live.truncatedCount)
        assertEquals(0, live.flushedCount)
    }

    @Test
    fun climbRightAfterADeliveryGapIsEmitted() {
        // 300 s flat, no events for 300 s (a throttled phone), then a climb 5 s after they resume.
        val full = climb(flatS = 605.0, climbS = 30.0, afterS = 40.0)
        val t0 = full.pressure.first().timestampNanos
        val gap = t0 + nanos(300.0) until t0 + nanos(600.0)
        val s = Stream("gap", full.pressure.filter { it.timestampNanos !in gap }, full.steps)
        val expected = batch(s)
        assertEquals(1, expected.size)
        val live = LiveSegmenter()
        assertEquals(expected, feed(live, s, null) + live.stop())
        assertEquals(0, live.truncatedCount)
    }

    @Test
    fun windowHoldsTheLongestStairsClimb() {
        with(LiveSegmenterParams) {
            assertTrue(
                WINDOW_S >=
                    ClassifierThresholds.MAX_STAIRS_WINDOW_S + CLOSE_S + EDGE_S
            )
        }
    }
}
