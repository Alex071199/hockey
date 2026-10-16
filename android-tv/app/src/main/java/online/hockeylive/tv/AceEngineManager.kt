package online.hockeylive.tv

import android.content.Context
import android.os.Handler
import android.os.Looper
import okhttp3.OkHttpClient
import okhttp3.Request
import org.acestream.engine.ServiceClient
import java.util.concurrent.TimeUnit

/**
 * Запускает установленный движок Ace Stream (через AIDL-сервис) и ждёт,
 * пока его HTTP API на 127.0.0.1 будет готов отдавать HLS.
 */
class AceEngineManager(private val context: Context) {

    sealed class Result {
        data class Ready(val httpPort: Int) : Result()
        object EngineMissing : Result()
        data class Failed(val message: String) : Result()
    }

    private val http = OkHttpClient.Builder()
        .connectTimeout(2, TimeUnit.SECONDS)
        .readTimeout(2, TimeUnit.SECONDS)
        .build()

    private val mainHandler = Handler(Looper.getMainLooper())
    private var client: ServiceClient? = null
    private var finished = false

    fun start(callback: (Result) -> Unit) {
        val serviceClient = ServiceClient("hockey", context, object : ServiceClient.Callback {
            override fun onConnected(service: org.acestream.engine.service.v0.IAceStreamEngine?) {
                val port = client?.httpApiPort ?: 0
                if (port > 0) {
                    waitForHttpApi(port, callback)
                } else {
                    finish(callback, Result.Failed("Движок не отдал HTTP-порт"))
                }
            }

            override fun onFailed() {
                finish(callback, Result.Failed("Движок не запустился"))
            }

            override fun onDisconnected() {}
            override fun onUnpacking() {}
            override fun onStarting() {}
            override fun onStopped() {}
            override fun onPlaylistUpdated() {}
            override fun onEPGUpdated() {}
            override fun onRestartPlayer() {}
            override fun onSettingsUpdated() {}
            override fun onAuthUpdated() {}
        })
        client = serviceClient
        try {
            serviceClient.bind()
            serviceClient.startEngine()
        } catch (e: ServiceClient.ServiceMissingException) {
            finish(callback, Result.EngineMissing)
        } catch (e: Exception) {
            finish(callback, Result.Failed(e.message ?: "Ошибка запуска движка"))
        }
    }

    private fun waitForHttpApi(port: Int, callback: (Result) -> Unit, attempt: Int = 0) {
        Thread {
            val url = "http://127.0.0.1:$port/webui/api/service?method=get_version&format=jsonp"
            val ok = try {
                val resp = http.newCall(Request.Builder().url(url).build()).execute()
                resp.use { it.isSuccessful && it.body?.string()?.contains("version") == true }
            } catch (e: Exception) {
                false
            }
            if (ok) {
                finish(callback, Result.Ready(port))
            } else if (attempt < 45) {
                mainHandler.postDelayed({ waitForHttpApi(port, callback, attempt + 1) }, 1000)
            } else {
                finish(callback, Result.Failed("Движок не ответил за 45 секунд"))
            }
        }.start()
    }

    private fun finish(callback: (Result) -> Unit, result: Result) {
        if (finished) return
        finished = true
        mainHandler.post { callback(result) }
    }

    fun release() {
        try {
            client?.unbind()
        } catch (_: Exception) {
        }
        client = null
    }
}
