package com.floorwars.floorsensors

class RawSensorEvent(val sensorType: Int, val timestampNanos: Long, val values: FloatArray)

// In-memory only until Room persistence (Week 3). Drops the oldest event when full.
class SensorEventBuffer(private val capacity: Int) {
    private val events = ArrayDeque<RawSensorEvent>()

    @Synchronized
    fun add(event: RawSensorEvent) {
        if (events.size == capacity) events.removeFirst()
        events.addLast(event)
    }

    @Synchronized
    fun clear() = events.clear()

    @Synchronized
    fun size() = events.size

    @Synchronized
    fun countByType(): Map<Int, Int> = events.groupingBy { it.sensorType }.eachCount()

    @Synchronized
    fun snapshot(): List<RawSensorEvent> = events.toList()
}
