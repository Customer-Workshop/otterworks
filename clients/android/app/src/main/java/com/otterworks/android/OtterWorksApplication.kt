package com.otterworks.android

import android.app.Application
import com.otterworks.android.data.OtterWorksRepository
import com.otterworks.android.data.TokenStore
import com.otterworks.android.data.remote.ApiClient

/**
 * Owns the singletons for the app. A lightweight manual service locator keeps the
 * project dependency-injection-framework free while still centralising wiring.
 */
class OtterWorksApplication : Application() {

    lateinit var repository: OtterWorksRepository
        private set

    override fun onCreate() {
        super.onCreate()
        val tokenStore = TokenStore(this)
        val api = ApiClient.create(tokenStore)
        repository = OtterWorksRepository(api, tokenStore)
    }
}
