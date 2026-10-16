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
import java.io.File

class EngineSetupActivity : ComponentActivity() {

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
        root.addView(text("\nДвижок уже встроен в приложение — установка не требует интернета."))
        root.addView(text("Нажмите кнопку ниже один раз.\n"))
        root.addView(text("Архитектура: ${Build.SUPPORTED_ABIS.firstOrNull() ?: "неизвестно"}", 14f, 0xFF8B98A5.toInt()))

        statusText = text("\nНажмите «Установить», чтобы распаковать и запустить установщик.")
        root.addView(statusText)

        root.addView(text("\n"))

        button = Button(this).apply {
            text = "Установить"
            setOnClickListener { extractAndInstall() }
        }
        root.addView(button)
    }

    private fun engineAsset(): String {
        val abis = Build.SUPPORTED_ABIS.toList()
        return when {
            abis.contains("arm64-v8a") || abis.contains("x86_64") -> "engine/armv8_64.apk"
            else -> "engine/armv7.apk"
        }
    }

    private fun setStatus(value: String) {
        mainHandler.post { statusText.text = value }
    }

    private fun extractAndInstall() {
        button.isEnabled = false
        setStatus("Распаковываю встроенный движок…")
        Thread {
            try {
                val assetPath = engineAsset()
                val dir = File(cacheDir, "engine").apply { mkdirs() }
                val file = File(dir, "acestream-core.apk")
                assets.open(assetPath).use { input ->
                    file.outputStream().use { output -> input.copyTo(output) }
                }
                setStatus("Запускаю установщик… (${file.length() / 1024 / 1024} МБ)")
                val uri: Uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                startActivity(intent)
                setStatus("Подтвердите установку в системном окне.\nПосле установки вернитесь к матчу.")
            } catch (e: Exception) {
                setStatus("Ошибка: ${e.message}")
            } finally {
                mainHandler.post { button.isEnabled = true }
            }
        }.start()
    }
}
