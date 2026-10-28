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

    /** URL, чей APK уже скачан в кэш (чтобы не качать повторно). */
    @Volatile
    private var downloadedUrl: String? = null

    fun currentVersionCode(context: Context): Int {
        return try {
            context.packageManager.getPackageInfo(context.packageName, 0).longVersionCode.toInt()
        } catch (e: Exception) {
            BuildConfig.VERSION_CODE
        }
    }

    private fun cachedFile(context: Context): File =
        File(File(context.cacheDir, "updates").apply { mkdirs() }, "update.apk")

    /** APK для этого url уже скачан и готов к установке? */
    fun isReady(context: Context, apkUrl: String): Boolean =
        downloadedUrl == apkUrl && cachedFile(context).let { it.exists() && it.length() > 0 }

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

    /** Фоновое скачивание APK в кэш (без установки). */
    fun prefetch(context: Context, apkUrl: String, onProgress: (String) -> Unit, onDone: (Boolean) -> Unit) {
        if (isReady(context, apkUrl)) {
            Handler(Looper.getMainLooper()).post { onDone(true) }
            return
        }
        Thread {
            try {
                val resp = http.newCall(Request.Builder().url(apkUrl).build()).execute()
                if (!resp.isSuccessful) {
                    Handler(Looper.getMainLooper()).post { onDone(false) }
                    return@Thread
                }
                val file = cachedFile(context)
                var read = 0L
                val total = resp.body?.contentLength() ?: -1L
                resp.body?.byteStream()?.use { input ->
                    file.outputStream().use { output ->
                        val buf = ByteArray(64 * 1024)
                        while (true) {
                            val n = input.read(buf)
                            if (n < 0) break
                            output.write(buf, 0, n)
                            read += n
                        }
                    }
                }
                downloadedUrl = apkUrl
                Handler(Looper.getMainLooper()).post { onDone(file.exists() && file.length() > 0) }
            } catch (e: Exception) {
                Handler(Looper.getMainLooper()).post { onDone(false) }
            }
        }.start()
    }

    /** Ставит из кэша; если кэша нет — сначала скачивает. */
    fun downloadAndInstall(context: Context, apkUrl: String, onProgress: (String) -> Unit) {
        if (isReady(context, apkUrl)) {
            onProgress("Подтвердите установку в системном окне.")
            install(context, cachedFile(context))
            return
        }
        Thread {
            try {
                onProgress("Скачиваю обновление…")
                val resp = http.newCall(Request.Builder().url(apkUrl).build()).execute()
                if (!resp.isSuccessful) {
                    onProgress("Ошибка скачивания: HTTP ${resp.code}")
                    return@Thread
                }
                val file = cachedFile(context)
                resp.body?.byteStream()?.use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                downloadedUrl = apkUrl
                onProgress("Устанавливаю… (${file.length() / 1024 / 1024} МБ)")
                install(context, file)
            } catch (e: Exception) {
                onProgress("Ошибка: ${e.message}")
            }
        }.start()
    }

    private fun install(context: Context, file: File) {
        val uri: Uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }
}
