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
import android.os.Handler
import android.os.HandlerThread
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import androidx.core.app.NotificationChannelCompat
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.app.ServiceCompat
import com.floorwars.R
import com.floorwars.floorsensors.detection.ActiveCheckin
import com.floorwars.floorsensors.detection.SegmentDetector
import com.floorwars.floorsensors.outbox.OutboxSegment
import com.floorwars.floorsensors.outbox.RoomSegmentOutbox
import com.floorwars.floorsensors.outbox.SegmentOutbox

// Two modes, which can overlap: logging records a trace for the logger screen; detecting runs the
// live segmenter during an active check-in and writes STAIRS segments to the outbox, no trace.
class FloorSensorsService :
    Service(),
    SensorEventListener {

    private lateinit var sensorManager: SensorManager
    private var wakeLock: PowerManager.WakeLock? = null

    // Sensor callbacks, segmenting and outbox writes run here: Room refuses the main thread, and a
    // pass over the 4-minute window should not hold up the UI.
    private val sensorThread = HandlerThread("FloorSensors").apply { start() }
    private val sensorHandler = Handler(sensorThread.looper)
    private val mainHandler = Handler(Looper.getMainLooper())
    private val expire = Runnable { stopDetecting() }

    // Main thread only.
    private var checkin: ActiveCheckin? = null

    // Sensor thread only.
    private var detector: SegmentDetector? = null

    override fun onCreate() {
        super.onCreate()
        sensorManager = getSystemService(SensorManager::class.java)
        // Off the main thread: a retention sweep can touch thousands of rows.
        Thread {
            try {
                RoomSegmentOutbox.get(this).pruneOld()
            } catch (e: RuntimeException) {
                Log.w(TAG, "outbox retention failed", e)
            }
        }.start()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_DETECT -> startDetecting(
                ActiveCheckin(
                    id = intent.getStringExtra(EXTRA_CHECKIN_ID).orEmpty(),
                    buildingId = intent.getIntExtra(EXTRA_BUILDING_ID, 0),
                    buildingName = intent.getStringExtra(EXTRA_BUILDING_NAME),
                    validUntilMs = intent.getLongExtra(EXTRA_VALID_UNTIL_MS, 0)
                )
            )
            ACTION_STOP_DETECT -> stopDetecting()
            else -> startLogging(intent?.getStringExtra(EXTRA_LABEL).orEmpty())
        }
        return START_NOT_STICKY
    }

    private fun startLogging(newLabel: String) {
        label = newLabel
        startForeground()
        buffer.clear()
        session =
            TraceSession(newLabel, System.currentTimeMillis(), SystemClock.elapsedRealtimeNanos())
        updateSensorsAndWakeLock()
        Log.i(TAG, "logging label=$newLabel")
        statusListener?.invoke()
    }

    private fun startDetecting(newCheckin: ActiveCheckin) {
        startForeground()
        val remainingMs = newCheckin.validUntilMs - System.currentTimeMillis()
        if (newCheckin.id.isEmpty() || newCheckin.buildingId < 1 || remainingMs <= 0) {
            Log.w(TAG, "detect: no valid check-in, not detecting")
            stopDetecting()
            return
        }
        checkin = newCheckin
        // One offset per session, so a wall-clock change cannot corrupt durations.
        val offsetMs = System.currentTimeMillis() - SystemClock.elapsedRealtimeNanos() / 1_000_000
        val hasBarometer = sensorManager.getDefaultSensor(Sensor.TYPE_PRESSURE) != null
        sensorHandler.post {
            // shortcut: a new check-in flushes the previous detector, so a climb across the swap
            // splits in two; W3-3 keeps one detector and looks up the check-in by climb start.
            detector?.stop()
            detector = SegmentDetector(outboxOrDrop, offsetMs, hasBarometer, { startMs ->
                newCheckin.takeIf { startMs <= it.validUntilMs }
            })
        }
        mainHandler.removeCallbacks(expire)
        mainHandler.postDelayed(expire, remainingMs)
        updateSensorsAndWakeLock()
        Log.i(TAG, "detecting building=${newCheckin.buildingId} for ${remainingMs / 1000} s")
    }

    private fun stopDetecting() {
        mainHandler.removeCallbacks(expire)
        checkin = null
        // Flushes an open climb into the outbox before the detector goes.
        sensorHandler.post {
            detector?.stop()
            detector = null
        }
        updateSensorsAndWakeLock()
        if (label == null) stopSelf()
    }

    // Called on every mode change: sensors and the wake lock run while either mode is on.
    private fun updateSensorsAndWakeLock() {
        sensorManager.unregisterListener(this)
        val active = checkin
        if (label == null && active == null) {
            wakeLock?.takeIf { it.isHeld }?.release()
            return
        }
        // Batching saves battery while detecting; the logger keeps it off so a stop loses no events.
        val latencyUs = if (label != null) 0 else MAX_REPORT_LATENCY_US
        val registered = SENSOR_TYPES.mapNotNull { type ->
            sensorManager.getDefaultSensor(type)?.also {
                sensorManager.registerListener(this, it, SAMPLING_PERIOD, latencyUs, sensorHandler)
            }
        }
        Log.i(TAG, "sensors=${registered.map { it.name }} latencyUs=$latencyUs")

        // Non-wakeup sensors stop delivering when the CPU sleeps, so a partial wake lock keeps it
        // awake with the screen off. While only detecting, it times out at the check-in's expiry,
        // so a missed stop cannot drain the battery (Cristea, 2026-11-06).
        val lock = wakeLock ?: getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "FloorWars:sensors")
            .apply { setReferenceCounted(false) }
            .also { wakeLock = it }
        if (label != null || active == null) {
            lock.acquire()
        } else {
            lock.acquire(active.validUntilMs - System.currentTimeMillis())
        }
    }

    override fun onDestroy() {
        mainHandler.removeCallbacks(expire)
        sensorManager.unregisterListener(this)
        sensorHandler.post {
            detector?.stop()
            detector = null
        }
        // Runs the flush above, then ends the thread.
        sensorThread.quitSafely()
        wakeLock?.takeIf { it.isHeld }?.release()
        wakeLock = null
        checkin = null
        Log.i(TAG, "stopped label=$label buffered=${buffer.size()} byType=${buffer.countByType()}")
        session = session?.copy(stoppedAtMillis = System.currentTimeMillis())
        label = null
        statusListener?.invoke()
        super.onDestroy()
    }

    override fun onSensorChanged(event: SensorEvent) {
        // The framework reuses event.values, so copy it.
        val raw = RawSensorEvent(event.sensor.type, event.timestamp, event.values.copyOf())
        if (label != null) buffer.add(raw)
        detector?.let {
            if (raw.sensorType == Sensor.TYPE_PRESSURE) {
                it.add(listOf(raw), emptyList())
            } else {
                it.add(emptyList(), listOf(raw))
            }
        }
    }

    override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) = Unit

    private val outboxOrDrop = object : SegmentOutbox {
        override fun insert(segment: OutboxSegment) {
            val target = outbox
            if (target == null) {
                droppedNoOutbox++
                Log.w(TAG, "no outbox, segment dropped ($droppedNoOutbox so far)")
            } else {
                target.insert(segment)
            }
        }
    }

    private fun startForeground() {
        val logging = label
        val notification = if (logging != null) {
            buildNotification(
                getString(R.string.sensor_notification_title),
                getString(R.string.sensor_notification_text, logging)
            )
        } else {
            buildNotification(
                getString(R.string.detect_notification_title),
                getString(R.string.detect_notification_text)
            )
        }
        ServiceCompat.startForeground(
            this,
            NOTIFICATION_ID,
            notification,
            ServiceInfo.FOREGROUND_SERVICE_TYPE_HEALTH
        )
    }

    private fun buildNotification(title: String, text: String): Notification {
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
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(openApp)
            .setOngoing(true)
            .build()
    }

    companion object {
        const val EXTRA_LABEL = "label"
        const val ACTION_DETECT = "com.floorwars.floorsensors.DETECT"
        const val ACTION_STOP_DETECT = "com.floorwars.floorsensors.STOP_DETECT"
        const val EXTRA_CHECKIN_ID = "checkin_id"
        const val EXTRA_BUILDING_ID = "building_id"
        const val EXTRA_BUILDING_NAME = "building_name"
        const val EXTRA_VALID_UNTIL_MS = "valid_until_ms"
        private const val TAG = "FloorSensors"
        private const val CHANNEL_ID = "sensor_logging"
        private const val NOTIFICATION_ID = 1
        private val SENSOR_TYPES = listOf(Sensor.TYPE_PRESSURE, Sensor.TYPE_STEP_DETECTOR)

        // About 25 Hz on the SM-S918B and 10 Hz on the SM-G985F (plan 3.3), plenty for an 8 s median.
        private const val SAMPLING_PERIOD = SensorManager.SENSOR_DELAY_GAME

        // The sensor hub may hold events up to 5 s and hand them over in one burst, fewer callbacks
        // than one per event. The segmenter runs every 5 s anyway (LiveSegmenterParams.EVAL_INTERVAL_S).
        private const val MAX_REPORT_LATENCY_US = 5_000_000

        // Bounded so a forgotten session cannot exhaust memory.
        val buffer = SensorEventBuffer(capacity = 100_000)

        // Set by the outbox owner (Room). Until then a segment is dropped and counted, never faked.
        @Volatile
        var outbox: SegmentOutbox? = null

        @Volatile
        var droppedNoOutbox = 0
            private set

        // Non-null while logging: the logger screen's session is running.
        @Volatile
        var label: String? = null
            private set

        // The latest session; stoppedAtMillis is set once it has stopped.
        @Volatile
        var session: TraceSession? = null
            private set

        @Volatile
        var statusListener: (() -> Unit)? = null
    }
}
