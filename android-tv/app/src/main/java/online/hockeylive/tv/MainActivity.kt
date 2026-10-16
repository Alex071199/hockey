package online.hockeylive.tv

import android.app.Activity
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

            HomeScreen(
                matches = matches.filter { it.isLive },
                error = error,
                loading = loading,
                onMatchClick = { match -> openMatch(context, match) },
            )
        }
    }

    private fun openMatch(context: android.content.Context, match: Match) {
        val aceHash = match.aceHashes.firstOrNull()
        val prime = match.primeUrl
        val title = "${match.teamHome} — ${match.teamAway}"

        when {
            aceHash != null && prime != null -> {
                val options = arrayOf("Основной", "AceStream")
                android.app.AlertDialog.Builder(context)
                    .setTitle(title)
                    .setItems(options) { _, which ->
                        val intent = Intent(context, PlayerActivity::class.java)
                        intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
                        if (which == 1) {
                            intent.putExtra(PlayerActivity.EXTRA_FORCE_ACE, aceHash)
                        }
                        context.startActivity(intent)
                    }
                    .setNegativeButton("Отмена", null)
                    .show()
            }
            aceHash != null -> {
                val intent = Intent(context, PlayerActivity::class.java)
                intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
                context.startActivity(intent)
            }
            prime != null -> {
                val intent = Intent(context, PlayerActivity::class.java)
                intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
                context.startActivity(intent)
            }
            else -> {
                Toast.makeText(context, "Нет доступных источников", Toast.LENGTH_SHORT).show()
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
    val other = matches.filter { !it.league.equals("KHL", true) && !it.league.equals("NHL", true) }

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
                    else -> "KHL · NHL"
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
            if (khl.isNotEmpty()) {
                item { LeagueRow("КХЛ", "KHL", khl, onMatchClick) }
            }
            if (nhl.isNotEmpty()) {
                item { LeagueRow("НХЛ", "NHL", nhl, onMatchClick) }
            }
            if (other.isNotEmpty()) {
                item { LeagueRow("Другие лиги", null, other, onMatchClick) }
            }
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
                        Text(
                            text = "●",
                            color = Theme.live,
                            fontSize = 10.sp,
                        )
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
