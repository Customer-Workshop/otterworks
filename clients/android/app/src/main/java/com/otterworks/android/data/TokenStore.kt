package com.otterworks.android.data

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/**
 * Persists the JWT access token (and lightweight user info) across app launches.
 *
 * Uses [EncryptedSharedPreferences] when available and falls back to plain
 * [SharedPreferences] if the keystore-backed store cannot be initialised (which
 * can happen on some emulator images).
 */
class TokenStore(context: Context) {

    private val prefs: SharedPreferences = createPrefs(context.applicationContext)

    // Cached in memory for fast, synchronous access.
    @Volatile
    var accessToken: String? = prefs.getString(KEY_TOKEN, null)
        private set

    val displayName: String?
        get() = prefs.getString(KEY_DISPLAY_NAME, null)

    fun save(token: String, displayName: String?) {
        accessToken = token
        prefs.edit()
            .putString(KEY_TOKEN, token)
            .putString(KEY_DISPLAY_NAME, displayName)
            .apply()
    }

    fun clear() {
        accessToken = null
        prefs.edit().clear().apply()
    }

    fun isLoggedIn(): Boolean = !accessToken.isNullOrBlank()

    private fun createPrefs(context: Context): SharedPreferences {
        return try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
            EncryptedSharedPreferences.create(
                context,
                "otterworks_secure_prefs",
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
            )
        } catch (e: Exception) {
            Log.w(TAG, "Falling back to plain SharedPreferences", e)
            context.getSharedPreferences("otterworks_prefs", Context.MODE_PRIVATE)
        }
    }

    private companion object {
        const val TAG = "TokenStore"
        const val KEY_TOKEN = "access_token"
        const val KEY_DISPLAY_NAME = "display_name"
    }
}
