package online.hockeylive.tv

import android.content.Context

object AppSettings {
    private const val PREFS = "hockey_live_tv"
    private const val KEY_SERVER = "server_url"
    private const val KEY_AUTHORIZED = "tv_authorized"
    private const val KEY_DEVICE = "device_id"
    private const val KEY_UPDATE_DISMISSED_CODE = "update_dismissed_version_code"
    private const val KEY_UPDATE_APK_URL = "update_downloaded_apk_url"
    const val DEFAULT_SERVER = "https://hockey-live.alwaysdata.net"

    /** Стабильный UUID устройства — для восстановления авторизации на сервере. */
    fun deviceId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        return prefs.getString(KEY_DEVICE, null) ?: java.util.UUID.randomUUID()
            .toString()
            .also { prefs.edit().putString(KEY_DEVICE, it).apply() }
    }

    fun serverUrl(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_SERVER, DEFAULT_SERVER) ?: DEFAULT_SERVER

    fun setServerUrl(context: Context, url: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_SERVER, url.trim().trimEnd('/'))
            .apply()
    }

    fun isAuthorized(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_AUTHORIZED, false)

    fun setAuthorized(context: Context, value: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_AUTHORIZED, value)
            .apply()
    }

    /** version_code обновления, для которого пользователь уже нажал «Позже». */
    fun updateDismissedCode(context: Context): Int =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getInt(KEY_UPDATE_DISMISSED_CODE, 0)

    fun setUpdateDismissedCode(context: Context, versionCode: Int) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putInt(KEY_UPDATE_DISMISSED_CODE, versionCode)
            .apply()
    }

    /** URL APK, уже скачанного в кэш. Переживает перезапуск процесса. */
    fun downloadedApkUrl(context: Context): String? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_UPDATE_APK_URL, null)

    fun setDownloadedApkUrl(context: Context, url: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_UPDATE_APK_URL, url)
            .apply()
    }
}
