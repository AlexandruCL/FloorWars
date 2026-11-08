package com.floorwars.floorsensors.outbox

import androidx.room.Room
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

// Robolectric: Room needs an Android Context and the framework SQLite, which plain JUnit lacks.
// SDK 34 because SDK 35 and later need JDK 21, and CI runs JDK 17.
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class RoomSegmentOutboxTest {
    private val context = RuntimeEnvironment.getApplication()
    private var clock = 1_000_000L
    private val db = Room.inMemoryDatabaseBuilder(context, OutboxDatabase::class.java)
        .allowMainThreadQueries()
        .build()
    private val outbox = RoomSegmentOutbox(db) { clock }

    @After
    fun close() = db.close()

    private fun segment(id: String) = OutboxSegment(
        id = id,
        checkinId = "c0a80101-0000-4000-8000-000000000001",
        buildingId = 7,
        startMs = 1_798_000_000_000L,
        endMs = 1_798_000_022_000L,
        ascentM = 9.6,
        durationS = 22.0,
        vertSpeedMps = 0.44,
        steps = 52,
        stepsPerM = 5.4,
        pressureStepsMatch = true,
        stairProb = 0.91,
        classifierVersion = "rules-1",
        hasBarometer = true
    )

    private fun insertAt(createdAt: Long, vararg ids: String) {
        clock = createdAt
        ids.forEach { outbox.insert(segment(it)) }
    }

    private fun ids(rows: List<Map<String, Any>>) = rows.map { it["id"] }

    private fun row(id: String): String? =
        db.query("SELECT status, reject_reason FROM segment_outbox WHERE id = ?", arrayOf(id))
            .use { if (it.moveToFirst()) "${it.getString(0)}:${it.getString(1)}" else null }

    @Test
    fun insertStoresAPendingRowWithExactlyTheContractFields() {
        outbox.insert(segment("a"))

        val rows = outbox.pending(10)
        assertEquals(1, outbox.pendingCount())
        assertEquals(
            mapOf(
                "id" to "a",
                "checkin_id" to "c0a80101-0000-4000-8000-000000000001",
                "started_at" to "2026-12-23T04:26:40.000Z",
                "building_id" to 7,
                "ascent_m" to 9.6,
                "duration_s" to 22.0,
                "vert_speed_mps" to 0.44,
                "steps" to 52,
                "stair_prob" to 0.91,
                "classifier_version" to "rules-1"
            ),
            rows.single()
        )
    }

    @Test
    fun repeatedIdIsANoOp() {
        outbox.insert(segment("a"))
        outbox.insert(segment("a"))
        assertEquals(1, outbox.pendingCount())
    }

    @Test
    fun getPendingIsOldestFirstAndHonoursTheLimit() {
        insertAt(3_000, "c")
        insertAt(1_000, "a")
        insertAt(2_000, "b1", "b2")

        assertEquals(listOf("a", "b1", "b2"), ids(outbox.pending(3)))
        assertEquals(listOf("a"), ids(outbox.pending(1)))
        assertEquals(emptyList<Any>(), ids(outbox.pending(0)))
        assertEquals(emptyList<Any>(), ids(outbox.pending(-5)))
    }

    @Test
    fun markSyncedTwiceIsANoOpAndSyncedRowsLeavePending() {
        insertAt(1_000, "a", "b")
        outbox.markSynced(listOf("a"))
        outbox.markSynced(listOf("a", "unknown"))

        assertEquals(listOf("b"), ids(outbox.pending(10)))
        assertEquals(2, db.dao().count())
    }

    @Test
    fun markRejectedDoesNotOverrideASyncedRow() {
        insertAt(1_000, "a", "b")
        outbox.markSynced(listOf("a"))
        outbox.markRejected(listOf("a", "b"), "building_mismatch")
        outbox.markRejected(listOf("b"), "other")

        assertEquals("synced:null", row("a"))
        assertEquals("rejected:building_mismatch", row("b"))
    }

    @Test
    fun clearPendingDeletesOnlyPendingRows() {
        insertAt(1_000, "a", "b", "c")
        outbox.markSynced(listOf("a"))
        outbox.markRejected(listOf("b"), "too_fast")
        outbox.clearPending()

        assertEquals(0, outbox.pendingCount())
        assertEquals(2, db.dao().count())
    }

    @Test
    fun retentionDropsOldSyncedAndRejectedButNeverPending() {
        val day = 24L * 60 * 60 * 1000
        insertAt(0, "pending0", "synced0", "rejected0")
        insertAt(10 * day, "synced10", "rejected10")
        insertAt(25 * day, "synced25")
        outbox.markSynced(listOf("synced0", "synced10", "synced25"))
        outbox.markRejected(listOf("rejected0", "rejected10"), "too_fast")
        clock = 31 * day

        outbox.pruneOld()

        // At day 31: synced rows older than 7 days and rejected rows older than 30 days go.
        assertEquals(
            listOf("pending:null", null, null, null, "rejected:too_fast", "synced:null"),
            listOf("pending0", "synced0", "rejected0", "synced10", "rejected10", "synced25")
                .map(::row)
        )
    }

    @Test
    fun capDropsOldestRejectedThenOldestSyncedThenRefuses() {
        val max = RoomSegmentOutbox.MAX_ROWS
        insertAt(1, "rejected1")
        insertAt(2, "rejected2")
        insertAt(3, "synced1")
        outbox.markRejected(listOf("rejected1", "rejected2"), "too_fast")
        outbox.markSynced(listOf("synced1"))
        db.runInTransaction {
            for (i in 3 until max) insertAt(10L + i, "p$i")
        }
        assertEquals(max, db.dao().count())

        insertAt(100_000, "new1")
        assertEquals(null, row("rejected1"))
        assertEquals("rejected:too_fast", row("rejected2"))
        insertAt(100_001, "new2")
        assertEquals(null, row("rejected2"))
        assertEquals("synced:null", row("synced1"))
        insertAt(100_002, "new3")
        assertEquals(null, row("synced1"))
        assertEquals(max, db.dao().count())
        assertEquals(max, outbox.pendingCount())
        assertEquals(0, outbox.refusedFull.get())

        insertAt(100_003, "refused")
        assertEquals(max, db.dao().count())
        assertEquals(1, outbox.refusedFull.get())
        assertEquals("p3", outbox.pending(1).single()["id"])
        assertEquals(
            listOf("new1", "new2", "new3"),
            ids(outbox.pending(max)).takeLast(3)
        )
    }

    @Test
    fun aPendingRowSurvivesARestart() {
        val name = "restart-test.db"
        context.deleteDatabase(name)
        val first = OutboxDatabase.open(context, name)
        RoomSegmentOutbox(first).insert(segment("a"))
        first.close()

        val second = OutboxDatabase.open(context, name)
        try {
            assertEquals(listOf("a"), ids(RoomSegmentOutbox(second).pending(10)))
        } finally {
            second.close()
            context.deleteDatabase(name)
        }
    }
}
