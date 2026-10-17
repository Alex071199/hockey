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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

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
            visibility = View.GONE
            webViewClient = object : WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = false
                override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                    hideStatus()
                }
            }
            webChromeClient = object : WebChromeClient() {
                override fun onProgressChanged(view: WebView?, newProgress: Int) {
                    if (newProgress >= 60) hideStatus()
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
        val prev = sourceIndex
        sourceIndex++
        if (sourceIndex in sources.indices) {
            releasePlayer()
            playCurrent()
        } else {
            sourceIndex = prev
            showError("Источник недоступен ($reason).\nВсе источники перепробованы.")
        }
    }

    private fun startExoPlayer(url: String, title: String, src: StreamUrl) {
        showStatus("Буферизация…\n$title")
        playerView?.visibility = View.VISIBLE
        webView?.visibility = View.GONE
        try {
            val p = ExoPlayer.Builder(this).build()
            player = p
            playerView?.player = p
            p.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    if (isPlaying) hideStatus()
                }
                override fun onPlayerError(error: PlaybackException) {
                    // Пробуем следующий источник вместо ошибки
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

    private fun startWebView(url: String, title: String) {
        showStatus("Загрузка трансляции…\n$title")
        playerView?.visibility = View.GONE
        webView?.visibility = View.VISIBLE
        var finalUrl = url
        if (url.contains("youtube.com/embed/")) {
            val sep = if (url.contains("?")) "&" else "?"
            finalUrl = url + sep + "autoplay=1&rel=0&playsinline=1"
        }
        if (url.contains("rutube.ru/play/embed/")) {
            finalUrl = url + "?autoplay=1"
        }
        webView?.loadUrl(finalUrl)
        statusText?.postDelayed({ hideStatus() }, 15000)
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
        releasePlayer()
        webView?.destroy()
        webView = null
    }
}
