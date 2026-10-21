package com.floorwars

import android.app.Application
import com.facebook.react.PackageList
import com.facebook.react.ReactApplication
import com.facebook.react.ReactHost
import com.facebook.react.ReactNativeApplicationEntryPoint.loadReactNative
import com.facebook.react.defaults.DefaultReactHost.getDefaultReactHost
import com.floorwars.floorsensors.FloorSensorsPackage

class MainApplication :
    Application(),
    ReactApplication {

    override val reactHost: ReactHost by lazy {
        getDefaultReactHost(
            context = applicationContext,
            packageList =
            PackageList(this).packages.apply {
                add(FloorSensorsPackage())
            }
        )
    }

    override fun onCreate() {
        super.onCreate()
        loadReactNative(this)
    }
}
