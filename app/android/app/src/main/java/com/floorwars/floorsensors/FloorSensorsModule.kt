package com.floorwars.floorsensors

import android.util.Log
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.ReactApplicationContext

class FloorSensorsModule(reactContext: ReactApplicationContext) :
    NativeFloorSensorsSpec(reactContext) {

    // Null while not logging. Sensor registration arrives with the foreground service (T3).
    private var label: String? = null

    override fun startLogging(label: String) {
        this.label = label
        Log.i(TAG, "startLogging label=$label")
        emitStatus()
    }

    override fun stopLogging() {
        Log.i(TAG, "stopLogging label=$label")
        label = null
        emitStatus()
    }

    private fun emitStatus() {
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
