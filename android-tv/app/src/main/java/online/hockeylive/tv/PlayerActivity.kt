package online.hockeylive.tv

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.KeyEvent
import android.view.View
import android.widget.FrameLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json

class PlayerActivity : ComponentActivity() {

    companion object {
        const val EXTRA_MATCH_JSON = "match_json"
        const val EXTRA_FORCE_ACE = "force_ace"
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var statusText: TextView? = null
    private var engineManager: AceEngineManager? = null
    private var match: Match? = null

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
        }
        root.addView(pv, FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT)

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
        statusText = status

        val m = match
        if (m == null) {
            showError("Матч не найден")
            return
        }

        val title = "${m.teamHome} — ${m.teamAway}"
        val forceAce = intent.getStringExtra(EXTRA_FORCE_ACE)
        val aceHash = m.aceHashes.firstOrNull()
        val prime = m.primeUrl

        when {
            forceAce != null -> startAce(forceAce, title)
            prime != null -> playUrl(prime, title)
            aceHash != null -> startAce(aceHash, title)
            else -> showError("Нет доступных источников\n\n$title")
        }
    }

    private fun startAce(hash: String, title: String) {
        showStatus("Запуск движка Ace Stream…\n$title")
        try {
            val manager = AceEngineManager(this)
            engineManager = manager
            manager.start { result ->
                when (result) {
                    is AceEngineManager.Result.Ready -> {
                        val url = "http://127.0.0.1:${result.httpPort}/ace/manifest.m3u8?id=$hash"
                        playUrl(url, title)
                    }
                    is AceEngineManager.Result.EngineMissing -> {
                        try {
                            startActivity(Intent(this, EngineSetupActivity::class.java))
                        } catch (_: Exception) {}
                        showError("Движок Ace Stream не установлен.\nУстановите его и вернитесь к матчу.")
                    }
                    is AceEngineManager.Result.Failed -> {
                        showError("Ошибка Ace Stream:\n${result.message}")
                    }
                }
            }
        } catch (e: Exception) {
            showError("Ошибка: ${e.message}")
        }
    }

    private fun playUrl(url: String, title: String) {
        showStatus("Буферизация…\n$title")
        try {
            val p = ExoPlayer.Builder(this).build()
            player = p
            playerView?.player = p
            p.addListener(object : Player.Listener {
                override fun onIsPlayingChanged(isPlaying: Boolean) {
                    if (isPlaying) hideStatus()
                }
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                    showError("Ошибка воспроизведения:\n${error.errorCodeName}")
                }
            })
            p.setMediaItem(MediaItem.fromUri(url))
            p.playWhenReady = true
            p.prepare()
        } catch (e: Exception) {
            showError("Ошибка: ${e.message}")
        }
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
        if (p != null) {
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

    override fun onStop() {
        super.onStop()
        player?.pause()
    }

    override fun onDestroy() {
        super.onDestroy()
        player?.release()
        player = null
        engineManager?.release()
        engineManager = null
    }
}
