package com.floorwars.floorsensors

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import com.floorwars.R

class FloorSensorsService :
    Service(),
    SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var wakeLock: PowerManager.WakeLock? = null

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(SensorManager::class.java)
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val newLabel = intent?.getStringExtra(EXTRA_LABEL).orEmpty()
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            buildNotification(newLabel),
            ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
        )

        sensorManager.unregisterListener(this)
        buffer.clear()
        val registered = SENSOR_TYPES.mapNotNull { type ->
            sensorManager.getDefaultSensor(type)?.also {
                sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME)
            }
        }
        Log.i(TAG, "logging label=$newLabel sensors=${registered.map { it.name }}")

        // Keeps the CPU awake with the screen off so non-wakeup sensors keep delivering events.
        if (wakeLock == null) {
            wakeLock = getSystemService(PowerManager::class.java)
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "FloorWars:sensors")
                .apply { acquire() }
        }

        label = newLabel
        statusListener?.invoke()
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        sensorManager.unregisterListener(this)
        wakeLock?.release()
        wakeLock = null
        Log.i(TAG, "stopped label=$label buffered=${buffer.size()} byType=${buffer.countByType()}")
        label = null
        statusListener?.invoke()
        super.onDestroy()
    }

    override fun onSensorChanged(event: SensorEvent) {
        // The framework reuses event.values, so copy it.
        buffer.add(RawSensorEvent(event.sensor.type, event.timestamp, event.values.copyOf()))
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) = Unit

    private fun buildNotification(label: String): Notification {
        val channel = NotificationChannelCompat
            .Builder(CHANNEL_ID, NotificationManagerCompat.IMPORTANCE_LOW)
            .setName(getString(R.string.sensor_channel_name))
            .build()
        NotificationManagerCompat.from(this).createNotificationChannel(channel)

        val openApp = PendingIntent.getActivity(
            this,
            0,
            packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_stat_sensors)
            .setContentTitle(getString(R.string.sensor_notification_title))
            .setContentText(getString(R.string.sensor_notification_text, label))
            .setContentIntent(openApp)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val EXTRA_LABEL = "label"
        private const val TAG = "FloorSensors"
        private const val CHANNEL_ID = "sensor_logging"
        private const val NOTIFICATION_ID = 1
        private val SENSOR_TYPES = listOf(Sensor.TYPE_PRESSURE, Sensor.TYPE_STEP_DETECTOR)

        // Bounded so a forgotten session cannot exhaust memory.
        val buffer = SensorEventBuffer(capacity = 100_000)

        // Non-null while the service is in the foreground and sensors are registered.
        @Volatile
        var label: String? = null
            private set

        @Volatile
        var statusListener: (() -> Unit)? = null
    }
}
