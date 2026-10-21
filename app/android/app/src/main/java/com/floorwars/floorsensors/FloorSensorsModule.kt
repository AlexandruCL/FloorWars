package com.floorwars.floorsensors

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.util.Log
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReactApplicationContext

class FloorSensorsModule(reactContext: ReactApplicationContext) :
    NativeFloorSensorsSpec(reactContext) {

    private val statusListener = { emitStatus() }

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
