package com.floorwars.floorsensors.classifier

// Thresholds from IMPLEMENTATION_PLAN.md 3.3 and 5.2. Tunable after real recordings.
object ScoringThresholds {
    const val MIN_STEPS_PER_METRE = 4.0
    const val MAX_STEPS_PER_METRE = 10.0
    const val MIN_ASCENT_M = 2.0
    const val MAX_ASCENT_M = 120.0
}

// Anti-cheat core: a segment scores its steps only when steps and pressure change agree.
// Steps without ascent (shake, flat walk) and ascent without steps (elevator) score zero.
fun stepsScored(steps: Int, ascentM: Double): Int = with(ScoringThresholds) {
    if (steps <= 0 || ascentM.isNaN() || ascentM !in MIN_ASCENT_M..MAX_ASCENT_M) return 0
    val stepsPerMetre = steps / ascentM
    if (stepsPerMetre in MIN_STEPS_PER_METRE..MAX_STEPS_PER_METRE) steps else 0
}
