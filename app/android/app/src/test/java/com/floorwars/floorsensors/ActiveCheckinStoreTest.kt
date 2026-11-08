package com.floorwars.floorsensors

import com.floorwars.floorsensors.detection.ActiveCheckin
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

// Robolectric for SharedPreferences. SDK 34 because CI runs JDK 17 (see RoomSegmentOutboxTest).
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ActiveCheckinStoreTest {
    private val context = RuntimeEnvironment.getApplication()
    private val checkin = ActiveCheckin("c1", 7, "Facultatea de Automatica", 2_000_000L)

    @After
    fun clear() = ActiveCheckinStore.clear(context)

    @Test
    fun savedCheckinIsLoadedWithAllFields() {
        ActiveCheckinStore.save(context, checkin)
        assertEquals(checkin, ActiveCheckinStore.load(context, nowMs = 1_000_000L))
    }

    @Test
    fun noneStoredLoadsNull() {
        assertNull(ActiveCheckinStore.load(context, nowMs = 1_000_000L))
    }

    @Test
    fun expiredCheckinLoadsNullAndIsRemoved() {
        ActiveCheckinStore.save(context, checkin)
        assertNull(ActiveCheckinStore.load(context, nowMs = 2_000_000L))
        // Gone for good, even for an earlier clock reading.
        assertNull(ActiveCheckinStore.load(context, nowMs = 1_000_000L))
    }

    @Test
    fun clearRemovesTheCheckin() {
        ActiveCheckinStore.save(context, checkin)
        ActiveCheckinStore.clear(context)
        assertNull(ActiveCheckinStore.load(context, nowMs = 1_000_000L))
    }

    @Test
    fun aNewCheckinReplacesTheOldOne() {
        ActiveCheckinStore.save(context, checkin)
        val next = ActiveCheckin("c2", 8, null, 3_000_000L)
        ActiveCheckinStore.save(context, next)
        assertEquals(next, ActiveCheckinStore.load(context, nowMs = 1_000_000L))
    }
}
