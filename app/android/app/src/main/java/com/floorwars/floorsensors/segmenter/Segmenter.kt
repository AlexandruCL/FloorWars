package com.floorwars.floorsensors.segmenter

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.classifier.stepsScored
import kotlin.math.ln

// Pure Kotlin, no Android imports, so JUnit can replay recorded traces (plan 4.3).

data class Segment(
    val startNanos: Long,
    val endNanos: Long,
    val ascentM: Double,
    val durationS: Double,
    val vertSpeedMps: Double,
    val steps: Int,
    val stepsPerM: Double,
    val pressureStepsMatch: Boolean
)

// Windows are in seconds, not samples: phones log pressure at 10 to 25 Hz (plan 3.3). All tune.
object SegmenterParams {
    // Centred 8 s median: drops blow bumps (about 2 s each, in pairs) and keeps ramp edges sharp.
    const val SMOOTHING_WINDOW_S = 8.0
    const val SPEED_WINDOW_S = 4.0

    // Weather moves under 0.01 m/s (1 hPa per hour is about 0.002 m/s); stairs climb at 0.1 m/s and up.
    const val MIN_CLIMB_SPEED_MPS = 0.05

    // Landings between flights: pauses up to this long stay in one segment.
    const val MAX_PAUSE_S = 15.0

    // Below this the ascent is barometer noise, not a climb.
    const val MIN_SEGMENT_ASCENT_M = 1.0

    // The step detector lags pressure by up to 240 ms (docs/trace_format.md section 7).
    const val STEP_LAG_S = 0.3

    // Isothermal scale height at 15 C: 0.12 hPa per metre near sea level.
    const val SCALE_HEIGHT_M = 8434.0
}

class Segmenter {
    // Inputs need not be sorted: the two sensors deliver out of order by up to 300 ms.
    fun segment(pressure: List<RawSensorEvent>, steps: List<RawSensorEvent>): List<Segment> =
        with(SegmenterParams) {
            val samples = pressure.sortedBy { it.timestampNanos }
            val n = samples.size
            if (n < 2) return emptyList()
            val t = LongArray(n) { samples[it].timestampNanos }
            val raw = DoubleArray(n) { samples[it].values.first().toDouble() }
            val smooth = DoubleArray(n)
            forEachWindow(t, SMOOTHING_WINDOW_S) { i, lo, hi ->
                // Shrink to a symmetric window at the ends, or a climb under way at an end reads as flat.
                val k = minOf(i - lo, hi - i)
                val window = raw.copyOfRange(i - k, i + k + 1).apply { sort() }
                smooth[i] = window[window.size / 2]
            }
            val alt = DoubleArray(n) { -SCALE_HEIGHT_M * ln(smooth[it]) }
            val climbing = BooleanArray(n)
            forEachWindow(t, SPEED_WINDOW_S) { i, lo, hi ->
                if (hi > lo) {
                    val speed = (alt[hi] - alt[lo]) / seconds(t[hi] - t[lo])
                    climbing[i] = speed >= MIN_CLIMB_SPEED_MPS
                }
            }

            // Climbing runs as [start, end] sample indices, joined across short pauses.
            val runs = mutableListOf<IntArray>()
            for (i in 0 until n) {
                if (!climbing[i]) continue
                val last = runs.lastOrNull()
                if (last != null && seconds(t[i] - t[last[1]]) <= MAX_PAUSE_S) {
                    last[1] = i
                } else {
                    runs.add(intArrayOf(i, i))
                }
            }

            val lagNanos = (STEP_LAG_S * 1e9).toLong()
            runs.mapNotNull { (start, end) ->
                val ascentM = alt[end] - alt[start]
                val durationS = seconds(t[end] - t[start])
                if (ascentM < MIN_SEGMENT_ASCENT_M || durationS <= 0) return@mapNotNull null
                val stepCount = steps.count { it.timestampNanos in t[start]..t[end] + lagNanos }
                Segment(
                    startNanos = t[start],
                    endNanos = t[end],
                    ascentM = ascentM,
                    durationS = durationS,
                    vertSpeedMps = ascentM / durationS,
                    steps = stepCount,
                    stepsPerM = stepCount / ascentM,
                    pressureStepsMatch = stepsScored(stepCount, ascentM) > 0
                )
            }
        }

    private fun seconds(nanos: Long) = nanos / 1e9

    // Calls block(i, lo, hi), where lo..hi are the samples within windowS / 2 of sample i.
    private inline fun forEachWindow(
        t: LongArray,
        windowS: Double,
        block: (Int, Int, Int) -> Unit
    ) {
        val half = (windowS / 2 * 1e9).toLong()
        var lo = 0
        var hi = 0
        for (i in t.indices) {
            while (t[lo] < t[i] - half) lo++
            while (hi + 1 < t.size && t[hi + 1] <= t[i] + half) hi++
            block(i, lo, hi)
        }
    }
}
