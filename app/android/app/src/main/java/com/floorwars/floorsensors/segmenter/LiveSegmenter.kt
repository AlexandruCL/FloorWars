package com.floorwars.floorsensors.segmenter

import com.floorwars.floorsensors.RawSensorEvent

// Runs the batch Segmenter on a bounded rolling window, so the rules exist once.
object LiveSegmenterParams {
    // How far each sample's climbing flag reaches: half the median window plus half the speed window.
    const val CONTEXT_S =
        SegmenterParams.SMOOTHING_WINDOW_S / 2 + SegmenterParams.SPEED_WINDOW_S / 2

    // A segment is final once this much pressure has arrived after its end: a climb within
    // MAX_PAUSE_S would still join it, and the flags up to there need CONTEXT_S of data after.
    const val CLOSE_S = SegmenterParams.MAX_PAUSE_S + CONTEXT_S + SegmenterParams.STEP_LAG_S

    // After a trim, samples within CONTEXT_S of the cutoff read a shrunken median, and a climb within
    // MAX_PAUSE_S of those would join them. A segment starting closer than this to the cutoff is not trusted.
    const val EDGE_S = CONTEXT_S + SegmenterParams.MAX_PAUSE_S

    // Must hold the longest STAIRS climb (180 s) plus CLOSE_S and EDGE_S, about 222 s. A segment is
    // taken at the first pass after it closes, and the window was trimmed before that, so neither
    // batched delivery nor EVAL_INTERVAL_S eats into this. A longer climb cannot be STAIRS, so cutting
    // it at the edge loses no points.
    const val WINDOW_S = 240.0

    // Re-run the segmenter at most once per this much pressure time; it only delays emission. One
    // pass over a full window takes about 16 ms on a desktop JVM, so once a second would cost a phone
    // several percent of a core for the whole check-in. Matches the 5 s sensor batching.
    const val EVAL_INTERVAL_S = 5.0
}

// Takes events as they arrive, in any order within the step lag, and returns each segment once,
// after it has closed. Not thread-safe: call from one thread. Timestamps are elapsedRealtimeNanos.
class LiveSegmenter(
    private val windowS: Double = LiveSegmenterParams.WINDOW_S,
    private val segmenter: Segmenter = Segmenter()
) {
    private val pressure = mutableListOf<RawSensorEvent>()
    private val steps = mutableListOf<RawSensorEvent>()
    private var newestNanos = Long.MIN_VALUE
    private var lastEvalNanos: Long? = null

    // The last trim's cutoff; Long.MIN_VALUE until the first trim. The cutoff, not the oldest sample
    // kept: after a delivery gap the oldest sample is far later, and batch reads that edge the same way.
    private var trimmedAtNanos = Long.MIN_VALUE

    // Every segment ending at or before this has been emitted or counted; a new one starts after it.
    private var lastEmittedEndNanos = Long.MIN_VALUE

    // Segments emitted by stop() while still open.
    var flushedCount = 0
        private set

    // Segments cut by the window edge; counted, never emitted.
    var truncatedCount = 0
        private set

    fun add(newPressure: List<RawSensorEvent>, newSteps: List<RawSensorEvent>): List<Segment> {
        pressure.addAll(newPressure)
        steps.addAll(newSteps)
        for (e in newPressure) newestNanos = maxOf(newestNanos, e.timestampNanos)
        val last = lastEvalNanos
        val interval = seconds(LiveSegmenterParams.EVAL_INTERVAL_S)
        if (pressure.isEmpty() ||
            (last != null && newestNanos - last < interval)
        ) {
            return emptyList()
        }
        lastEvalNanos = newestNanos
        val closedBefore = newestNanos - seconds(LiveSegmenterParams.CLOSE_S)
        val emitted = take(segmenter.segment(pressure, steps).filter { it.endNanos < closedBefore })
        trim()
        return emitted
    }

    // Emits every segment not yet emitted, open climbs included, and empties the window.
    fun stop(): List<Segment> {
        val emitted = take(segmenter.segment(pressure, steps))
        flushedCount += emitted.size
        pressure.clear()
        steps.clear()
        return emitted
    }

    private fun take(segments: List<Segment>): List<Segment> {
        val edge = if (trimmedAtNanos == Long.MIN_VALUE) {
            Long.MIN_VALUE
        } else {
            trimmedAtNanos + seconds(LiveSegmenterParams.EDGE_S)
        }
        val fresh = segments.filter { it.startNanos > lastEmittedEndNanos }
        fresh.lastOrNull()?.let { lastEmittedEndNanos = it.endNanos }
        val (cut, whole) = fresh.partition { it.startNanos < edge }
        // A segment taken for the first time ends at least WINDOW_S - CLOSE_S after the last cutoff, far
        // past the edge zone. So one that also ends inside the zone is an artefact of the shrunken median
        // there (a raw blow spike reads as a jump), not a climb; one that runs past it was cut, and is
        // too long to be STAIRS.
        truncatedCount += cut.count { it.endNanos >= edge }
        return whole
    }

    private fun trim() {
        val cutoff = newestNanos - seconds(windowS)
        if (pressure.none { it.timestampNanos < cutoff }) return
        pressure.removeAll { it.timestampNanos < cutoff }
        steps.removeAll { it.timestampNanos < cutoff }
        trimmedAtNanos = cutoff
    }

    private fun seconds(s: Double) = (s * 1e9).toLong()
}
