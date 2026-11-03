package online.hockeylive.tv

import android.annotation.SuppressLint
import android.os.Bundle
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/**
 * Просмотрщик обзоров матчей:
 * — НХЛ — ролик Brightcove с nhl.com (WebView-embed);
 * — КХЛ — HLS-поток с KHL video (WebView его не проигрывает — ExoPlayer).
 */
class HighlightActivity : ComponentActivity() {

    companion object {
        const val EXTRA_URL = "url"
    }

    private var webView: WebView? = null
    private var player: ExoPlayer? = null

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val url = intent.getStringExtra(EXTRA_URL)
        if (url.isNullOrBlank()) {
            finish()
            return
        }

        if (url.contains(".m3u8", ignoreCase = true)) {
            val pv = PlayerView(this).apply {
                useController = true
                controllerShowTimeoutMs = 5000
                setShowBuffering(PlayerView.SHOW_BUFFERING_ALWAYS)
            }
            val exo = ExoPlayer.Builder(this).build()
            exo.playWhenReady = true
            exo.setMediaItem(MediaItem.fromUri(url))
            exo.addListener(object : Player.Listener {
                override fun onPlayerError(error: PlaybackException) {
                    Toast.makeText(this@HighlightActivity, "Обзор недоступен", Toast.LENGTH_SHORT).show()
                    finish()
                }
            })
            exo.prepare()
            pv.player = exo
            setContentView(pv)
            player = exo
            return
        }

        val wv = WebView(this).apply {
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true
            settings.mediaPlaybackRequiresUserGesture = false
            settings.setSupportMultipleWindows(false)
            settings.userAgentString =
                "Mozilla/5.0 (Linux; Android 12; SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            webViewClient = WebViewClient()
        }
        setContentView(wv)
        webView = wv
        wv.loadUrl(url)
    }

    override fun onPause() {
        super.onPause()
        webView?.onPause()
        player?.pause()
    }

    override fun onResume() {
        super.onResume()
        webView?.onResume()
        player?.play()
    }

    override fun onDestroy() {
        super.onDestroy()
        webView?.destroy()
        webView = null
        player?.release()
        player = null
    }
}
