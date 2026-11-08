package com.floorwars.floorsensors.detection

import com.floorwars.floorsensors.classifier.ClassifierThresholds
import com.floorwars.floorsensors.segmenter.LiveSegmenterParams

// Detection keeps running this long after valid_until: a STAIRS climb that starts just before
// expiry lasts at most MAX_STAIRS_WINDOW_S and needs CLOSE_S more data to close. It still counts
// for that check-in (plan section 2); a climb starting after valid_until counts for none.
const val EXPIRY_GRACE_S = ClassifierThresholds.MAX_STAIRS_WINDOW_S + LiveSegmenterParams.CLOSE_S

fun detectionEndMs(validUntilMs: Long) = validUntilMs + (EXPIRY_GRACE_S * 1000).toLong()

// Which check-in was active when. A climb belongs to the one active at its start (plan section 2),
// even when it is emitted after a newer check-in replaced it. Times are on the detector's clock.
class CheckinHistory {
    private class Entry(val checkin: ActiveCheckin, val fromMs: Long, var untilMs: Long)

    private val entries = ArrayList<Entry>()

    // A new check-in ends the previous one now, as on the server.
    @Synchronized
    fun set(checkin: ActiveCheckin, nowMs: Long) {
        end(nowMs)
        // A climb is emitted within minutes of its start, so older entries can go.
        entries.removeAll { it.untilMs < nowMs - KEEP_MS }
        entries += Entry(checkin, nowMs, checkin.validUntilMs)
    }

    @Synchronized
    fun end(nowMs: Long) {
        entries.lastOrNull()?.let { it.untilMs = minOf(it.untilMs, nowMs) }
    }

    @Synchronized
    fun at(startMs: Long): ActiveCheckin? =
        entries.lastOrNull { startMs >= it.fromMs && startMs <= it.untilMs }?.checkin

    private companion object {
        // Well past the longest wait from a climb's start to its emission (window plus grace).
        const val KEEP_MS = 60 * 60 * 1000L
    }
}
