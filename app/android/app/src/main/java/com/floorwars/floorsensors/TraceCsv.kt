package com.floorwars.floorsensors

import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

data class TraceSession(
    val label: String,
    val startedAtMillis: Long,
    val startElapsedNanos: Long,
    val stoppedAtMillis: Long? = null
)

// A trace read back from CSV: the "# key,value" header and the events split by sensor.
class Trace(
    val metadata: Map<String, String>,
    val pressure: List<RawSensorEvent>,
    val steps: List<RawSensorEvent>
)

// Metadata as "# key,value" lines, then one row per event. elapsed_s is relative to session start.
object TraceCsv {
    const val COLUMNS = "sensor,timestamp_ns,elapsed_s,value"

    fun write(
        out: Appendable,
        metadata: List<Pair<String, String>>,
        events: List<RawSensorEvent>,
        startElapsedNanos: Long,
        sensorName: (Int) -> String
    ) {
        for ((key, value) in metadata) out.append("# $key,${escape(value)}\n")
        out.append(COLUMNS).append('\n')
        for (event in events) {
            val elapsed = (event.timestampNanos - startElapsedNanos) / 1e9
            out.append(sensorName(event.sensorType)).append(',')
                .append(event.timestampNanos.toString()).append(',')
                .append(String.format(Locale.US, "%.3f", elapsed)).append(',')
                .append(event.values.first().toString()).append('\n')
        }
    }

    // Sensor.TYPE_PRESSURE and Sensor.TYPE_STEP_DETECTOR, without an Android import, so JUnit can read.
    private const val TYPE_PRESSURE = 6
    private val SENSOR_TYPES = mapOf("pressure" to TYPE_PRESSURE, "step" to 18)

    fun read(lines: List<String>): Trace {
        val metadata = linkedMapOf<String, String>()
        val pressure = mutableListOf<RawSensorEvent>()
        val steps = mutableListOf<RawSensorEvent>()
        var columnsSeen = false
        for ((index, line) in lines.withIndex()) {
            when {
                line.isEmpty() -> continue
                line.startsWith("# ") && !columnsSeen -> {
                    val parts = line.removePrefix("# ").split(",", limit = 2)
                    require(parts.size == 2) {
                        "line ${index + 1}: metadata without a value: $line"
                    }
                    metadata[parts[0]] = unescape(parts[1])
                }
                !columnsSeen -> {
                    require(line == COLUMNS) {
                        "line ${index + 1}: expected \"$COLUMNS\", got: $line"
                    }
                    columnsSeen = true
                }
                else -> {
                    val fields = line.split(",")
                    require(fields.size == 4) { "line ${index + 1}: expected 4 fields: $line" }
                    val (sensor, nanos, _, value) = fields
                    val type = requireNotNull(SENSOR_TYPES[sensor]) {
                        "line ${index + 1}: unknown sensor: $sensor"
                    }
                    val event = RawSensorEvent(type, nanos.toLong(), floatArrayOf(value.toFloat()))
                    if (type == TYPE_PRESSURE) pressure.add(event) else steps.add(event)
                }
            }
        }
        require(columnsSeen) { "no \"$COLUMNS\" line" }
        return Trace(metadata, pressure, steps)
    }

    fun isoUtc(millis: Long): String = utc("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").format(Date(millis))

    // No colons, so the file name survives a copy to Windows.
    fun fileStamp(millis: Long): String = utc("yyyyMMdd'T'HHmmss'Z'").format(Date(millis))

    fun fileName(label: String, placement: String, startedAtMillis: Long): String =
        listOf(label, placement, fileStamp(startedAtMillis))
            .joinToString("_") { it.replace(Regex("[^A-Za-z0-9_-]"), "-") } + ".csv"

    private fun utc(pattern: String) =
        SimpleDateFormat(pattern, Locale.US).apply { timeZone = TimeZone.getTimeZone("UTC") }

    private fun escape(value: String) = if (value.any { it == ',' || it == '"' || it == '\n' }) {
        "\"" + value.replace("\"", "\"\"") + "\""
    } else {
        value
    }

    private fun unescape(value: String): String {
        if (value.length < 2 || !value.startsWith('"') || !value.endsWith('"')) return value
        return value.substring(1, value.length - 1).replace("\"\"", "\"")
    }
}
