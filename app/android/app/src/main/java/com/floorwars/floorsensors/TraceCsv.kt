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
}
