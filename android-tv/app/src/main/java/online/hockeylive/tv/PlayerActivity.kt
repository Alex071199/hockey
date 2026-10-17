package online.hockeylive.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

class PlayerActivity : ComponentActivity() {

    companion object {
        const val EXTRA_MATCH_JSON = "match_json"
        const val EXTRA_SOURCE_URL = "source_url"
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var webView: WebView? = null
    private var statusText: TextView? = null
    private var match: Match? = null

    // Очередь источников (prime — первый) и текущий индекс
    private var sources: List<StreamUrl> = emptyList()
    private var sourceIndex: Int = -1

    private val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
    private var webTimeout: Runnable? = null
    private var changingSource = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val json = intent.getStringExtra(EXTRA_MATCH_JSON)
        match = try {
            Json.decodeFromString<Match>(json ?: "")
        } catch (e: Exception) {
            null
        }

        val root = FrameLayout(this).apply { setBackgroundColor(0xFF0A0A0A.toInt()) }

        val pv = PlayerView(this).apply {
            useController = true
            controllerShowTimeoutMs = 4000
            setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS)
            visibility = View.GONE
        }
        root.addView(pv, FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)

        val wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.setSupportMultipleWindows(false)
            settings.userAgentString =
                "Mozilla/5.0 (Linux; Android 12; SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            visibility = View.GONE
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = false
                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    hideStatus()
                }

                override fun onReceivedError(
                    view: WebView,
                    request: WebResourceRequest,
                    error: android.webkit.WebResourceError,
                ) {
                    if (request.isForMainFrame) {
                        nextSource("web_error ${error.errorCode}")
                    }
                }

                override fun onReceivedHttpError(
                    view: WebView,
                    request: WebResourceRequest,
                    errorResponse: android.webkit.WebResourceResponse,
                ) {
                    if (request.isForMainFrame && errorResponse.statusCode in 400..599) {
                        nextSource("http_${errorResponse.statusCode}")
                    }
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    if (newProgress >= 60) {
                        hideStatus()
                        cancelWebTimeout()
                    }
                }
            }
        }
        root.addView(wv, FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)

        val status = TextView(this).apply {
            setTextColor(0xFFC9D1D9.toInt())
            textSize = 18f
            setPadding(48, 48, 48, 48)
        }
        val statusParams = FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.WRAP_CONTENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
        ).apply { gravity = android.view.Gravity.CENTER }
        root.addView(status, statusParams)

        setContentView(root)
        playerView = pv
        webView = wv
        statusText = status

        val m = match
        if (m == null) {
            showError("Матч не найден")
            return
        }

        sources = m.playableSources
        if (sources.isEmpty()) {
            showError("Нет доступных источников\n\n${m.teamHome} — ${m.teamAway}")
            return
        }

        // Если пользователь выбрал конкретный источник — начинаем с него,
        // иначе с первого (prime). При ошибке — авто-фоллбэк на следующий.
        val chosenUrl = intent.getStringExtra(EXTRA_SOURCE_URL)
        sourceIndex = sources.indexOfFirst { it.url == chosenUrl }.takeIf { it >= 0 } ?: 0
        playCurrent()
    }

    private fun playCurrent() {
        if (sourceIndex !in sources.indices) {
            showError("Все источники недоступны.\nПопробуйте позже.")
            return
        }
        val src = sources[sourceIndex]
        val title = match?.let { "${it.teamHome} — ${it.teamAway}" } ?: ""
        if (src.isHls) {
            startExoPlayer(src.url, title, src)
        } else {
            startWebView(src.url, title)
        }
    }

    // Фоллбэк: пробуем следующий источник
    private fun nextSource(reason: String) {
        if (changingSource) return
        changingSource = true
        val prev = sourceIndex
        sourceIndex++
        if (sourceIndex in sources.indices) {
            cancelWebTimeout()
            webView?.stopLoading()
            releasePlayer()
            playCurrent()
            mainHandler.postDelayed({ changingSource = false }, 1500)
        } else {
            sourceIndex = prev
            changingSource = false
            showError("Источник недоступен ($reason).\nВсе источники перепробованы.")
        }
    }

    private fun cancelWebTimeout() {
        webTimeout?.let { mainHandler.removeCallbacks(it) }
        webTimeout = null
    }

    private fun startExoPlayer(url: String, title: String, src: StreamUrl) {
        showStatus("Буферизация…\n$title")
        playerView?.visibility = View.VISIBLE
        webView?.visibility = View.GONE
        try {
            val httpFactory = androidx.media3.datasource.DefaultHttpDataSource.Factory()
                .setUserAgent("Mozilla/5.0 (Linux; Android 12; SM-T220) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
                .setConnectTimeoutMs(15_000)
                .setReadTimeoutMs(20_000)
                .setAllowCrossProtocolRedirects(true)
            val p = ExoPlayer.Builder(this)
                .setMediaSourceFactory(androidx.media3.exoplayer.source.DefaultMediaSourceFactory(httpFactory))
                .build()
            player = p
            playerView?.player = p
            p.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    if (isPlaying) hideStatus()
                }
                override fun onPlayerError(error: PlaybackException) {
                    nextSource(error.errorCodeName)
                }
            })
            p.setMediaItem(MediaItem.fromUri(url))
            p.playWhenReady = true
            p.prepare()
        } catch (e: Exception) {
            nextSource(e.message ?: "exception")
        }
    }

    // Источники, которые наш бэкенд резолвит в чистый плеер —
    // тот же список, что needsProxy во фронтенде (StreamPlayer.tsx).
    private fun needsProxy(url: String): Boolean = listOf(
        "sportplus.watch", "web2.onsport365.live", "sportplustv.live", "pppdata.com",
        "sportvideodata.com", "vitalsport1.ru", "milanolive.top", "playyy.php",
        "apl431.me", "apl430.me", "apl502.me", "peerflow", "buzznews4u.com",
        "livep2p.top", "onlinestreams.ru", "playfa.st", "shd247.world",
        "dynbetray.net", "varline.store", "wideiptv.top", "vdocity.com",
        "embedded.slevel.ru", "videocdn", "red.sport", "onhockey.tv",
        "livetv903.me", "livetv.sx", "livetv904.me", "/cdnlivetv",
    ).any { it in url }

    private fun startWebView(url: String, title: String) {
        showStatus("Загрузка трансляции…\n$title")
        playerView?.visibility = View.GONE
        webView?.visibility = View.VISIBLE

        // Как на сайте: для проксируемых источников грузим не страницу
        // провайдера, а наш /api/proxy/stream — там backend вычищает
        // интерфейс и отдаёт чистый плеер.
        var finalUrl = if (needsProxy(url)) {
            val server = AppSettings.serverUrl(this).trimEnd('/')
            "$server/api/proxy/stream?url=" +
                java.net.URLEncoder.encode(url, "UTF-8")
        } else {
            url
        }
        if (url.contains("youtube.com/embed/")) {
            val sep = if (finalUrl.contains("?")) "&" else "?"
            finalUrl = finalUrl + sep + "autoplay=1&rel=0&playsinline=1"
        }
        if (url.contains("rutube.ru/play/embed/")) {
            finalUrl = finalUrl + "?autoplay=1"
        }
        webView?.loadUrl(finalUrl)
        // Если страница не дала плеер за 25 секунд — пробуем следующий источник
        cancelWebTimeout()
        val timeout = Runnable { nextSource("web_timeout") }
        webTimeout = timeout
        mainHandler.postDelayed(timeout, 25_000)
    }

    private fun showStatus(text: String) {
        statusText?.apply {
            this.text = text
            visibility = View.VISIBLE
        }
    }

    private fun hideStatus() {
        statusText?.visibility = View.GONE
    }

    private fun showError(text: String) {
        showStatus(text)
    }

    override fun onKeyDown(keyCode: Int, event: KeyEvent?): Boolean {
        val p = player
        if (p != null && playerView?.visibility == View.VISIBLE) {
            when (keyCode) {
                KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> {
                    if (p.isPlaying) p.pause() else p.play()
                    playerView?.showController()
                    return true
                }
                KeyEvent.KEYCODE_MEDIA_PLAY -> { p.play(); return true }
                KeyEvent.KEYCODE_MEDIA_PAUSE -> { p.pause(); return true }
                KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_MEDIA_REWIND -> {
                    p.seekTo((p.currentPosition - 10_000).coerceAtLeast(0))
                    playerView?.showController()
                    return true
                }
                KeyEvent.KEYCODE_DPAD_RIGHT, KeyEvent.KEYCODE_MEDIA_FAST_FORWARD -> {
                    p.seekTo(p.currentPosition + 10_000)
                    playerView?.showController()
                    return true
                }
            }
        }
        return super.onKeyDown(keyCode, event)
    }

    private fun releasePlayer() {
        player?.release()
        player = null
        playerView?.player = null
    }

    override fun onStop() {
        super.onStop()
        player?.pause()
        webView?.onPause()
    }

    override fun onResume() {
        super.onResume()
        webView?.onResume()
    }

    override fun onDestroy() {
        super.onDestroy()
        cancelWebTimeout()
        releasePlayer()
        webView?.destroy()
        webView = null
    }
}
