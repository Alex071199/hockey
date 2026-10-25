package online.hockeylive.tv

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.KeyEvent
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.load
import coil.transform.CircleCropTransformation
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.json.Json
import online.hockeylive.tv.ace.AceRuntime
import online.hockeylive.tv.ace.AceStreamClient
import java.net.URLEncoder

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

    // Задача запуска AceStream (P2P) для текущего источника
    private var aceJob: Job? = null

    // Overlay статистики (стрелка вниз на пульте)
    private var statsRoot: FrameLayout? = null
    private var statsScroll: ScrollView? = null
    private var statsContainer: LinearLayout? = null
    private var statsVisible = false
    private var statsRefresh: Runnable? = null

    // Подсказка «стрелка вниз — статистика» (показывается один раз)
    private var hintText: TextView? = null
    private var hintShown = false

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

        // Подсказка при первом запуске трансляции
        val hint = TextView(this).apply {
            text = "▼  Стрелка вниз — статистика матча"
            setTextColor(0xFFDDDDDD.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            gravity = Gravity.CENTER
            setPadding(dp(24), dp(11), dp(24), dp(11))
            setBackgroundColor(0xCC161616.toInt())
            visibility = View.GONE
        }
        root.addView(
            hint,
            FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.WRAP_CONTENT,
                FrameLayout.LayoutParams.WRAP_CONTENT,
            ).apply {
                gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
                bottomMargin = dp(96)
            },
        )
        hintText = hint

        // Overlay статистики — поверх плеера, открывается стрелкой вниз
        val statsLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(32), dp(24), dp(32), dp(24))
        }
        val statsScroller = ScrollView(this).apply {
            isFillViewport = true
            addView(statsLayout)
        }
        val statsOverlay = FrameLayout(this).apply {
            setBackgroundColor(0xF20A0A0A.toInt())
            addView(
                statsScroller,
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT,
            )
            visibility = View.GONE
        }
        root.addView(
            statsOverlay,
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT,
        )
        statsRoot = statsOverlay
        statsScroll = statsScroller
        statsContainer = statsLayout

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
        showStatsHint()
        when {
            src.isAcestream -> startAceStream(src, title)
            src.isHls -> startExoPlayer(src.url, title, src)
            else -> startWebView(src.url, title)
        }
    }

    // AceStream: распаковка/запуск встроенного P2P-движка, затем telnet-сессия
    // и обычный ExoPlayer на локальный http-url движка.
    private fun startAceStream(src: StreamUrl, title: String) {
        playerView?.visibility = View.GONE
        webView?.visibility = View.GONE
        cancelWebTimeout()
        aceJob?.cancel()
        aceJob = lifecycleScope.launch {
            try {
                showStatus("Запуск P2P-движка…\n$title")
                withContext(Dispatchers.IO) {
                    AceRuntime.ensureStarted(this@PlayerActivity) { msg ->
                        runOnUiThread { showStatus("$msg\n$title") }
                    }
                }
                val value = src.url
                    .substringAfter("://")
                    .substringBefore("?")
                    .substringBefore("/")
                    .trim()
                val url = AceStreamClient.startSmart(value) { msg ->
                    runOnUiThread { showStatus("$msg\n$title") }
                }
                startExoPlayer(url, title, src)
            } catch (e: Exception) {
                runCatching { AceStreamClient.stop() }
                nextSource("ace ${e.message?.take(50) ?: "error"}")
            }
        }
    }

    // Фоллбэк: пробуем следующий источник
    private fun nextSource(reason: String) {
        if (changingSource) return
        changingSource = true
        val prev = sourceIndex
        sourceIndex++
        if (sourceIndex in sources.indices) {
            val prevAce = sources[prev].isAcestream
            if (prevAce && !sources[sourceIndex].isAcestream) {
                AceStreamClient.stopAsync()
            }
            aceJob?.cancel()
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
        // embed youtube/rutube backend резолвит в чистый HLS/mp4-плеер:
        // системный WebView на ТВ их embed не воспроизводит
        "youtube.com/embed", "rutube.ru/play/embed",
    ).any { it in url }

    private fun startWebView(url: String, title: String) {
        showStatus("Загрузка трансляции…\n$title")
        playerView?.visibility = View.GONE
        webView?.visibility = View.VISIBLE

        // Как на сайте: для проксируемых источников грузим не страницу
        // провайдера, а наш /api/proxy/stream — там backend вычищает
        // интерфейс и отдаёт чистый плеер.
        val proxied = needsProxy(url)
        var finalUrl = if (proxied) {
            val server = AppSettings.serverUrl(this).trimEnd('/')
            "$server/api/proxy/stream?url=" +
                java.net.URLEncoder.encode(url, "UTF-8")
        } else {
            url
        }
        if (!proxied && url.contains("youtube.com/embed/")) {
            val sep = if (finalUrl.contains("?")) "&" else "?"
            finalUrl = finalUrl + sep + "autoplay=1&rel=0&playsinline=1"
        }
        if (!proxied && url.contains("rutube.ru/play/embed/")) {
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

    // ---------- Статистика матча (стрелка вниз на пульте) ----------

    private fun dp(v: Int): Int =
        (v * resources.displayMetrics.density).toInt()

    private fun showStatsHint() {
        if (hintShown) return
        hintShown = true
        val h = hintText ?: return
        h.visibility = View.VISIBLE
        h.alpha = 0f
        h.animate().alpha(1f).setDuration(350).start()
        h.postDelayed({
            h.animate().alpha(0f).setDuration(400)
                .withEndAction { h.visibility = View.GONE }
                .start()
        }, 6000)
    }

    private fun openStats() {
        val m = match ?: return
        statsVisible = true
        statsRoot?.visibility = View.VISIBLE
        statsScroll?.scrollTo(0, 0)
        renderMessage("Загрузка статистики…")
        loadStats()

        statsRefresh?.let { mainHandler.removeCallbacks(it) }
        if (m.isLive) {
            val r = object : Runnable {
                override fun run() {
                    if (statsVisible) {
                        loadStats()
                        mainHandler.postDelayed(this, 60_000)
                    }
                }
            }
            statsRefresh = r
            mainHandler.postDelayed(r, 60_000)
        }
    }

    private fun closeStats() {
        statsVisible = false
        statsRoot?.visibility = View.GONE
        statsRefresh?.let { mainHandler.removeCallbacks(it) }
        statsRefresh = null
    }

    private fun loadStats() {
        val m = match ?: return
        lifecycleScope.launch {
            val server = AppSettings.serverUrl(this@PlayerActivity)
            val stats = ApiClient.fetchMatchStats(
                server, m.teamHome, m.teamAway, m.datetimeUtc.take(10), live = m.isLive,
            )
            if (!statsVisible) return@launch
            if (stats == null) {
                renderMessage("Статистика недоступна\nдля этого матча")
            } else {
                renderStats(stats)
            }
        }
    }

    private fun renderMessage(text: String) {
        val c = statsContainer ?: return
        c.removeAllViews()
        c.addView(
            TextView(this).apply {
                this.text = text
                setTextColor(0xFF888888.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                gravity = Gravity.CENTER
                setPadding(0, dp(80), 0, 0)
            },
        )
    }

    private fun sectionTitle(text: String) {
        statsContainer?.addView(
            TextView(this).apply {
                this.text = text.uppercase()
                setTextColor(0xFFE11D48.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                typeface = Typeface.DEFAULT_BOLD
                letterSpacing = 0.06f
                setPadding(0, dp(26), 0, dp(10))
            },
        )
    }

    private fun statRow(label: String, home: Int, away: Int) {
        val c = statsContainer ?: return

        fun value(v: Int, gravity: Int) = TextView(this).apply {
            text = v.toString()
            setTextColor(0xFFFFFFFF.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 17f)
            typeface = Typeface.DEFAULT_BOLD
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            this.gravity = gravity
        }

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(8), 0, 0)
        }
        row.addView(value(home, Gravity.END))
        row.addView(
            TextView(this).apply {
                text = label.uppercase()
                setTextColor(0xFF888888.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
                gravity = Gravity.CENTER
                layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.6f)
                setPadding(dp(14), 0, dp(14), 0)
            },
        )
        row.addView(value(away, Gravity.START))
        c.addView(row)

        // Двухцветная полоса пропорций, как на сайте
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(4),
            ).apply { topMargin = dp(5) }
        }
        fun seg(w: Int, color: Int) = View(this).apply {
            setBackgroundColor(color)
            layoutParams = LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.MATCH_PARENT,
                if (w > 0) w.toFloat() else 0.01f,
            )
        }
        bar.addView(seg(home, 0xFFE11D48.toInt()))
        bar.addView(seg(away, 0xFF3A3A3A.toInt()))
        c.addView(bar)
    }

    private fun renderStats(s: MatchStatsResponse) {
        val c = statsContainer ?: return
        c.removeAllViews()
        val info = s.match

        c.addView(
            TextView(this).apply {
                text = "${info?.home ?: ""}  ${info?.scoreHome ?: 0} : ${info?.scoreAway ?: 0}  ${info?.away ?: ""}"
                setTextColor(0xFFFFFFFF.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 22f)
                typeface = Typeface.DEFAULT_BOLD
                gravity = Gravity.CENTER
            },
        )

        val p = s.periods
        val periodLine = listOfNotNull(
            listOfNotNull(p?.first, p?.second, p?.third)
                .filter { !it.isNullOrBlank() }
                .joinToString("  ·  ")
                .ifBlank { null },
            p?.overtime?.takeIf { it.isNotBlank() }?.let { "ОТ: $it" },
            p?.penalties?.takeIf { it.isNotBlank() }?.let { "Б: $it" },
        ).joinToString("  ·  ")
        if (periodLine.isNotBlank()) {
            c.addView(
                TextView(this).apply {
                    text = periodLine
                    setTextColor(0xFF888888.toInt())
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
                    gravity = Gravity.CENTER
                    setPadding(0, dp(6), 0, 0)
                },
            )
        }

        // Обзор матча (НХЛ — ролики Brightcove, как на сайте)
        val hlItems = s.highlights.filter { it.embedUrl.isNotBlank() }
        if (hlItems.isNotEmpty()) {
            sectionTitle("Обзор матча")
            for (h in hlItems) {
                val label = h.title?.takeIf { t -> t.isNotBlank() } ?: "Смотреть обзор"
                c.addView(
                    TextView(this).apply {
                        text = "▶  $label"
                        setTextColor(0xFFFFFFFF.toInt())
                        setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
                        typeface = Typeface.DEFAULT_BOLD
                        gravity = Gravity.CENTER_VERTICAL
                        isFocusable = true
                        isClickable = true
                        setPadding(dp(18), dp(14), dp(18), dp(14))
                        setBackgroundColor(0xFFE11D48.toInt())
                        layoutParams = LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            LinearLayout.LayoutParams.WRAP_CONTENT,
                        ).apply { topMargin = dp(8) }
                        setOnClickListener {
                            startActivity(
                                Intent(this@PlayerActivity, HighlightActivity::class.java)
                                    .putExtra(HighlightActivity.EXTRA_URL, h.embedUrl),
                            )
                        }
                    },
                )
            }
        }

        val homeId = info?.homeTeamId ?: 0
        // Куда класть строку: если id команды не пришёл (0) — определяем по ФИО
        // из составов, иначе удаления/голы с team_id=0 уезжали в чужую колонку.
        val homeNames = (s.rosters?.home ?: emptyList())
            .mapNotNull { p -> p.name.trim().lowercase().takeIf { it.isNotEmpty() } }
            .toSet()
        val awayNames = (s.rosters?.away ?: emptyList())
            .mapNotNull { p -> p.name.trim().lowercase().takeIf { it.isNotEmpty() } }
            .toSet()
        fun isHomeSide(teamId: Int, name: String): Boolean {
            if (homeId != 0 && teamId != 0) return teamId == homeId
            val n = name.trim().lowercase()
            if (n.isNotEmpty()) {
                if (n in homeNames && n !in awayNames) return true
                if (n in awayNames && n !in homeNames) return false
            }
            return teamId == homeId
        }
        val serverBase = AppSettings.serverUrl(this).trimEnd('/')
        if (s.goals.isNotEmpty()) {
            sectionTitle("Авторы шайб")
            val images = HashMap<String, String?>()
            for (pl in (s.rosters?.home ?: emptyList()) + (s.rosters?.away ?: emptyList())) {
                if (pl.image != null) images[pl.name] = pl.image
            }
            c.addView(teamsHeader(info?.home ?: "Домашняя", info?.away ?: "Гостевая"))
            val colHome = goalColumn()
            val colAway = goalColumn()
            for (g in s.goals) {
                val target = if (isHomeSide(g.teamId, g.scorer)) colHome else colAway
                target.addView(goalRow(g, images, serverBase))
            }
            if (colHome.childCount == 0) colHome.addView(emptyColMarker())
            if (colAway.childCount == 0) colAway.addView(emptyColMarker())
            c.addView(twoColumns(colHome, colAway))
        }

        val hs = s.teamStats?.home
        val asAway = s.teamStats?.away
        if (hs != null && asAway != null) {
            sectionTitle("Статистика")
            statRow("Броски", hs.shots, asAway.shots)
            statRow("Вбрасывания", hs.faceoffsWon, asAway.faceoffsWon)
            statRow("Большинство", hs.ppg, asAway.ppg)
            statRow("Меньшинство", hs.shg, asAway.shg)
            statRow("Штрафные минуты", hs.pim, asAway.pim)
            statRow("Входы в зону", hs.zoneEntries, asAway.zoneEntries)
            val pcH = hs.puckControl
            val pcA = asAway.puckControl
            if (pcH != null && pcA != null) {
                statRow("Владение шайбой %", pcH.toInt(), pcA.toInt())
            }
        }

        if (s.penalties.isNotEmpty()) {
            sectionTitle("Удаления")
            c.addView(teamsHeader(info?.home ?: "Домашняя", info?.away ?: "Гостевая"))
            val colHome = goalColumn()
            val colAway = goalColumn()
            for (pen in s.penalties) {
                val target = if (isHomeSide(pen.teamId, pen.player)) colHome else colAway
                target.addView(penaltyRow(pen))
            }
            if (colHome.childCount == 0) colHome.addView(emptyColMarker())
            if (colAway.childCount == 0) colAway.addView(emptyColMarker())
            c.addView(twoColumns(colHome, colAway))
        }

        c.addView(
            TextView(this).apply {
                text = "Данные KHL · обновляется автоматически"
                setTextColor(0xFF555555.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                gravity = Gravity.CENTER
                setPadding(0, dp(30), 0, dp(10))
            },
        )
    }

    private fun teamsHeader(left: String, right: String): LinearLayout {
        fun head(name: String) = TextView(this).apply {
            text = name
            setTextColor(0xFFFFFFFF.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
            typeface = Typeface.DEFAULT_BOLD
            gravity = Gravity.CENTER
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
            setPadding(0, 0, 0, dp(8))
        }
        return LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(head(left))
            addView(head(right))
        }
    }

    private fun goalColumn() = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
    }

    private fun twoColumns(left: View, right: View): LinearLayout =
        LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            addView(left)
            addView(
                View(this@PlayerActivity).apply {
                    setBackgroundColor(0xFF222222.toInt())
                    layoutParams = LinearLayout.LayoutParams(dp(1), LinearLayout.LayoutParams.MATCH_PARENT)
                        .apply { setMargins(dp(8), 0, dp(8), 0) }
                },
            )
            addView(right)
        }

    private fun emptyColMarker() = TextView(this).apply {
        text = "—"
        setTextColor(0xFF555555.toInt())
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
        gravity = Gravity.CENTER
        setPadding(0, dp(8), 0, dp(8))
    }

    private fun goalRow(g: StatGoal, images: Map<String, String?>, serverBase: String): View {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(0, dp(4), 0, dp(4))
        }
        val photoUrl = images[g.scorer]?.let {
            "$serverBase/api/proxy/player-photo?url=${URLEncoder.encode(it, "UTF-8")}"
        }
        row.addView(
            ImageView(this).apply {
                layoutParams = LinearLayout.LayoutParams(dp(40), dp(40))
                    .apply { marginEnd = dp(10) }
                scaleType = ImageView.ScaleType.CENTER_CROP
                setBackgroundColor(0xFF222222.toInt())
                load(photoUrl) {
                    transformations(CircleCropTransformation())
                }
            },
        )
        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f,
            )
        }
        val meta = buildString {
            g.time?.takeIf { it.isNotBlank() }?.let { append(it) }
            g.score?.takeIf { it.isNotBlank() }?.let {
                if (isNotEmpty()) append("  ·  ")
                append(it)
            }
            if (g.period in 1..3) {
                if (isNotEmpty()) append("  ·  ")
                append("${g.period} период")
            }
        }
        if (meta.isNotBlank()) {
            col.addView(
                TextView(this).apply {
                    text = meta
                    setTextColor(0xFF888888.toInt())
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                },
            )
        }
        col.addView(
            TextView(this).apply {
                text = g.scorer
                setTextColor(0xFFFFFFFF.toInt())
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 15f)
                typeface = Typeface.DEFAULT_BOLD
            },
        )
        val assists = g.assistants.filter { it.isNotBlank() }
        if (assists.isNotEmpty()) {
            col.addView(
                TextView(this).apply {
                    text = "Ассист: ${assists.joinToString(", ")}"
                    setTextColor(0xFF888888.toInt())
                    setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                    setPadding(0, dp(1), 0, 0)
                },
            )
        }
        row.addView(col)
        return row
    }

    private fun penaltyRow(pen: StatPenalty): View =
        TextView(this).apply {
            text = buildString {
                pen.time?.takeIf { it.isNotBlank() }?.let { append(it) }
                append(" · ${pen.minutes} мин")
                if (pen.reason.isNotBlank()) append(" · ${pen.reason}")
                if (pen.player.isNotBlank()) append(" — ${pen.player}")
            }
            setTextColor(0xFFCCCCCC.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setPadding(0, dp(4), 0, dp(4))
        }

    // Клавиши перехватываем ДО view hierarchy: WebView на livetv-источниках
    // съедает стрелки, если ждать onKeyDown (views получают событие первыми).
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        if (event.action == KeyEvent.ACTION_DOWN && event.repeatCount == 0) {
            if (statsVisible) {
                when (event.keyCode) {
                    KeyEvent.KEYCODE_BACK -> {
                        closeStats()
                        return true
                    }
                    KeyEvent.KEYCODE_DPAD_DOWN -> {
                        statsScroll?.smoothScrollBy(0, dp(320))
                        return true
                    }
                    KeyEvent.KEYCODE_DPAD_UP -> {
                        val s = statsScroll
                        if (s != null && s.scrollY <= 0) closeStats()
                        else s?.smoothScrollBy(0, -dp(320))
                        return true
                    }
                }
            } else if (
                event.keyCode == KeyEvent.KEYCODE_DPAD_DOWN &&
                match != null &&
                playerView?.isControllerFullyVisible != true
            ) {
                openStats()
                return true
            }
        }
        return super.dispatchKeyEvent(event)
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
        aceJob?.cancel()
        AceStreamClient.stopAsync()
        releasePlayer()
        webView?.destroy()
        webView = null
    }
}
