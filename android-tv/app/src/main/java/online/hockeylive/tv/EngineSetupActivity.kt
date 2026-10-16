package online.hockeylive.tv

import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.core.content.FileProvider
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.util.concurrent.TimeUnit

class EngineSetupActivity : ComponentActivity() {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private val mainHandler = Handler(Looper.getMainLooper())
    private lateinit var statusText: TextView
    private lateinit var button: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(64, 64, 64, 64)
            setBackgroundColor(0xFF0D1117.toInt())
        }
        scroll.addView(root)
        setContentView(scroll)

        fun text(value: String, size: Float = 18f, color: Int = 0xFFC9D1D9.toInt()): TextView {
            return TextView(this).apply {
                text = value
                textSize = size
                setTextColor(color)
            }
        }

        root.addView(text("Движок Ace Stream", 28f, 0xFF4AC7FF.toInt()))
        root.addView(text("\nДля просмотра AceStream-трансляций нужен бесплатный движок Ace Stream."))
        root.addView(text("Установите его один раз — приложение само будет его запускать.\n"))
        root.addView(text("Архитектура: ${Build.SUPPORTED_ABIS.firstOrNull() ?: "неизвестно"}", 14f, 0xFF8B98A5.toInt()))
        root.addView(text("Ссылка: ${engineUrl()}\n", 12f, 0xFF8B98A5.toInt()))

        statusText = text("Нажмите кнопку ниже, чтобы скачать и установить движок.")
        root.addView(statusText)

        root.addView(text("\n"))

        button = Button(this).apply {
            text = "Скачать и установить"
            setOnClickListener { downloadAndInstall() }
        }
        root.addView(button)
    }

    private fun engineUrl(): String {
        val abis = Build.SUPPORTED_ABIS.toList()
        val arch = when {
            abis.contains("arm64-v8a") -> "armv8_64"
            abis.contains("armeabi-v7a") -> "armv7"
            abis.contains("x86_64") -> "x86_64"
            abis.contains("x86") -> "x86"
            else -> "armv8_64"
        }
        return "https://download.acestream.media/products/android-tv/acestream-core/$arch/latest"
    }

    private fun setStatus(value: String) {
        mainHandler.post { statusText.text = value }
    }

    private fun downloadAndInstall() {
        button.isEnabled = false
        setStatus("Скачиваю движок…")
        Thread {
            try {
                val resp = http.newCall(Request.Builder().url(engineUrl()).build()).execute()
                if (!resp.isSuccessful) {
                    setStatus("Ошибка скачивания: HTTP ${resp.code}")
                    return@Thread
                }
                val dir = File(filesDir, "downloads").apply { mkdirs() }
                val file = File(dir, "acestream-engine.apk")
                resp.body?.byteStream()?.use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                setStatus("Устанавливаю… (${file.length() / 1024 / 1024} МБ)")
                val uri: Uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                startActivity(intent)
                setStatus("Если установщик не открылся — разрешите установку из неизвестных источников и повторите.")
            } catch (e: Exception) {
                setStatus("Ошибка: ${e.message}\n\nПопробуйте скачать вручную:\n${engineUrl()}")
            } finally {
                mainHandler.post { button.isEnabled = true }
            }
        }.start()
    }
}
