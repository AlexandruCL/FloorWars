package com.floorwars.floorsensors.classifier

import org.junit.Assert.assertEquals
import org.junit.Test

class StepScoringTest {
    @Test
    fun stairsScoreAllTheirSteps() {
        // Plan section 6 example: 58 steps over 9.7 m is about 6 steps per metre.
        assertEquals(58, stepsScored(steps = 58, ascentM = 9.7))
    }

    @Test
    fun flatWalkScoresZero() {
        assertEquals(0, stepsScored(steps = 50, ascentM = 0.1))
    }

    @Test
    fun shakeScoresZero() {
        assertEquals(0, stepsScored(steps = 40, ascentM = 0.0))
    }

    @Test
    fun elevatorScoresZero() {
        // 15 m in a lift with a few steps in and out: 0.2 steps per metre.
        assertEquals(0, stepsScored(steps = 3, ascentM = 15.0))
    }

    @Test
    fun ascentWithNoStepsScoresZero() {
        assertEquals(0, stepsScored(steps = 0, ascentM = 9.7))
    }

    @Test
    fun descentScoresZero() {
        assertEquals(0, stepsScored(steps = 58, ascentM = -9.7))
    }

    @Test
    fun boundsAreInclusive() {
        assertEquals(8, stepsScored(steps = 8, ascentM = 2.0))
        assertEquals(16, stepsScored(steps = 16, ascentM = 2.0))
        assertEquals(480, stepsScored(steps = 480, ascentM = 120.0))
    }

    @Test
    fun justOutsideTheBoundsScoresZero() {
        assertEquals(0, stepsScored(steps = 7, ascentM = 2.0))
        assertEquals(0, stepsScored(steps = 17, ascentM = 2.0))
        assertEquals(0, stepsScored(steps = 10, ascentM = 1.99))
        assertEquals(0, stepsScored(steps = 500, ascentM = 120.1))
        assertEquals(0, stepsScored(steps = 10, ascentM = Double.NaN))
    }
}
