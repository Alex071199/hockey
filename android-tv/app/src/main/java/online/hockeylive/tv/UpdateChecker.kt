package online.hockeylive.tv

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import androidx.core.content.FileProvider
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

@Serializable
data class AppVersionInfo(
    val version: String = "",
    val version_code: Int = 0,
    val apk_url: String? = null,
    val notes: String = "",
    val force_update: Boolean = false,
)

object UpdateChecker {

    private val json = Json { ignoreUnknownKeys = true }
    private val http = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    fun currentVersionCode(context: Context): Int {
        return try {
            context.packageManager.getPackageInfo(context.packageName, 0).longVersionCode.toInt()
        } catch (e: Exception) {
            BuildConfig.VERSION_CODE
        }
    }

    fun check(serverUrl: String, callback: (AppVersionInfo?) -> Unit) {
        Thread {
            val result = try {
                val url = "${serverUrl.trimEnd('/')}/api/app/version"
                val resp = http.newCall(Request.Builder().url(url).build()).execute()
                if (resp.isSuccessful) {
                    resp.body?.string()?.let { json.decodeFromString<AppVersionInfo>(it) }
                } else null
            } catch (e: Exception) {
                null
            }
            Handler(Looper.getMainLooper()).post { callback(result) }
        }.start()
    }

    fun downloadAndInstall(context: Context, apkUrl: String, onProgress: (String) -> Unit) {
        Thread {
            try {
                onProgress("Скачиваю обновление…")
                val resp = http.newCall(Request.Builder().url(apkUrl).build()).execute()
                if (!resp.isSuccessful) {
                    onProgress("Ошибка скачивания: HTTP ${resp.code}")
                    return@Thread
                }
                val dir = File(context.cacheDir, "updates").apply { mkdirs() }
                val file = File(dir, "update.apk")
                resp.body?.byteStream()?.use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                onProgress("Устанавливаю… (${file.length() / 1024 / 1024} МБ)")
                val uri: Uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                context.startActivity(intent)
                onProgress("Подтвердите установку в системном окне.")
            } catch (e: Exception) {
                onProgress("Ошибка: ${e.message}")
            }
        }.start()
    }
}
