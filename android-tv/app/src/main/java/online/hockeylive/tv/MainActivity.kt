package online.hockeylive.tv

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString

object Theme {
    val bg = Color(0xFF0A0A0A)
    val card = Color(0xFF161616)
    val cardHover = Color(0xFF1C1C1C)
    val border = Color(0xFF222222)
    val text = Color(0xFFFFFFFF)
    val textSecondary = Color(0xFF888888)
    val textMuted = Color(0xFF555555)
    val accent = Color(0xFFE11D48)
    val accentHover = Color(0xFFF43F5E)
    val live = Color(0xFFEF4444)
}

class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContent {
            val context = LocalContext.current
            var authorized by remember { mutableStateOf(AppSettings.isAuthorized(context)) }

            // Восстановление авторизации с сервера (переустановка/очистка данных)
            LaunchedEffect(Unit) {
                if (!authorized) {
                    try {
                        val ok = ApiClient.isDeviceActivated(
                            AppSettings.serverUrl(context),
                            AppSettings.deviceId(context),
                        )
                        if (ok) {
                            AppSettings.setAuthorized(context, true)
                            authorized = true
                        }
                    } catch (_: Exception) {
                    }
                }
            }

            if (!authorized) {
                AuthScreen(
                    onActivated = {
                        AppSettings.setAuthorized(context, true)
                        authorized = true
                    },
                )
            } else {
            var matches by remember { mutableStateOf<List<Match>>(emptyList()) }
            var error by remember { mutableStateOf<String?>(null) }
            var loading by remember { mutableStateOf(true) }
            var pendingMatch by remember { mutableStateOf<Match?>(null) }
            var updateInfo by remember { mutableStateOf<AppVersionInfo?>(null) }
            var updateStatus by remember { mutableStateOf<String?>(null) }
            val scope = rememberCoroutineScope()

            LaunchedEffect(Unit) {
                while (true) {
                    try {
                        matches = ApiClient.fetchMatches(AppSettings.serverUrl(context))
                        error = null
                    } catch (e: Exception) {
                        error = "Ошибка загрузки: ${e.message}"
                    }
                    loading = false
                    delay(30_000)
                }
            }

            LaunchedEffect(Unit) {
                UpdateChecker.check(AppSettings.serverUrl(context)) { info ->
                    val currentCode = BuildConfig.VERSION_CODE
                    if (info != null && info.version_code > currentCode && info.apk_url != null) {
                        updateInfo = info
                    }
                }
            }

            HomeScreen(
                matches = matches.filter { it.isLive },
                error = error,
                loading = loading,
                onMatchClick = { match ->
                    when {
                        match.playableSources.size > 1 -> pendingMatch = match
                        match.playableSources.size == 1 ->
                            launchPlayer(context, match, match.playableSources.first())
                        match.league.equals("NHL", true) && match.status == "finished" -> {
                            val m = match
                            scope.launch {
                                val stats = runCatching {
                                    ApiClient.fetchMatchStats(
                                        AppSettings.serverUrl(context),
                                        m.teamHome,
                                        m.teamAway,
                                        m.datetimeUtc.take(10),
                                        live = false,
                                    )
                                }.getOrNull()
                                val hl = stats?.highlights?.firstOrNull()?.embedUrl
                                if (!hl.isNullOrBlank()) {
                                    context.startActivity(
                                        Intent(context, HighlightActivity::class.java)
                                            .putExtra(HighlightActivity.EXTRA_URL, hl),
                                    )
                                } else {
                                    Toast.makeText(context, "Обзор пока недоступен", Toast.LENGTH_SHORT).show()
                                }
                            }
                        }
                        match.status == "finished" ->
                            Toast.makeText(context, "Нет доступных источников", Toast.LENGTH_SHORT).show()
                        else ->
                            Toast.makeText(
                                context,
                                "Трансляция появится на главном экране в день матча",
                                Toast.LENGTH_SHORT,
                            ).show()
                    }
                },
            )

            pendingMatch?.let { m ->
                SourceChoiceDialog(
                    match = m,
                    onChoice = { source ->
                        pendingMatch = null
                        launchPlayer(context, m, source)
                    },
                    onDismiss = { pendingMatch = null },
                )
            }

            updateInfo?.let { info ->
                UpdateDialog(
                    info = info,
                    status = updateStatus,
                    onUpdate = {
                        updateStatus = "Скачиваю…"
                        UpdateChecker.downloadAndInstall(context, info.apk_url!!) { s ->
                            updateStatus = s
                        }
                    },
                    onDismiss = { updateInfo = null },
                )
            }
            }
        }
    }

    private fun launchPlayer(context: android.content.Context, match: Match, source: StreamUrl?) {
        val intent = Intent(context, PlayerActivity::class.java)
        intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
        if (source != null) intent.putExtra(PlayerActivity.EXTRA_SOURCE_URL, source.url)
        context.startActivity(intent)
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun AuthScreen(onActivated: () -> Unit) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var status by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    fun activate() {
        if (code.length != 6 || busy) return
        busy = true
        status = null
        scope.launch {
            try {
                if (ApiClient.activateCode(
                        AppSettings.serverUrl(context), code,
                        AppSettings.deviceId(context),
                    )
                ) {
                    onActivated()
                    return@launch
                }
                status = "Код не найден или уже использован"
            } catch (e: Exception) {
                status = "Нет связи с сервером: ${e.message}"
            }
            busy = false
        }
    }

    val qrImage = remember {
        try {
            val matrix = QRCodeWriter().encode(
                "https://t.me/hockeylivenotificationbot",
                BarcodeFormat.QR_CODE,
                600,
                600,
            )
            val bmp = android.graphics.Bitmap.createBitmap(
                matrix.width, matrix.height, android.graphics.Bitmap.Config.ARGB_8888,
            )
            for (x in 0 until matrix.width) {
                for (y in 0 until matrix.height) {
                    bmp.setPixel(
                        x, y,
                        if (matrix.get(x, y)) android.graphics.Color.BLACK
                        else android.graphics.Color.WHITE,
                    )
                }
            }
            bmp.asImageBitmap()
        } catch (e: Exception) {
            null
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Theme.bg)
            .padding(horizontal = 24.dp, vertical = 12.dp)
            .onPreviewKeyEvent { e ->
                if (e.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
                val kc = e.nativeKeyEvent.keyCode
                val digit = when {
                    kc in android.view.KeyEvent.KEYCODE_0..android.view.KeyEvent.KEYCODE_9 ->
                        ('0'.code + (kc - android.view.KeyEvent.KEYCODE_0)).toChar()
                    kc in android.view.KeyEvent.KEYCODE_NUMPAD_0..android.view.KeyEvent.KEYCODE_NUMPAD_9 ->
                        ('0'.code + (kc - android.view.KeyEvent.KEYCODE_NUMPAD_0)).toChar()
                    else -> null
                }
                when {
                    digit != null -> {
                        if (code.length < 6 && !busy) {
                            code += digit
                            status = null
                        }
                        true
                    }
                    kc == android.view.KeyEvent.KEYCODE_DEL -> {
                        if (code.isNotEmpty()) code = code.dropLast(1)
                        status = null
                        true
                    }
                    kc == android.view.KeyEvent.KEYCODE_ENTER ||
                        kc == android.view.KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                        activate()
                        true
                    }
                    else -> false
                }
            },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = "Активация приложения",
            color = Theme.text,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
        )
        Spacer(Modifier.height(12.dp))

        Row(
            horizontalArrangement = Arrangement.spacedBy(18.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                if (qrImage != null) {
                    Box(
                        modifier = Modifier
                            .background(Color.White)
                            .padding(6.dp),
                    ) {
                        Image(
                            bitmap = qrImage,
                            contentDescription = "QR: открыть бота в Telegram",
                            modifier = Modifier.size(112.dp),
                        )
                    }
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    text = "@hockeylivenotificationbot",
                    color = Theme.textSecondary,
                    fontSize = 12.sp,
                    textAlign = TextAlign.Center,
                    maxLines = 1,
                )
            }
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text(
                    text = "Отсканируйте QR камерой телефона",
                    color = Theme.text,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                )
                Text(
                    text = "1. В боте нажмите «Подключить ТВ»",
                    color = Theme.textSecondary,
                    fontSize = 12.sp,
                )
                Text(
                    text = "2. Оплатите активацию — придёт 6-значный код",
                    color = Theme.textSecondary,
                    fontSize = 12.sp,
                )
                Text(
                    text = "3. Введите код ниже — кнопки или цифры с пульта",
                    color = Theme.textSecondary,
                    fontSize = 12.sp,
                )
            }
        }

        Spacer(Modifier.height(14.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            repeat(6) { i ->
                Box(
                    modifier = Modifier
                        .width(46.dp)
                        .height(52.dp)
                        .background(
                            if (i == code.length) Theme.cardHover else Theme.card,
                        ),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(
                        text = if (i < code.length) code[i].toString() else "•",
                        color = Theme.text,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
        }

        Spacer(Modifier.height(12.dp))

        val rows = listOf(
            listOf("1", "2", "3"),
            listOf("4", "5", "6"),
            listOf("7", "8", "9"),
            listOf("⌫", "0", "OK"),
        )
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            rows.forEach { row ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    row.forEach { label ->
                        val isOk = label == "OK"
                        val isDel = label == "⌫"
                        Surface(
                            onClick = {
                                when {
                                    isOk -> activate()
                                    isDel -> {
                                        if (code.isNotEmpty()) code = code.dropLast(1)
                                        status = null
                                    }
                                    code.length < 6 -> {
                                        code += label
                                        status = null
                                    }
                                }
                            },
                            colors = ClickableSurfaceDefaults.colors(
                                containerColor = when {
                                    isOk -> Theme.accent
                                    isDel -> Theme.card
                                    else -> Theme.cardHover
                                },
                                focusedContainerColor = if (isOk) Theme.accentHover else Theme.accent,
                            ),
                        ) {
                            Text(
                                text = if (busy && isOk) "…" else label,
                                color = if (isOk) Color.White else Theme.text,
                                fontSize = if (isOk) 15.sp else 18.sp,
                                fontWeight = FontWeight.Bold,
                                textAlign = TextAlign.Center,
                                modifier = Modifier
                                    .width(if (isOk) 96.dp else 64.dp)
                                    .padding(vertical = 10.dp),
                            )
                        }
                    }
                }
                Spacer(Modifier.height(5.dp))
            }
        }

        Spacer(Modifier.height(8.dp))
        Text(
            text = status ?: "Кнопка OK или Enter на клавиатуре — активировать",
            color = if (status != null) Theme.accent else Theme.textMuted,
            fontSize = 13.sp,
        )
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun SourceChoiceDialog(match: Match, onChoice: (StreamUrl) -> Unit, onDismiss: () -> Unit) {
    val sources = match.playableSources
    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .background(Theme.card)
                .padding(24.dp)
                .width(380.dp),
        ) {
            Text(
                text = "${match.teamHome} — ${match.teamAway}",
                color = Theme.text,
                fontSize = 18.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                text = "Выберите источник",
                color = Theme.textSecondary,
                fontSize = 13.sp,
            )
            Spacer(Modifier.height(16.dp))
            var otherNum = 0
            sources.forEachIndexed { index, src ->
                val label = if (src.source.equals("prime", true)) {
                    "Прайм"
                } else {
                    otherNum++
                    "Источник $otherNum"
                }
                Surface(
                    onClick = { onChoice(src) },
                    colors = ClickableSurfaceDefaults.colors(
                        containerColor = Theme.cardHover,
                        focusedContainerColor = Theme.accent,
                    ),
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 10.dp, horizontal = 12.dp),
                    ) {
                        Text(
                            text = "${index + 1}.",
                            color = Theme.textSecondary,
                            fontSize = 14.sp,
                        )
                        Spacer(Modifier.width(10.dp))
                        Text(
                            text = label,
                            color = Theme.text,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
                if (index < sources.lastIndex) Spacer(Modifier.height(6.dp))
            }
            Spacer(Modifier.height(14.dp))
            Surface(
                onClick = onDismiss,
                colors = ClickableSurfaceDefaults.colors(
                    containerColor = Theme.cardHover,
                    focusedContainerColor = Theme.border,
                ),
            ) {
                Text(
                    text = "  Отмена  ",
                    color = Theme.textSecondary,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
        }
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun UpdateDialog(info: AppVersionInfo, status: String?, onUpdate: () -> Unit, onDismiss: () -> Unit) {
    Dialog(onDismissRequest = onDismiss) {
        Column(
            modifier = Modifier
                .background(Theme.card)
                .padding(24.dp)
                .width(360.dp),
        ) {
            Text(
                text = "Доступно обновление",
                color = Theme.accent,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Версия ${info.version}",
                color = Theme.text,
                fontSize = 16.sp,
            )
            if (info.notes.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = info.notes,
                    color = Theme.textSecondary,
                    fontSize = 13.sp,
                    maxLines = 5,
                )
            }
            if (status != null) {
                Spacer(Modifier.height(12.dp))
                Text(
                    text = status,
                    color = Theme.textSecondary,
                    fontSize = 13.sp,
                )
            }
            Spacer(Modifier.height(16.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Surface(
                    onClick = onUpdate,
                    colors = ClickableSurfaceDefaults.colors(
                        containerColor = Theme.accent,
                        focusedContainerColor = Theme.accentHover,
                    ),
                ) {
                    Text(
                        text = "  Обновить  ",
                        color = Color.White,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(vertical = 10.dp),
                    )
                }
                Surface(
                    onClick = onDismiss,
                    colors = ClickableSurfaceDefaults.colors(
                        containerColor = Theme.cardHover,
                        focusedContainerColor = Theme.border,
                    ),
                ) {
                    Text(
                        text = "  Позже  ",
                        color = Theme.textSecondary,
                        fontSize = 15.sp,
                        modifier = Modifier.padding(vertical = 10.dp),
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun HomeScreen(
    matches: List<Match>,
    error: String?,
    loading: Boolean,
    onMatchClick: (Match) -> Unit,
) {
    val context = LocalContext.current
    var screen by remember { mutableStateOf("home") }
    var calendarMatches by remember { mutableStateOf<List<Match>>(emptyList()) }
    var calendarLoading by remember { mutableStateOf(true) }
    var standings by remember { mutableStateOf<StandingsResponse?>(null) }
    var standingsError by remember { mutableStateOf<String?>(null) }

    LaunchedEffect(screen) {
        when (screen) {
            "calendar" -> {
                calendarLoading = true
                calendarMatches = runCatching {
                    ApiClient.fetchCalendarMatches(AppSettings.serverUrl(context))
                }.getOrDefault(emptyList())
                calendarLoading = false
            }
            "table" -> {
                standingsError = null
                standings = runCatching {
                    ApiClient.fetchStandings(AppSettings.serverUrl(context))
                }.getOrNull()
                if (standings == null) standingsError = "Ошибка загрузки таблицы"
            }
        }
    }

    val khl = matches.filter { it.league.equals("KHL", true) }
    val nhl = matches.filter { it.league.equals("NHL", true) }
    val vhl = matches.filter { it.league.equals("VHL", true) }
    val mhl = matches.filter { it.league.equals("MHL", true) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Theme.bg)
            .padding(vertical = 24.dp)
            .onPreviewKeyEvent { e ->
                if (e.type == KeyEventType.KeyDown && e.key == Key.Back && screen != "home") {
                    screen = "home"
                    true
                } else false
            },
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 32.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Image(
                painter = painterResource(R.drawable.mainlogo),
                contentDescription = "HOCKEY LIVE",
                modifier = Modifier.size(40.dp),
            )
            Spacer(Modifier.width(12.dp))
            Text(
                text = "HOCKEY LIVE",
                color = Theme.text,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.width(16.dp))
            Text(
                text = when {
                    loading -> "Загрузка…"
                    error != null -> error
                    screen == "calendar" -> "Календарь: КХЛ и НХЛ на 7 дней"
                    screen == "table" -> "Турнирная таблица КХЛ"
                    else -> "KHL · NHL · VHL · MHL"
                },
                color = Theme.textSecondary,
                fontSize = 14.sp,
            )
            Spacer(Modifier.weight(1f))
            HeaderButton("Календарь", selected = screen == "calendar") { screen = "calendar" }
            Spacer(Modifier.width(10.dp))
            HeaderButton("Таблица", selected = screen == "table") { screen = "table" }
            if (screen != "home") {
                Spacer(Modifier.width(10.dp))
                HeaderButton("◀ Главная", selected = false) { screen = "home" }
            }
        }

        Spacer(Modifier.height(20.dp))

        when (screen) {
            "calendar" -> CalendarSection(
                matches = calendarMatches,
                loading = calendarLoading,
                onMatchClick = onMatchClick,
            )
            "table" -> StandingsSection(
                data = standings,
                error = standingsError,
                loading = standings == null && standingsError == null,
            )
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(20.dp),
            ) {
                if (khl.isNotEmpty()) item { LeagueRow("КХЛ", "KHL", khl, onMatchClick) }
                if (nhl.isNotEmpty()) item { LeagueRow("НХЛ", "NHL", nhl, onMatchClick) }
                if (vhl.isNotEmpty()) item { LeagueRow("ВХЛ", "VHL", vhl, onMatchClick) }
                if (mhl.isNotEmpty()) item { LeagueRow("МХЛ", "MHL", mhl, onMatchClick) }
                if (!loading && error == null && matches.isEmpty()) {
                    item {
                        Text(
                            text = "Нет активных трансляций",
                            color = Theme.textSecondary,
                            fontSize = 16.sp,
                            modifier = Modifier.padding(horizontal = 32.dp),
                        )
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun HeaderButton(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        colors = ClickableSurfaceDefaults.colors(
            containerColor = if (selected) Theme.accent else Theme.card,
            focusedContainerColor = Theme.accentHover,
        ),
    ) {
        Text(
            text = "  $label  ",
            color = Color.White,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(vertical = 6.dp),
        )
    }
}

@Composable
fun CalendarSection(
    matches: List<Match>,
    loading: Boolean,
    onMatchClick: (Match) -> Unit,
) {
    if (loading) {
        Text(
            text = "Загрузка календаря…",
            color = Theme.textSecondary,
            fontSize = 16.sp,
            modifier = Modifier.padding(horizontal = 32.dp),
        )
        return
    }

    val zone = java.time.ZoneId.systemDefault()
    val today = java.time.LocalDate.now(zone)
    val filtered = matches.mapNotNull { m ->
        val inst = runCatching { java.time.Instant.parse(m.datetimeUtc) }.getOrNull()
            ?: return@mapNotNull null
        val d = inst.atZone(zone).toLocalDate()
        if (d < today || d >= today.plusDays(7)) null else d to m
    }.sortedBy { it.second.datetimeUtc }

    if (filtered.isEmpty()) {
        Text(
            text = "Нет матчей КХЛ и НХЛ на ближайшие 7 дней",
            color = Theme.textSecondary,
            fontSize = 16.sp,
            modifier = Modifier.padding(horizontal = 32.dp),
        )
        return
    }

    val grouped = LinkedHashMap<java.time.LocalDate, MutableList<Match>>()
    for ((d, m) in filtered) grouped.getOrPut(d) { mutableListOf() }.add(m)

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        for ((date, list) in grouped) {
            item(key = "day_$date") { CalendarDayHeader(date, today) }
            items(list, key = { "${it.league}|${it.matchUid ?: it.id}|${it.datetimeUtc}" }) { m ->
                CalendarRow(match = m, onClick = { onMatchClick(m) })
            }
        }
    }
}

@Composable
fun CalendarDayHeader(date: java.time.LocalDate, today: java.time.LocalDate) {
    val months = listOf(
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    val weekdays = listOf(
        "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье",
    )
    val md = "${date.dayOfMonth} ${months[date.monthValue - 1]}"
    val title = when (date) {
        today -> "Сегодня, $md"
        today.plusDays(1) -> "Завтра, $md"
        else -> "${weekdays[date.dayOfWeek.value - 1]}, $md"
    }
    Text(
        text = title,
        color = Theme.accent,
        fontSize = 18.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.padding(horizontal = 32.dp, vertical = 4.dp),
    )
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun CalendarRow(match: Match, onClick: () -> Unit) {
    val time = runCatching {
        java.time.Instant.parse(match.datetimeUtc)
            .atZone(java.time.ZoneId.systemDefault())
            .format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"))
    }.getOrDefault("")

    Surface(
        onClick = onClick,
        colors = ClickableSurfaceDefaults.colors(
            containerColor = Theme.card,
            focusedContainerColor = Theme.cardHover,
        ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = 1.02f),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 32.dp, vertical = 12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = time,
                color = Theme.text,
                fontSize = 17.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.width(52.dp),
            )
            LeagueLogo(match.league, height = 22.dp)
            Spacer(Modifier.width(12.dp))
            TeamLogo(match.teamHome, size = 34.dp)
            Spacer(Modifier.width(10.dp))
            Text(
                text = match.teamHome,
                color = Theme.text,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(12.dp))
            CalendarCenter(match)
            Spacer(Modifier.width(12.dp))
            Text(
                text = match.teamAway,
                color = Theme.text,
                fontSize = 15.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 1,
                textAlign = TextAlign.End,
                modifier = Modifier.weight(1f),
            )
            Spacer(Modifier.width(10.dp))
            TeamLogo(match.teamAway, size = 34.dp)
        }
    }
}

@Composable
fun CalendarCenter(match: Match) {
    when {
        match.isLive -> Row(verticalAlignment = Alignment.CenterVertically) {
            Text(text = "●", color = Theme.live, fontSize = 10.sp)
            Spacer(Modifier.width(4.dp))
            Text(
                text = "LIVE",
                color = Theme.live,
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
            )
            if (match.displayScore.isNotEmpty()) {
                Spacer(Modifier.width(8.dp))
                Text(
                    text = match.displayScore,
                    color = Theme.text,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
        match.status == "finished" && match.displayScore.isNotEmpty() -> Text(
            text = match.displayScore,
            color = Theme.textSecondary,
            fontSize = 17.sp,
            fontWeight = FontWeight.Bold,
        )
        else -> Text(text = "vs", color = Theme.textMuted, fontSize = 14.sp)
    }
}

private val khlTableCols = listOf(44.dp, 44.dp, 48.dp, 48.dp, 44.dp, 80.dp, 52.dp)

@Composable
fun StandingsSection(
    data: StandingsResponse?,
    error: String?,
    loading: Boolean,
) {
    when {
        error != null -> Text(
            text = error,
            color = Theme.textSecondary,
            fontSize = 16.sp,
            modifier = Modifier.padding(horizontal = 32.dp, vertical = 8.dp),
        )
        loading || data == null -> Text(
            text = "Загрузка таблицы…",
            color = Theme.textSecondary,
            fontSize = 16.sp,
            modifier = Modifier.padding(horizontal = 32.dp, vertical = 8.dp),
        )
        else -> {
            val confNames = mapOf(
                "Western Conference" to "Западная конференция",
                "Eastern Conference" to "Восточная конференция",
            )
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(vertical = 8.dp),
            ) {
                item(key = "title") {
                    Text(
                        text = "Турнирная таблица КХЛ",
                        color = Theme.text,
                        fontSize = 24.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(horizontal = 32.dp, vertical = 4.dp),
                    )
                }
                for (g in data.groups) {
                    item(key = "g_${g.name}") {
                        Text(
                            text = confNames[g.name] ?: g.name,
                            color = Theme.accent,
                            fontSize = 17.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(horizontal = 32.dp, vertical = 10.dp),
                        )
                    }
                    item(key = "h_${g.name}") { StandingsHeaderRow() }
                    items(g.rows, key = { "r_${g.name}_${it.position}" }) { row ->
                        StandingsRowView(row)
                    }
                }
                item(key = "foot") {
                    Text(
                        text = "Данные официального API КХЛ · сезон ${data.season}",
                        color = Theme.textMuted,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(horizontal = 32.dp, vertical = 16.dp),
                    )
                }
            }
        }
    }
}

@Composable
fun StandingsHeaderRow() {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "#",
            color = Theme.textMuted,
            fontSize = 12.sp,
            modifier = Modifier.width(34.dp),
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.width(34.dp))
        Text(
            text = "КОМАНДА",
            color = Theme.textMuted,
            fontSize = 12.sp,
            modifier = Modifier.weight(1f),
        )
        val labels = listOf("И", "В", "ВО", "ПО", "П", "Ш", "О")
        labels.forEachIndexed { i, l ->
            Text(
                text = l,
                color = Theme.textMuted,
                fontSize = 12.sp,
                modifier = Modifier.width(khlTableCols[i]),
                textAlign = TextAlign.Center,
            )
        }
    }
}

@Composable
fun StandingsRowView(row: StandingsRow) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 32.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = "${row.position}",
            color = Theme.textSecondary,
            fontSize = 14.sp,
            modifier = Modifier.width(34.dp),
            textAlign = TextAlign.Center,
        )
        TeamLogo(row.teamName, size = 26.dp)
        Spacer(Modifier.width(8.dp))
        Text(
            text = row.teamName,
            color = Theme.text,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
            maxLines = 1,
            modifier = Modifier.weight(1f),
        )
        val values = listOf(
            "${row.played}",
            "${row.wins}",
            "${row.otWins}",
            "${row.otLosses}",
            "${row.losses}",
            "${row.goalsFor}:${row.goalsAgainst}",
        )
        values.forEachIndexed { i, v ->
            Text(
                text = v,
                color = Theme.textSecondary,
                fontSize = 13.sp,
                modifier = Modifier.width(khlTableCols[i]),
                textAlign = TextAlign.Center,
            )
        }
        Text(
            text = "${row.points}",
            color = Theme.accent,
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.width(khlTableCols[6]),
            textAlign = TextAlign.Center,
        )
    }
}

@Composable
fun LeagueRow(title: String, leagueCode: String?, matches: List<Match>, onMatchClick: (Match) -> Unit) {
    Column {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(horizontal = 32.dp, vertical = 8.dp),
        ) {
            if (leagueCode != null) {
                LeagueLogo(leagueCode, height = 24.dp)
                Spacer(Modifier.width(8.dp))
            }
            Text(
                text = title,
                color = Theme.text,
                fontSize = 20.sp,
                fontWeight = FontWeight.SemiBold,
            )
        }
        LazyRow(
            contentPadding = PaddingValues(horizontal = 32.dp),
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            items(matches, key = { it.id }) { match ->
                MatchCard(match = match, onClick = { onMatchClick(match) })
            }
        }
    }
}

@OptIn(ExperimentalTvMaterial3Api::class)
@Composable
fun MatchCard(match: Match, onClick: () -> Unit) {
    Surface(
        onClick = onClick,
        colors = ClickableSurfaceDefaults.colors(
            containerColor = Theme.card,
            focusedContainerColor = Theme.cardHover,
        ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = 1.03f),
    ) {
        Column(
            modifier = Modifier
                .width(300.dp)
                .padding(16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    text = match.currentPeriod ?: match.status,
                    color = Theme.textSecondary,
                    fontSize = 12.sp,
                )
                Spacer(Modifier.weight(1f))
                if (match.isLive) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(text = "●", color = Theme.live, fontSize = 10.sp)
                        Spacer(Modifier.width(4.dp))
                        Text(
                            text = "LIVE",
                            color = Theme.live,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                TeamLogo(match.teamHome, size = 40.dp)
                Spacer(Modifier.width(10.dp))
                Text(
                    text = match.teamHome,
                    color = Theme.text,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    modifier = Modifier.weight(1f),
                )
            }
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                TeamLogo(match.teamAway, size = 40.dp)
                Spacer(Modifier.width(10.dp))
                Text(
                    text = match.teamAway,
                    color = Theme.text,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    modifier = Modifier.weight(1f),
                )
            }
            if (match.displayScore.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Text(
                    text = match.displayScore,
                    color = Theme.accent,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}
