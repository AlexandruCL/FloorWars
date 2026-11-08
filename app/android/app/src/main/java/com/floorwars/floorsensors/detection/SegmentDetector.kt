package com.floorwars.floorsensors.detection

import com.floorwars.floorsensors.RawSensorEvent
import com.floorwars.floorsensors.classifier.CLASSIFIER_VERSION
import com.floorwars.floorsensors.classifier.Classifier
import com.floorwars.floorsensors.classifier.RULES_STAIR_PROB
import com.floorwars.floorsensors.classifier.Verdict
import com.floorwars.floorsensors.outbox.OutboxSegment
import com.floorwars.floorsensors.outbox.SegmentOutbox
import com.floorwars.floorsensors.segmenter.LiveSegmenter
import com.floorwars.floorsensors.segmenter.Segment
import java.util.UUID

// Pure Kotlin, no Android imports, so JUnit can drive it.

data class ActiveCheckin(
    val id: String,
    val buildingId: Int,
    val buildingName: String?,
    val validUntilMs: Long
) {
    fun isValidAt(nowMs: Long) = id.isNotEmpty() && buildingId >= 1 && validUntilMs > nowMs
}

// The server's bounds (contracts/openapi.yaml, SegmentFields). Kept apart from ScoringThresholds,
// which tune; these change only with the contract.
object ContractBounds {
    const val MIN_ASCENT_M = 2.0
    const val MAX_ASCENT_M = 120.0
    const val MIN_STEPS = 1
    const val MAX_STEPS = 2000
}

// Live segments in, outbox rows out. Plan 3.4 layer 1: only STAIRS with a pressure-steps match
// inside the contract bounds are stored; the rest are counted, not kept.
class SegmentDetector(
    private val outbox: SegmentOutbox,
    // Wall-clock ms = elapsedRealtimeNanos / 1e6 + this, taken once when detection starts,
    // so a clock change mid-session cannot stretch or shrink a duration.
    private val wallClockOffsetMs: Long,
    private val hasBarometer: Boolean,
    private val checkinAt: (startMs: Long) -> ActiveCheckin?,
    private val live: LiveSegmenter = LiveSegmenter(),
    private val classifier: Classifier = Classifier(),
    private val newId: () -> String = { UUID.randomUUID().toString() }
) {
    // Written on the sensor thread, read by getStatus on another.
    @Volatile
    var rejectedCount = 0
        private set

    @Volatile
    var noCheckinCount = 0
        private set

    @Volatile
    var lastSegmentMs: Long? = null
        private set

    val flushedCount get() = live.flushedCount
    val truncatedCount get() = live.truncatedCount

    fun add(pressure: List<RawSensorEvent>, steps: List<RawSensorEvent>) =
        live.add(pressure, steps).forEach(::store)

    fun stop() = live.stop().forEach(::store)

    private fun store(s: Segment) {
        val storable = classifier.verdict(s) == Verdict.STAIRS && s.pressureStepsMatch &&
            s.ascentM in ContractBounds.MIN_ASCENT_M..ContractBounds.MAX_ASCENT_M &&
            s.steps in ContractBounds.MIN_STEPS..ContractBounds.MAX_STEPS
        if (!storable) {
            rejectedCount++
            return
        }
        val startMs = toWallMs(s.startNanos)
        val checkin = checkinAt(startMs)
        if (checkin == null) {
            noCheckinCount++
            return
        }
        outbox.insert(
            OutboxSegment(
                id = newId(),
                checkinId = checkin.id,
                buildingId = checkin.buildingId,
                startMs = startMs,
                endMs = toWallMs(s.endNanos),
                ascentM = s.ascentM,
                durationS = s.durationS,
                vertSpeedMps = s.vertSpeedMps,
                steps = s.steps,
                stepsPerM = s.stepsPerM,
                pressureStepsMatch = s.pressureStepsMatch,
                stairProb = RULES_STAIR_PROB,
                classifierVersion = CLASSIFIER_VERSION,
                hasBarometer = hasBarometer
            )
        )
        lastSegmentMs = toWallMs(s.endNanos)
    }

    private fun toWallMs(elapsedNanos: Long) = elapsedNanos / 1_000_000 + wallClockOffsetMs
}
