package com.floorwars.floorsensors.outbox

data class OutboxSegment(
    val id: String,
    val checkinId: String,
    val buildingId: Int,
    val startMs: Long,
    val endMs: Long,
    val ascentM: Double,
    val durationS: Double,
    val vertSpeedMps: Double,
    val steps: Int,
    val stepsPerM: Double,
    val pressureStepsMatch: Boolean,
    val stairProb: Double,
    val classifierVersion: String,
    val hasBarometer: Boolean
)

interface SegmentOutbox {
    fun insert(segment: OutboxSegment)
}
