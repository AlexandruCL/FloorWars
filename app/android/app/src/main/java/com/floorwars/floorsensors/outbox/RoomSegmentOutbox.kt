package com.floorwars.floorsensors.outbox

import android.content.Context
import android.util.Log
import com.floorwars.floorsensors.TraceCsv
import java.util.concurrent.atomic.AtomicInteger

class RoomSegmentOutbox(
    private val db: OutboxDatabase,
    private val now: () -> Long = System::currentTimeMillis
) : SegmentOutbox {

    private val dao = db.dao()

    // Debug counter: segments refused because the table was full of pending rows.
    val refusedFull = AtomicInteger()

    override fun insert(segment: OutboxSegment) {
        val stored = db.runInTransaction<Boolean> {
            var excess = dao.count() - MAX_ROWS + 1
            if (excess > 0) excess -= dao.deleteOldest(REJECTED, excess)
            if (excess > 0) excess -= dao.deleteOldest(SYNCED, excess)
            // Pending rows are never dropped; refusing the new one keeps the older climbs.
            if (excess <= 0) dao.insert(segment.toRow(now()))
            excess <= 0
        }
        if (!stored) {
            Log.w(TAG, "outbox full of pending rows, refused=${refusedFull.incrementAndGet()}")
        }
    }

    fun pending(limit: Int): List<Map<String, Any>> =
        dao.pending(limit.coerceIn(0, MAX_ROWS)).map { it.toSegmentFields() }

    fun pendingCount(): Int = dao.pendingCount()

    fun markSynced(ids: List<String>) = db.runInTransaction {
        ids.chunked(MAX_SQL_ARGS).forEach { dao.markSynced(it) }
    }

    fun markRejected(ids: List<String>, reason: String) = db.runInTransaction {
        ids.chunked(MAX_SQL_ARGS).forEach { dao.markRejected(it, reason) }
    }

    fun clearPending() {
        dao.clearPending()
    }

    // Age counts from created_at; there is no status-change time in the table.
    fun pruneOld() = db.runInTransaction {
        val t = now()
        dao.deleteOlderThan(SYNCED, t - SYNCED_KEEP_MS)
        dao.deleteOlderThan(REJECTED, t - REJECTED_KEEP_MS)
    }

    private fun OutboxSegment.toRow(createdAt: Long) = OutboxRow(
        id = id,
        startMs = startMs,
        endMs = endMs,
        ascentM = ascentM,
        durationS = durationS,
        vertSpeedMps = vertSpeedMps,
        steps = steps,
        stairProb = stairProb,
        classifierVersion = classifierVersion,
        stepsPerM = stepsPerM,
        pressureStepsMatch = pressureStepsMatch,
        hasBarometer = hasBarometer,
        checkinId = checkinId,
        buildingId = buildingId,
        status = PENDING,
        rejectReason = null,
        createdAt = createdAt,
        attempts = 0
    )

    companion object {
        const val MAX_ROWS = 5000
        const val PENDING = "pending"
        const val SYNCED = "synced"
        const val REJECTED = "rejected"
        const val SYNCED_KEEP_MS = 7L * 24 * 60 * 60 * 1000
        const val REJECTED_KEEP_MS = 30L * 24 * 60 * 60 * 1000

        // Below SQLite's 999 bound-argument limit on older Android versions.
        private const val MAX_SQL_ARGS = 500
        private const val TAG = "FloorSensors"

        @Volatile
        private var instance: RoomSegmentOutbox? = null

        // One database per process, shared by the service, the module and the engine.
        fun get(context: Context): RoomSegmentOutbox = instance ?: synchronized(this) {
            instance ?: RoomSegmentOutbox(OutboxDatabase.open(context.applicationContext))
                .also { instance = it }
        }
    }
}

// The contract's Segment allows no other keys (unevaluatedProperties: false).
fun PendingRow.toSegmentFields(): Map<String, Any> = linkedMapOf(
    "id" to id,
    "checkin_id" to checkinId,
    "started_at" to TraceCsv.isoUtc(startMs),
    "building_id" to buildingId,
    "ascent_m" to ascentM,
    "duration_s" to durationS,
    "vert_speed_mps" to vertSpeedMps,
    "steps" to steps,
    "stair_prob" to stairProb,
    "classifier_version" to classifierVersion
)
