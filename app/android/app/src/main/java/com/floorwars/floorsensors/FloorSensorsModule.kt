package com.floorwars.floorsensors

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorManager
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReadableArray
import com.floorwars.floorsensors.outbox.RoomSegmentOutbox
import java.io.File
import java.io.IOException

class FloorSensorsModule(reactContext: ReactApplicationContext) :
    NativeFloorSensorsSpec(reactContext) {

    private val statusListener = { emitStatus() }

    private val hasBarometer by lazy {
        reactApplicationContext.getSystemService(SensorManager::class.java)
            .getDefaultSensor(Sensor.TYPE_PRESSURE) != null
    }

    init {
        FloorSensorsService.statusListener = statusListener
    }

    override fun startLogging(label: String) {
        Log.i(TAG, "startLogging label=$label")
        // A health foreground service without this permission throws SecurityException on API 34+.
        if (!hasActivityRecognition()) {
            Log.w(TAG, "ACTIVITY_RECOGNITION not granted, not starting the service")
            emitStatus()
            return
        }
        ContextCompat.startForegroundService(
            reactApplicationContext,
            serviceIntent().putExtra(FloorSensorsService.EXTRA_LABEL, label)
        )
    }

    override fun stopLogging() {
        Log.i(TAG, "stopLogging label=${FloorSensorsService.label}")
        // The service reports idle from onDestroy; a service that was not running never does.
        if (!reactApplicationContext.stopService(serviceIntent())) emitStatus()
    }

    override fun getStatus(promise: Promise) {
        val label = FloorSensorsService.label
        val status = Arguments.createMap().apply {
            putBoolean("logging", label != null)
            putString("label", label.orEmpty())
            putBoolean("has_barometer", hasBarometer)
            putInt("buffered", FloorSensorsService.buffer.size())
            // Seam placeholders; w3-engine fills them.
            putBoolean("detecting", false)
            putNull("last_segment_ms")
            putInt("rejected_count", 0)
            putInt("no_checkin_count", 0)
            putDouble("longest_gap_s", 0.0)
            putInt("gaps_over_threshold", 0)
        }
        Log.i(TAG, "getStatus $status")
        promise.resolve(status)
    }

    override fun saveTrace(placement: String, promise: Promise) {
        val session = FloorSensorsService.session
        val stoppedAt = session?.stoppedAtMillis
        if (session == null || stoppedAt == null) {
            promise.reject("E_NO_TRACE", "No stopped logging session to save")
            return
        }
        val metadata = listOf(
            "device_model" to "${Build.MANUFACTURER} ${Build.MODEL}",
            "has_barometer" to hasBarometer.toString(),
            "label" to session.label,
            "placement" to placement,
            "start_utc" to TraceCsv.isoUtc(session.startedAtMillis),
            "stop_utc" to TraceCsv.isoUtc(stoppedAt)
        )
        try {
            val dir = File(reactApplicationContext.filesDir, "traces").apply { mkdirs() }
            val file =
                File(dir, TraceCsv.fileName(session.label, placement, session.startedAtMillis))
            file.bufferedWriter().use { out ->
                TraceCsv.write(
                    out,
                    metadata,
                    FloorSensorsService.buffer.snapshot(),
                    session.startElapsedNanos,
                    ::sensorName
                )
            }
            Log.i(TAG, "saveTrace ${file.absolutePath}")
            promise.resolve(file.absolutePath)
        } catch (e: IOException) {
            promise.reject("E_SAVE_TRACE", e)
        }
    }

    // Seam stubs (W3-0). Each owner replaces its own; the others keep rejecting until then.
    override fun setActiveCheckin(
        checkinId: String,
        buildingId: Double,
        buildingName: String?,
        validUntilMs: Double
    ) = Unit // w3-engine

    override fun clearActiveCheckin() = Unit // w3-engine

    override fun getActiveCheckin(promise: Promise) = notImplemented(promise) // w3-engine

    override fun getPending(limit: Double, promise: Promise) = withOutbox(promise) {
        Arguments.makeNativeArray(it.pending(limit.toInt()))
    }

    override fun markSynced(ids: ReadableArray, promise: Promise) =
        withOutbox(promise) { it.markSynced(ids.strings()) }

    override fun markRejected(ids: ReadableArray, reason: String, promise: Promise) =
        withOutbox(promise) { it.markRejected(ids.strings(), reason) }

    override fun getPendingCount(promise: Promise) = withOutbox(promise) { it.pendingCount() }

    override fun clearPending(promise: Promise) = withOutbox(promise) { it.clearPending() }

    override fun isIgnoringBatteryOptimizations(promise: Promise) =
        notImplemented(promise) // w3-sync

    override fun openBatteryOptimizationSettings() = Unit // w3-sync

    private fun notImplemented(promise: Promise) =
        promise.reject("E_NOT_IMPLEMENTED", "Not implemented yet")

    private fun withOutbox(promise: Promise, call: (RoomSegmentOutbox) -> Any?) {
        try {
            val result = call(RoomSegmentOutbox.get(reactApplicationContext))
            promise.resolve(if (result == Unit) null else result)
        } catch (e: RuntimeException) {
            promise.reject("E_OUTBOX", e)
        }
    }

    // Ids come from JS; anything that is not a string cannot match a row.
    private fun ReadableArray.strings() = toArrayList().filterIsInstance<String>()

    override fun invalidate() {
        if (FloorSensorsService.statusListener === statusListener) {
            FloorSensorsService.statusListener = null
        }
        super.invalidate()
    }

    private fun serviceIntent() = Intent(reactApplicationContext, FloorSensorsService::class.java)

    private fun hasActivityRecognition() = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q ||
        ContextCompat.checkSelfPermission(
            reactApplicationContext,
            Manifest.permission.ACTIVITY_RECOGNITION
        ) == PackageManager.PERMISSION_GRANTED

    private fun sensorName(type: Int) = when (type) {
        Sensor.TYPE_PRESSURE -> "pressure"
        Sensor.TYPE_STEP_DETECTOR -> "step"
        else -> type.toString()
    }

    private fun emitStatus() {
        val label = FloorSensorsService.label
        emitOnStatusChange(
            Arguments.createMap().apply {
                putBoolean("logging", label != null)
                putString("label", label.orEmpty())
            }
        )
    }

    private companion object {
        const val TAG = "FloorSensors"
    }
}
