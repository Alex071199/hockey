package online.hockeylive.tv

import android.content.Context

object AppSettings {
    private const val PREFS = "hockey_live_tv"
    private const val KEY_SERVER = "server_url"
    const val DEFAULT_SERVER = "https://hockey-live-production-b0cc.up.railway.app"

    fun serverUrl(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SERVER, DEFAULT_SERVER) ?: DEFAULT_SERVER

    fun setServerUrl(context: Context, url: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER, url.trim().trimEnd('/'))
            .apply()
    }
}
