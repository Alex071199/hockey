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

    /**
     * versionCode реально установленного пакета.
     *
     * Берём именно его, а не BuildConfig.VERSION_CODE: при установке поверх другой
     * сборки (или при рассинхроне прогона и сервера) константа сборки может
     * расходиться с тем, что стоит на устройстве, и приложение будет «вечно
     * требовать обновление» уже актуальной версии.
     */
    @Suppress("DEPRECATION")
    fun currentVersionCode(context: Context): Int {
        return try {
            // versionCode (int) доступен с API 1; longVersionCode — только с API 28,
            // а minSdk здесь 21, поэтому на старых ТВ он бросил бы NoSuchMethodError.
            context.packageManager.getPackageInfo(context.packageName, 0).versionCode
        } catch (e: Exception) {
            BuildConfig.VERSION_CODE
        }
    }

    private fun cachedFile(context: Context): File =
        File(File(context.cacheDir, "updates").apply { mkdirs() }, "update.apk")

    /**
     * APK для этого url уже скачан и готов к установке.
     * Отметка живёт в SharedPreferences, а не в памяти процесса, поэтому скачанный
     * 57 МБ APK не качается заново при каждом перезапуске приложения.
     */
    fun isReady(context: Context, apkUrl: String): Boolean =
        AppSettings.downloadedApkUrl(context) == apkUrl &&
            cachedFile(context).let { it.exists() && it.length() > 0 }

    private fun markReady(context: Context, apkUrl: String) {
        AppSettings.setDownloadedApkUrl(context, apkUrl)
    }

    /** Callback'ки обновления приходят на main потоке — состояния Compose правятся корректно. */
    private fun main(block: () -> Unit) = Handler(Looper.getMainLooper()).post(block)

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
            main { onDone(true) }
            return
        }
        Thread {
            try {
                val resp = http.newCall(Request.Builder().url(apkUrl).build()).execute()
                if (!resp.isSuccessful) {
                    main { onProgress("Ошибка скачивания: HTTP ${resp.code}"); onDone(false) }
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
                            // Обновляем прогресс на main — Compose-стейт безопасно меняет UI.
                            if (total > 0) {
                                main {
                                    onProgress("Скачиваю ${read * 100 / total}%…")
                                }
                            }
                        }
                    }
                }
                markReady(context, apkUrl)
                main {
                    onProgress("Готово — нажмите «Обновить»")
                    onDone(file.exists() && file.length() > 0)
                }
            } catch (e: Exception) {
                main { onProgress("Ошибка: ${e.message}"); onDone(false) }
            }
        }.start()
    }

    /** Ставит из кэша; если кэша нет — сначала скачивает. */
    fun downloadAndInstall(context: Context, apkUrl: String, onProgress: (String) -> Unit) {
        if (isReady(context, apkUrl)) {
            main { onProgress("Подтвердите установку в системном окне.") }
            main { install(context, cachedFile(context)) }
            return
        }
        Thread {
            try {
                main { onProgress("Скачиваю обновление…") }
                val resp = http.newCall(Request.Builder().url(apkUrl).build()).execute()
                if (!resp.isSuccessful) {
                    main { onProgress("Ошибка скачивания: HTTP ${resp.code}") }
                    return@Thread
                }
                val file = cachedFile(context)
                resp.body?.byteStream()?.use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                markReady(context, apkUrl)
                main {
                    onProgress("Устанавливаю… (${file.length() / 1024 / 1024} МБ)")
                }
                main { install(context, file) }
            } catch (e: Exception) {
                main { onProgress("Ошибка: ${e.message}") }
            }
        }.start()
    }

    @Suppress("DEPRECATION")
    private fun install(context: Context, file: File) {
        val uri: Uri = FileProvider.getUriForFile(context, "${context.packageName}.fileprovider", file)
        // ACTION_INSTALL_PACKAGE — штатный способ для APK; часть TV-прошивок
        // не обрабатывает ACTION_VIEW и молча закрывает установщик, из-за чего
        // обновление «не приживалось» и просилось снова при каждом запуске.
        val intent = Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
            data = uri
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            context.startActivity(intent)
        } catch (e: Exception) {
            val fallback = Intent(Intent.ACTION_VIEW).apply {
                setDataAndType(uri, "application/vnd.android.package-archive")
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            try {
                context.startActivity(fallback)
            } catch (e2: Exception) {
                Handler(Looper.getMainLooper()).post {
                    android.widget.Toast.makeText(
                        context,
                        "Не удалось открыть установщик: ${e2.message}",
                        android.widget.Toast.LENGTH_LONG,
                    ).show()
                }
            }
        }
    }
}
