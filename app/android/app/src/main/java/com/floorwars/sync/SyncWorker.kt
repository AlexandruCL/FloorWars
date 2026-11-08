package com.floorwars.sync

import android.content.Context
import android.content.Intent
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import java.util.concurrent.TimeUnit

// Wakes the JS sync worker through Headless JS. It never uploads by itself: the sync logic lives
// in app/src/sync.
class SyncWorker(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result = try {
        applicationContext.startService(Intent(applicationContext, SyncTaskService::class.java))
        Result.success()
    } catch (e: IllegalStateException) {
        // Android refused a background service start; try again on the next backoff.
        Result.retry()
    }

    companion object {
        const val NAME = "floorwars-sync"
        const val INTERVAL_MINUTES = 15L // WorkManager's minimum period

        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(INTERVAL_MINUTES, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
                )
                .build()
            WorkManager.getInstance(context)
                .enqueueUniquePeriodicWork(NAME, ExistingPeriodicWorkPolicy.KEEP, request)
        }
    }
}
