package com.floorwars.floorsensors

import org.junit.Assert.assertEquals
import org.junit.Test

class SensorEventBufferTest {
    private fun event(type: Int, t: Long) = RawSensorEvent(type, t, floatArrayOf(t.toFloat()))

    @Test
    fun dropsOldestWhenFull() {
        val buffer = SensorEventBuffer(capacity = 3)
        (1L..5L).forEach { buffer.add(event(6, it)) }
        assertEquals(3, buffer.size())
        assertEquals(listOf(3L, 4L, 5L), buffer.snapshot().map { it.timestampNanos })
    }

    @Test
    fun countsBySensorTypeAndClears() {
        val buffer = SensorEventBuffer(capacity = 10)
        buffer.add(event(6, 1))
        buffer.add(event(18, 2))
        buffer.add(event(6, 3))
        assertEquals(mapOf(6 to 2, 18 to 1), buffer.countByType())
        buffer.clear()
        assertEquals(0, buffer.size())
    }
}
