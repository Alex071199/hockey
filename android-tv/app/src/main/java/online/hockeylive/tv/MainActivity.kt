package online.hockeylive.tv

import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import kotlinx.coroutines.delay
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
        setContent {
            val context = LocalContext.current
            var matches by remember { mutableStateOf<List<Match>>(emptyList()) }
            var error by remember { mutableStateOf<String?>(null) }
            var loading by remember { mutableStateOf(true) }
            var pendingMatch by remember { mutableStateOf<Match?>(null) }
            var updateInfo by remember { mutableStateOf<AppVersionInfo?>(null) }
            var updateStatus by remember { mutableStateOf<String?>(null) }

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
                        match.playableSources.size == 1 -> launchPlayer(context, match, match.playableSources.first())
                        else -> Toast.makeText(context, "Нет доступных источников", Toast.LENGTH_SHORT).show()
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

    private fun launchPlayer(context: android.content.Context, match: Match, source: StreamUrl?) {
        val intent = Intent(context, PlayerActivity::class.java)
        intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
        if (source != null) intent.putExtra(PlayerActivity.EXTRA_SOURCE_URL, source.url)
        context.startActivity(intent)
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
            sources.forEachIndexed { index, src ->
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
                            text = src.displayName,
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
    val khl = matches.filter { it.league.equals("KHL", true) }
    val nhl = matches.filter { it.league.equals("NHL", true) }
    val vhl = matches.filter { it.league.equals("VHL", true) }
    val mhl = matches.filter { it.league.equals("MHL", true) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Theme.bg)
            .padding(vertical = 24.dp),
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
                    else -> "KHL · NHL · VHL · MHL"
                },
                color = Theme.textSecondary,
                fontSize = 14.sp,
            )
        }

        Spacer(Modifier.height(20.dp))

        LazyColumn(
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
