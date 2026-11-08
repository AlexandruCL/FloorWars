package com.floorwars.floorsensors.detection

// A pressure gap longer than this means the phone stopped delivering (CPU asleep, service throttled):
// at 10 to 25 Hz, normal gaps are under 0.1 s. Event timestamps are sensor times, so the 5 s sensor
// batching does not show up as a gap.
const val GAP_THRESHOLD_S = 5.0

// Per check-in session: the longest gap between pressure events and how many exceed the threshold.
// Local diagnostics for W3-7, never uploaded. Fed on the sensor thread, read by getStatus.
class GapCounter(private val thresholdS: Double = GAP_THRESHOLD_S) {
    private var lastNanos: Long? = null

    @Volatile
    var longestGapS = 0.0
        private set

    @Volatile
    var gapsOverThreshold = 0
        private set

    fun onPressure(timestampNanos: Long) {
        val last = lastNanos
        if (last != null && timestampNanos > last) {
            val gapS = (timestampNanos - last) / 1e9
            if (gapS > longestGapS) longestGapS = gapS
            if (gapS > thresholdS) gapsOverThreshold++
        }
        // Out-of-order events (within the step lag) must not count as a gap twice.
        if (last == null || timestampNanos > last) lastNanos = timestampNanos
    }
}
