package com.floorwars.floorsensors.outbox

import android.content.Context
import androidx.room.ColumnInfo
import androidx.room.Dao
import androidx.room.Database
import androidx.room.Entity
import androidx.room.Index
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.PrimaryKey
import androidx.room.Query
import androidx.room.Room
import androidx.room.RoomDatabase

// Contract Segment fields plus local-only checks; no location, no raw sensor data (plan 8).
@Entity(tableName = "segment_outbox", indices = [Index("status", "created_at")])
data class OutboxRow(
    @PrimaryKey val id: String,
    @ColumnInfo(name = "start_ms") val startMs: Long,
    @ColumnInfo(name = "end_ms") val endMs: Long,
    @ColumnInfo(name = "ascent_m") val ascentM: Double,
    @ColumnInfo(name = "duration_s") val durationS: Double,
    @ColumnInfo(name = "vert_speed_mps") val vertSpeedMps: Double,
    val steps: Int,
    @ColumnInfo(name = "stair_prob") val stairProb: Double,
    @ColumnInfo(name = "classifier_version") val classifierVersion: String,
    @ColumnInfo(name = "steps_per_m") val stepsPerM: Double,
    @ColumnInfo(name = "pressure_steps_match") val pressureStepsMatch: Boolean,
    @ColumnInfo(name = "has_barometer") val hasBarometer: Boolean,
    @ColumnInfo(name = "checkin_id") val checkinId: String,
    @ColumnInfo(name = "building_id") val buildingId: Int,
    val status: String,
    @ColumnInfo(name = "reject_reason") val rejectReason: String?,
    @ColumnInfo(name = "created_at") val createdAt: Long,
    val attempts: Int
)

// The upload projection: exactly the columns behind the contract's Segment.
data class PendingRow(
    val id: String,
    @ColumnInfo(name = "checkin_id") val checkinId: String,
    @ColumnInfo(name = "start_ms") val startMs: Long,
    @ColumnInfo(name = "building_id") val buildingId: Int,
    @ColumnInfo(name = "ascent_m") val ascentM: Double,
    @ColumnInfo(name = "duration_s") val durationS: Double,
    @ColumnInfo(name = "vert_speed_mps") val vertSpeedMps: Double,
    val steps: Int,
    @ColumnInfo(name = "stair_prob") val stairProb: Double,
    @ColumnInfo(name = "classifier_version") val classifierVersion: String
)

@Dao
interface OutboxDao {
    // A repeated id is a no-op: the server treats a re-sent id as the same segment.
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    fun insert(row: OutboxRow): Long

    @Query("SELECT COUNT(*) FROM segment_outbox")
    fun count(): Int

    @Query("SELECT COUNT(*) FROM segment_outbox WHERE status = 'pending'")
    fun pendingCount(): Int

    @Query(
        "SELECT id, checkin_id, start_ms, building_id, ascent_m, duration_s, vert_speed_mps, " +
            "steps, stair_prob, classifier_version FROM segment_outbox " +
            "WHERE status = 'pending' ORDER BY created_at, rowid LIMIT :limit"
    )
    fun pending(limit: Int): List<PendingRow>

    // Only pending rows move, so a repeat or a synced-then-rejected id changes nothing.
    @Query("UPDATE segment_outbox SET status = 'synced' WHERE status = 'pending' AND id IN (:ids)")
    fun markSynced(ids: List<String>): Int

    @Query(
        "UPDATE segment_outbox SET status = 'rejected', reject_reason = :reason " +
            "WHERE status = 'pending' AND id IN (:ids)"
    )
    fun markRejected(ids: List<String>, reason: String): Int

    @Query("DELETE FROM segment_outbox WHERE status = 'pending'")
    fun clearPending(): Int

    @Query("DELETE FROM segment_outbox WHERE status = :status AND created_at < :before")
    fun deleteOlderThan(status: String, before: Long): Int

    @Query(
        "DELETE FROM segment_outbox WHERE id IN (SELECT id FROM segment_outbox " +
            "WHERE status = :status ORDER BY created_at, rowid LIMIT :n)"
    )
    fun deleteOldest(status: String, n: Int): Int
}

@Database(entities = [OutboxRow::class], version = 1)
abstract class OutboxDatabase : RoomDatabase() {
    abstract fun dao(): OutboxDao

    companion object {
        const val NAME = "segment_outbox.db"

        // Inserts are single-row transactions, and SegmentOutbox.insert is synchronous so the
        // row is on disk when it returns; the engine may call it from a sensor callback.
        fun open(context: Context, name: String = NAME): OutboxDatabase = Room
            .databaseBuilder(context, OutboxDatabase::class.java, name)
            .allowMainThreadQueries()
            .build()
    }
}
