package com.floorwars.floorsensors

import org.junit.Assert.assertEquals
import org.junit.Test

class TraceCsvTest {
    @Test
    fun writesMetadataColumnsAndRows() {
        val out = StringBuilder()
        TraceCsv.write(
            out,
            metadata = listOf("label" to "stairs_up", "device_model" to "Acme X1, Pro"),
            events = listOf(
                RawSensorEvent(6, 1_500_000_000, floatArrayOf(1013.25f)),
                RawSensorEvent(18, 2_000_000_000, floatArrayOf(1f))
            ),
            startElapsedNanos = 1_000_000_000,
            sensorName = { if (it == 6) "pressure" else "step" }
        )
        assertEquals(
            """
            # label,stairs_up
            # device_model,"Acme X1, Pro"
            sensor,timestamp_ns,elapsed_s,value
            pressure,1500000000,0.500,1013.25
            step,2000000000,1.000,1.0

            """.trimIndent(),
            out.toString()
        )
    }

    @Test
    fun formatsUtcTimestampsAndSafeFileNames() {
        assertEquals("2026-10-21T17:05:09.123Z", TraceCsv.isoUtc(1_792_602_309_123))
        assertEquals(
            "stairs_up_pocket_20261021T170509Z.csv",
            TraceCsv.fileName("stairs_up", "pocket", 1_792_602_309_123)
        )
        assertEquals("a-b_hand_19700101T000000Z.csv", TraceCsv.fileName("a/b", "hand", 0))
    }
}
