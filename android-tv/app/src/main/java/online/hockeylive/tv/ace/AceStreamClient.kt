package online.hockeylive.tv.ace

import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.io.PrintWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URLDecoder
import java.security.MessageDigest

/**
 * Telnet API движка AceStream (127.0.0.1:62062).
 * Протокол: HELLOBG -> READY(sha1) -> AUTH -> LOADASYNC -> START -> playback url.
 * После START сокет остаётся открытым: фоновый цикл читает STATUS (keepalive).
 */
object AceStreamClient {

    private const val TAG = "AceApiClient"
    private const val HOST = "127.0.0.1"
    private const val API_PORT = 62062
    private const val PRODUCT_KEY =
        "n51LvQoTlJzNGaFxseRK-uvnvX-sD4Vm5Axwmc4UcoD-jruxmKsuJaH0eVgE"

    private var socket: Socket? = null
    private var reader: BufferedReader? = null
    private var writer: PrintWriter? = null
    private var keepAliveJob: Job? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    @Synchronized
    fun isActive(): Boolean = socket?.isConnected == true && socket?.isClosed == false

    /**
     * @param sourceType "infohash" (40 hex) или "pid"
     * @param value сам хэш/идентификатор
     * @param onStatus вызывается из фонового потока, сюда можно слать тексты в UI
     * @return локальный http-url воспроизведения (http://127.0.0.1:6878/...)
     */
    suspend fun startStream(
        sourceType: String,
        value: String,
        onStatus: (String) -> Unit = {},
    ): String = withContext(Dispatchers.IO) {
        val hadSession = isActive()
        closeLocked()
        if (hadSession) {
            // движок должен успеть завершить прошлую сессию (как в aceHub: delay 500)
            Thread.sleep(500)
        }

        onStatus("Подключение к движку…")
        val s = connectWithRetry()
        s.soTimeout = 60_000
        socket = s
        val r = BufferedReader(InputStreamReader(s.getInputStream()))
        val w = PrintWriter(OutputStreamWriter(s.getOutputStream()), true)
        reader = r
        writer = w

        // 1. Handshake
        w.print("HELLOBG version=4\r\n")
        w.flush()

        var authenticated = false
        val deadline = System.currentTimeMillis() + 15_000
        while (System.currentTimeMillis() < deadline && !authenticated) {
            val line = r.readLine() ?: break
            Log.d(TAG, "RECV [AUTH]: $line")
            when {
                line.startsWith("HELLOTS") -> {
                    val keyMatch = Regex("key=([^\\s]+)").find(line)
                    if (keyMatch != null) {
                        val readyKey = computeReadyKey(keyMatch.groupValues[1], PRODUCT_KEY)
                        w.print("READY key=$readyKey\r\n")
                        w.flush()
                    }
                }
                line.startsWith("AUTH") -> {
                    authenticated = true
                    Log.i(TAG, "authenticated: $line")
                    w.print("STOP\r\n")
                    w.print("STOPDL\r\n")
                    w.print("SETOPTIONS use_stop_notifications=1\r\n")
                    w.flush()
                    Thread.sleep(200)
                }
                line.startsWith("NOTREADY") -> {
                    closeLocked()
                    throw IllegalStateException("Движок вернул NOTREADY")
                }
            }
        }
        if (!authenticated) {
            closeLocked()
            throw IllegalStateException("Не удалось аутентифицироваться в движке")
        }

        // 2. LOADASYNC
        onStatus("Загрузка канала P2P…")
        val isInfohash = sourceType == "infohash"
        if (isInfohash) {
            w.print("LOADASYNC 0 INFOHASH $value 0 0 0\r\n")
        } else {
            w.print("LOADASYNC 0 PID $value\r\n")
        }
        w.flush()

        var loaded = false
        var canonicalHash = if (isInfohash) value else ""
        val loadDeadline = System.currentTimeMillis() + 20_000
        while (System.currentTimeMillis() < loadDeadline && !loaded) {
            val line = r.readLine() ?: break
            Log.d(TAG, "RECV [LOAD]: $line")
            if (line.startsWith("LOADRESP")) {
                if (line.contains("\"status\": 100") ||
                    line.contains("\"status\": 0") ||
                    line.contains("Cannot load transport file")
                ) {
                    closeLocked()
                    throw IllegalStateException("Движок не смог загрузить канал")
                }
                val hashMatch =
                    Regex("\"infohash\"\\s*:\\s*\"([a-fA-F0-9]{40})\"").find(line)
                if (hashMatch != null) canonicalHash = hashMatch.groupValues[1]
                loaded = true
            }
        }

        // 3. START
        onStatus("Запуск потока…")
        val targetHash = canonicalHash.ifEmpty { value }
        val startCmd = if (targetHash.length == 40) {
            "START INFOHASH $targetHash 0 0 0 0 output_format=http\r\n"
        } else {
            "START PID $value 0 output_format=http\r\n"
        }
        Log.i(TAG, "send: ${startCmd.trim()}")
        w.print(startCmd)
        w.flush()

        var playbackUrl: String? = null
        val startDeadline = System.currentTimeMillis() + 60_000
        while (System.currentTimeMillis() < startDeadline && playbackUrl == null) {
            val line = r.readLine() ?: break
            Log.d(TAG, "RECV [START]: $line")
            when {
                line.startsWith("START") -> {
                    val urlMatch = Regex("url=([^\\s]+)").find(line)
                    if (urlMatch != null) {
                        playbackUrl = URLDecoder.decode(urlMatch.groupValues[1], "UTF-8")
                    }
                }
                line.startsWith("EVENT showdialog") -> {
                    closeLocked()
                    throw IllegalStateException("Движок запросил premium-доступ")
                }
                line.startsWith("EVENT download_stopped") -> {
                    closeLocked()
                    throw IllegalStateException("Движок остановил загрузку")
                }
            }
        }
        if (playbackUrl == null) {
            closeLocked()
            throw IllegalStateException("Движок не вернул url потока за 60 секунд")
        }
        Log.i(TAG, "started: $playbackUrl")

        // 4. Keepalive: сокет обязан оставаться открытым, пока играет поток
        s.soTimeout = 0
        keepAliveJob = scope.launch {
            try {
                while (isActive()) {
                    val line = r.readLine() ?: break
                    if (line.startsWith("STATUS")) {
                        Log.d(TAG, "STATUS: $line")
                    }
                }
            } catch (e: Exception) {
                Log.d(TAG, "keepalive ended: ${e.message}")
            }
        }

        playbackUrl
    }

