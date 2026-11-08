package com.floorwars.floorsensors

import android.Manifest
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorManager
import android.net.Uri
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.util.Log
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.ReadableArray
import com.floorwars.floorsensors.detection.ActiveCheckin
import com.floorwars.floorsensors.outbox.RoomSegmentOutbox
import java.io.File
import java.io.IOException

class FloorSensorsModule(reactContext: ReactApplicationContext) :
    NativeFloorSensorsSpec(reactContext) {

    private val statusListener = { emitStatus() }
    private val pendingListener = { emitPending() }

    private val hasBarometer by lazy {
        reactApplicationContext.getSystemService(SensorManager::class.java)
            .getDefaultSensor(Sensor.TYPE_PRESSURE) != null
    }

    init {
        FloorSensorsService.statusListener = statusListener
        FloorSensorsService.pendingListener = pendingListener
        // After an app restart: resume detection for a check-in that is still valid.
        if (!FloorSensorsService.detecting) {
            ActiveCheckinStore.load(reactApplicationContext)?.let { startDetecting() }
        }
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
        // An action rather than stopService, so detection keeps running. The service reports idle.
        if (FloorSensorsService.label == null) {
            emitStatus()
            return
        }
        sendToService(FloorSensorsService.ACTION_STOP_LOGGING)
    }

    override fun getStatus(promise: Promise) {
        val label = FloorSensorsService.label
        val status = Arguments.createMap().apply {
            putBoolean("logging", label != null)
            putString("label", label.orEmpty())
            putBoolean("has_barometer", hasBarometer)
            putInt("buffered", FloorSensorsService.buffer.size())
            val detector = FloorSensorsService.lastDetector
            putBoolean("detecting", FloorSensorsService.detecting)
            val lastSegmentMs = detector?.lastSegmentMs
            if (lastSegmentMs == null) {
                putNull("last_segment_ms")
            } else {
                putDouble("last_segment_ms", lastSegmentMs.toDouble())
            }
            putInt("rejected_count", detector?.rejectedCount ?: 0)
            putInt("no_checkin_count", detector?.noCheckinCount ?: 0)
            // Gap metric (W3-7), local only.
            val gaps = FloorSensorsService.lastGaps
            putDouble("longest_gap_s", gaps?.longestGapS ?: 0.0)
            putInt("gaps_over_threshold", gaps?.gapsOverThreshold ?: 0)
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

    // Replaces any earlier check-in, as the server does, and starts or moves detection.
    override fun setActiveCheckin(
        checkinId: String,
        buildingId: Double,
        buildingName: String?,
        validUntilMs: Double
    ) {
        // From JS: a fractional or out-of-range number must not become a building id or expiry.
        val okBuilding = buildingId % 1.0 == 0.0 && buildingId in 1.0..Int.MAX_VALUE.toDouble()
        val okUntil = validUntilMs % 1.0 == 0.0 && validUntilMs in 0.0..Long.MAX_VALUE.toDouble()
        val checkin = ActiveCheckin(
            id = checkinId,
            buildingId = if (okBuilding) buildingId.toInt() else 0,
            buildingName = buildingName,
            validUntilMs = if (okUntil) validUntilMs.toLong() else 0
        )
        if (!checkin.isValidAt(System.currentTimeMillis())) {
            Log.w(TAG, "setActiveCheckin: invalid or expired, ignored")
            return
        }
        ActiveCheckinStore.save(reactApplicationContext, checkin)
        startDetecting()
    }

    override fun clearActiveCheckin() {
        ActiveCheckinStore.clear(reactApplicationContext)
        // Only sign-out clears the check-in: the open climb belongs to the user who is leaving, so
        // it is dropped, not flushed into the outbox after clearPending() has run.
        if (FloorSensorsService.detecting) {
            sendToService(FloorSensorsService.ACTION_STOP_DETECT, discard = true)
        }
    }

    override fun getActiveCheckin(promise: Promise) {
        val c = ActiveCheckinStore.load(reactApplicationContext)
        promise.resolve(
            c?.let {
                Arguments.createMap().apply {
                    putString("checkin_id", it.id)
                    putInt("building_id", it.buildingId)
                    putString("building_name", it.buildingName)
                    putDouble("valid_until_ms", it.validUntilMs.toDouble())
                }
            }
        )
    }

    // The service reads the check-in from ActiveCheckinStore.
    private fun startDetecting() {
        // A health foreground service without this permission throws SecurityException on API 34+.
        if (!hasActivityRecognition()) {
            Log.w(TAG, "ACTIVITY_RECOGNITION not granted, not detecting")
            return
        }
        try {
            ContextCompat.startForegroundService(
                reactApplicationContext,
                serviceIntent().setAction(FloorSensorsService.ACTION_DETECT)
            )
        } catch (e: IllegalStateException) {
            // The WorkManager sync job loads this module in a background process, where Android 12
            // and later refuse a foreground service start (ForegroundServiceStartNotAllowedException).
            // Detection resumes the next time the app opens in the foreground.
            Log.w(TAG, "detect: foreground start refused in the background", e)
        }
    }

    // startService, not startForegroundService: these paths may not call startForeground.
    private fun sendToService(action: String, discard: Boolean = false) {
        try {
            val intent = serviceIntent()
                .setAction(action)
                .putExtra(FloorSensorsService.EXTRA_DISCARD, discard)
            reactApplicationContext.startService(intent)
        } catch (e: IllegalStateException) {
            // Background start refused; only possible if the service already stopped.
            Log.w(TAG, "could not send $action", e)
        }
    }

    override fun getPending(limit: Double, promise: Promise) = withOutbox(promise) {
        Arguments.makeNativeArray(it.pending(limit.toInt()))
    }

    // The three writes below change the pending count, so each emits onPendingChanged.
    override fun markSynced(ids: ReadableArray, promise: Promise) = withOutbox(promise) {
        it.markSynced(ids.strings())
        emitPending()
    }

    override fun markRejected(ids: ReadableArray, reason: String, promise: Promise) =
        withOutbox(promise) {
            it.markRejected(ids.strings(), reason)
            emitPending()
        }

    override fun getPendingCount(promise: Promise) = withOutbox(promise) { it.pendingCount() }

    override fun clearPending(promise: Promise) = withOutbox(promise) {
        it.clearPending()
        emitPending()
    }

    override fun isIgnoringBatteryOptimizations(promise: Promise) {
        val power = reactApplicationContext.getSystemService(PowerManager::class.java)
        promise.resolve(power.isIgnoringBatteryOptimizations(reactApplicationContext.packageName))
    }

    // The list of apps, which needs no extra permission (the direct exemption dialog does).
    override fun openBatteryOptimizationSettings() {
        val intent = Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        try {
            reactApplicationContext.startActivity(intent)
        } catch (e: ActivityNotFoundException) {
            reactApplicationContext.startActivity(
                Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS)
                    .setData(Uri.fromParts("package", reactApplicationContext.packageName, null))
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }

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
        if (FloorSensorsService.pendingListener === pendingListener) {
            FloorSensorsService.pendingListener = null
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

    private fun emitPending() {
        try {
            val pending = RoomSegmentOutbox.get(reactApplicationContext).pendingCount()
            emitOnPendingChanged(Arguments.createMap().apply { putInt("pending", pending) })
        } catch (e: RuntimeException) {
            Log.w(TAG, "pending count failed", e)
        }
    }

    private companion object {
        const val TAG = "FloorSensors"
    }
}
