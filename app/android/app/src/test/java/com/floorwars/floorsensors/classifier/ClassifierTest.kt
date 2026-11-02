package com.floorwars.floorsensors.classifier

import com.floorwars.floorsensors.segmenter.Segment
import org.junit.Assert.assertEquals
import org.junit.Test

// One test per row of the plan 3.3 thresholds table, each threshold hit on both sides.
class ClassifierTest {
    private val classifier = Classifier()

    // Derives the other fields the way the segmenter does.
    private fun segment(ascentM: Double, durationS: Double, steps: Int) = Segment(
        startNanos = 0,
        endNanos = (durationS * 1e9).toLong(),
        ascentM = ascentM,
        durationS = durationS,
        vertSpeedMps = ascentM / durationS,
        steps = steps,
        stepsPerM = steps / ascentM,
        pressureStepsMatch = stepsScored(steps, ascentM) > 0
    )

    private fun assertVerdict(expected: Verdict, s: Segment) {
        assertEquals(expected, classifier.verdict(s))
        assertEquals(expected.segmentClass, classifier.classify(s))
    }

    @Test
    fun verticalSpeedRow() {
        // Stairs 0.1 to 0.9 m/s inclusive, at 6 steps per metre over 60 s.
        assertVerdict(Verdict.STAIRS, segment(ascentM = 6.0, durationS = 60.0, steps = 36))
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 5.94, durationS = 60.0, steps = 36))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 54.0, durationS = 60.0, steps = 324))
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 54.06, durationS = 60.0, steps = 324))
        // Elevator strictly above 0.5 m/s.
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 30.0, durationS = 60.0, steps = 0))
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 30.06, durationS = 60.0, steps = 0))
        // The rows overlap from 0.5 to 0.9 m/s: no steps is a lift, matching steps are stairs.
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 36.0, durationS = 60.0, steps = 0))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 36.0, durationS = 60.0, steps = 216))
        // A stairs-like step rate at lift speed is not stairs.
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 60.06, durationS = 60.0, steps = 360))
    }

    @Test
    fun stepsPerMetreRow() {
        // Stairs 4 to 10 inclusive, over 10 m at 0.2 m/s.
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 10.0, durationS = 50.0, steps = 39))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 10.0, durationS = 50.0, steps = 40))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 10.0, durationS = 50.0, steps = 100))
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 10.0, durationS = 50.0, steps = 101))
        // Elevator strictly below 1, over 10 m at 2 m/s: stepping in and out is allowed.
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 10.0, durationS = 5.0, steps = 9))
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 10.0, durationS = 5.0, steps = 10))
        // Other: ascent without steps at stairs speed (too slow for a lift, too long for a blow).
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 9.0, durationS = 30.0, steps = 0))
    }

    @Test
    fun windowLengthRow() {
        // Stairs 5 s to 3 min inclusive, at 0.5 m/s and 6 steps per metre.
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 2.495, durationS = 4.99, steps = 15))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 2.5, durationS = 5.0, steps = 15))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 90.0, durationS = 180.0, steps = 540))
        assertVerdict(Verdict.NO_MATCH, segment(ascentM = 90.005, durationS = 180.01, steps = 540))
        // Elevator: any window, short or long.
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 3.0, durationS = 1.5, steps = 1))
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 300.0, durationS = 200.0, steps = 0))
    }

    @Test
    fun pointsRow() {
        // Plan section 6 example: 58 steps over 9.7 m in 40 s.
        assertEquals(58, classifier.points(segment(ascentM = 9.7, durationS = 40.0, steps = 58)))
        assertEquals(0, classifier.points(segment(ascentM = 10.0, durationS = 5.0, steps = 9)))
        assertEquals(0, classifier.points(segment(ascentM = 10.0, durationS = 50.0, steps = 101)))
        assertEquals(0, classifier.points(segment(ascentM = 0.0, durationS = 20.0, steps = 40)))
    }

    @Test
    fun shakeIsRejected() {
        // Steps with no ascent; the boundary is the 2.0 m scoring minimum.
        assertVerdict(Verdict.SHAKE, segment(ascentM = 0.0, durationS = 20.0, steps = 40))
        assertVerdict(Verdict.SHAKE, segment(ascentM = 1.99, durationS = 10.0, steps = 12))
        assertVerdict(Verdict.STAIRS, segment(ascentM = 2.0, durationS = 10.0, steps = 12))
    }

    @Test
    fun blowIsRejected() {
        // A 1 hPa bump falling back to baseline in 2 s reads as an 8 m rise at 4 m/s.
        assertVerdict(Verdict.BLOW, segment(ascentM = 8.0, durationS = 2.0, steps = 0))
        assertVerdict(Verdict.BLOW, segment(ascentM = 7.485, durationS = 4.99, steps = 0))
        assertVerdict(Verdict.ELEVATOR, segment(ascentM = 7.5, durationS = 5.0, steps = 0))
    }
}
