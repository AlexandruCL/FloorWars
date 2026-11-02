package com.floorwars.floorsensors.classifier

import com.floorwars.floorsensors.segmenter.Segment

// Pure Kotlin, no Android imports, so JUnit can test it off-device (plan 4.3).

enum class SegmentClass { STAIRS, ELEVATOR, OTHER }

// Why a segment got its class, so a rejection can be read back from a trace replay.
enum class Verdict(val segmentClass: SegmentClass) {
    STAIRS(SegmentClass.STAIRS),
    ELEVATOR(SegmentClass.ELEVATOR),
    SHAKE(SegmentClass.OTHER), // steps with no ascent
    BLOW(SegmentClass.OTHER), // brief rise with no steps
    NO_MATCH(SegmentClass.OTHER) // outside both the stairs and the elevator rows of plan 3.3
}

// Starting thresholds from the plan 3.3 table; all tune in W2-4 on real traces. Steps per
// metre and minimum ascent live in ScoringThresholds and reach stairs via pressureStepsMatch.
object ClassifierThresholds {
    const val MIN_STAIRS_SPEED_MPS = 0.1 // inclusive
    const val MAX_STAIRS_SPEED_MPS = 0.9 // inclusive
    const val MIN_STAIRS_WINDOW_S = 5.0 // inclusive
    const val MAX_STAIRS_WINDOW_S = 180.0 // inclusive

    // Exclusive. Was 1.0, which missed both real rides at 0.586 and 0.693 m/s (docs/evaluation.md).
    const val MIN_ELEVATOR_SPEED_MPS = 0.5
    const val MAX_ELEVATOR_STEPS_PER_M = 1.0 // exclusive: "below 1", as validator check 9

    // Not in the 3.3 table: a no-step rise shorter than any stairs window is a blow bump, not a lift.
    const val MAX_BLOW_WINDOW_S = MIN_STAIRS_WINDOW_S // exclusive

    // Steps over less than this ascent are a shake; equals the validator's FLAT_MAX_ASCENT_M.
    const val MIN_SHAKE_FREE_ASCENT_M = ScoringThresholds.MIN_ASCENT_M
}

class Classifier {
    fun classify(segment: Segment): SegmentClass = verdict(segment).segmentClass

    fun verdict(segment: Segment): Verdict = with(ClassifierThresholds) {
        val s = segment
        when {
            s.steps > 0 && s.ascentM < MIN_SHAKE_FREE_ASCENT_M -> Verdict.SHAKE
            s.steps == 0 && s.durationS < MAX_BLOW_WINDOW_S -> Verdict.BLOW
            s.pressureStepsMatch &&
                s.vertSpeedMps in MIN_STAIRS_SPEED_MPS..MAX_STAIRS_SPEED_MPS &&
                s.durationS in MIN_STAIRS_WINDOW_S..MAX_STAIRS_WINDOW_S -> Verdict.STAIRS
            s.vertSpeedMps > MIN_ELEVATOR_SPEED_MPS &&
                s.stepsPerM < MAX_ELEVATOR_STEPS_PER_M -> Verdict.ELEVATOR
            else -> Verdict.NO_MATCH
        }
    }

    // Plan 3.3 "Points awarded": the window's steps for stairs, none otherwise.
    fun points(segment: Segment): Int =
        if (classify(segment) == SegmentClass.STAIRS) segment.steps else 0
}
