package com.floorwars.sync

import android.content.Intent
import com.facebook.react.HeadlessJsTaskService
import com.facebook.react.bridge.Arguments
import com.facebook.react.jstasks.HeadlessJsTaskConfig

class SyncTaskService : HeadlessJsTaskService() {
    override fun getTaskConfig(intent: Intent?) =
        HeadlessJsTaskConfig(TASK_KEY, Arguments.createMap(), TIMEOUT_MS, true)

    companion object {
        const val TASK_KEY = "FloorWarsSync" // registered in index.js
        const val TIMEOUT_MS = 120_000L
    }
}