    /**
     * Умный запуск: 40-символьный id сначала пробуем как infohash,
     * при неудаче — как content_id (fallback из aceHub).
     */
    suspend fun startSmart(value: String, onStatus: (String) -> Unit = {}): String {
        val is40 = value.matches(Regex("[0-9a-fA-F]{40}"))
        val primary = if (is40) "infohash" else "content_id"
        return try {
            startStream(primary, value, onStatus)
        } catch (e: Exception) {
            if (value.length == 40) {
                val alt = if (primary == "infohash") "content_id" else "infohash"
                Log.w(TAG, "retry with $alt after: ${e.message}")
                startStream(alt, value, onStatus)
            } else {
                throw e
            }
        }
    }

    /** Останавливает текущую сессию (STOP/STOPDL) и закрывает сокет. */
    suspend fun stop() = withContext(Dispatchers.IO) {
        closeLocked()
    }

    /** Для мест, где нельзя вызвать suspend (onDestroy и т.п.). */
    fun stopAsync() {
        scope.launch { closeLocked() }
    }

    @Synchronized
    private fun closeLocked() {
        keepAliveJob?.cancel()
        keepAliveJob = null
        try {
            writer?.print("STOP\r\n")
            writer?.print("STOPDL\r\n")
            writer?.flush()
        } catch (_: Exception) {
        }
        try {
            socket?.close()
        } catch (_: Exception) {
        }
        socket = null
        reader = null
        writer = null
    }

    private fun connectWithRetry(): Socket {
        var last: Exception? = null
        repeat(3) { attempt ->
            try {
                val s = Socket()
                s.connect(InetSocketAddress(HOST, API_PORT), 3000)
                return s
            } catch (e: Exception) {
                last = e
                Log.w(TAG, "telnet connect attempt ${attempt + 1} failed: ${e.message}")
                Thread.sleep(1000)
            }
        }
        throw IllegalStateException("Не удалось подключиться к движку: ${last?.message}")
    }

    private fun computeReadyKey(reqKey: String, productKey: String): String {
        val digest = MessageDigest.getInstance("SHA-1")
            .digest((reqKey + productKey).toByteArray(Charsets.UTF_8))
        val hex = digest.joinToString("") { "%02x".format(it) }
        return "${productKey.substringBefore("-")}-$hex"
    }
}
