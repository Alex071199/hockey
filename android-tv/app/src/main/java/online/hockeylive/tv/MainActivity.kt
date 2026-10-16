package online.hockeylive.tv

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.tv.material3.ClickableSurfaceDefaults
import androidx.tv.material3.ExperimentalTvMaterial3Api
import androidx.tv.material3.Surface
import androidx.tv.material3.Text
import kotlinx.coroutines.delay
import kotlinx.serialization.encodeToString

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
                    delay(60_000)
                }
            }

            HomeScreen(
                matches = matches,
                error = error,
                loading = loading,
                onMatchClick = { match ->
                    val intent = Intent(context, PlayerActivity::class.java)
                    intent.putExtra(PlayerActivity.EXTRA_MATCH_JSON, JsonFormat.json.encodeToString(match))
                    context.startActivity(intent)
                },
                onSettingsClick = {
                    val input = android.widget.EditText(context).apply {
                        setText(AppSettings.serverUrl(context))
                        hint = "https://..."
                    }
                    android.app.AlertDialog.Builder(context)
                        .setTitle("Адрес сервера")
                        .setView(input)
                        .setPositiveButton("Сохранить") { _, _ ->
                            AppSettings.setServerUrl(context, input.text.toString())
                            Toast.makeText(context, "Сохранено", Toast.LENGTH_SHORT).show()
                        }
                        .setNegativeButton("Отмена", null)
                        .show()
                },
            )
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
    onSettingsClick: () -> Unit,
) {
    val khl = matches.filter { it.league.equals("KHL", true) }
    val nhl = matches.filter { it.league.equals("NHL", true) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color(0xFF0D1117))
            .padding(vertical = 24.dp),
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 32.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "HOCKEY LIVE",
                color = Color(0xFF4AC7FF),
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
                color = Color(0xFF8B98A5),
                fontSize = 14.sp,
            )
            Spacer(Modifier.weight(1f))
            Surface(
                onClick = onSettingsClick,
                colors = ClickableSurfaceDefaults.colors(
                    containerColor = Color(0xFF161B22),
                    focusedContainerColor = Color(0xFF1F2937),
                ),
            ) {
                Text(
                    text = "  Настройки  ",
                    color = Color(0xFFC9D1D9),
                    fontSize = 14.sp,
                    modifier = Modifier.padding(vertical = 8.dp),
                )
            }
        }

        Spacer(Modifier.height(20.dp))

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp),
        ) {
            if (khl.isNotEmpty()) {
                item { LeagueRow("КХЛ", khl, onMatchClick) }
            }
            if (nhl.isNotEmpty()) {
                item { LeagueRow("НХЛ", nhl, onMatchClick) }
            }
            if (!loading && error == null && matches.isEmpty()) {
                item {
                    Text(
                        text = "Матчей пока нет",
                        color = Color(0xFF8B98A5),
                        fontSize = 16.sp,
                        modifier = Modifier.padding(horizontal = 32.dp),
                    )
                }
            }
        }
    }
}

@Composable
fun LeagueRow(title: String, matches: List<Match>, onMatchClick: (Match) -> Unit) {
    Column {
        Text(
            text = title,
            color = Color(0xFFC9D1D9),
            fontSize = 20.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(horizontal = 32.dp, vertical = 8.dp),
        )
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
            containerColor = Color(0xFF161B22),
            focusedContainerColor = Color(0xFF253040),
        ),
        scale = ClickableSurfaceDefaults.scale(focusedScale = 1.05f),
    ) {
        Column(
            modifier = Modifier
                .width(280.dp)
                .padding(16.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (match.isLive) {
                    Text(
                        text = " LIVE ",
                        color = Color.White,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier
                            .background(Color(0xFFD6293E))
                            .padding(horizontal = 6.dp, vertical = 2.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text(
                    text = match.currentPeriod ?: match.status,
                    color = Color(0xFF8B98A5),
                    fontSize = 12.sp,
                )
            }
            Spacer(Modifier.height(10.dp))
            Text(
                text = match.teamHome,
                color = Color(0xFFE8EDF3),
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
            )
            Text(
                text = match.teamAway,
                color = Color(0xFFE8EDF3),
                fontSize = 16.sp,
                fontWeight = FontWeight.Medium,
                maxLines = 2,
            )
            if (match.displayScore.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = match.displayScore,
                    color = Color(0xFF4AC7FF),
                    fontSize = 22.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                if (match.primeUrl != null) {
                    SourceBadge("PRIME", Color(0xFF238636))
                }
                if (match.aceHashes.isNotEmpty()) {
                    SourceBadge("ACE", Color(0xFF8957E5))
                }
            }
        }
    }
}

@Composable
fun SourceBadge(text: String, color: Color) {
    Text(
        text = text,
        color = Color.White,
        fontSize = 11.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier
            .background(color)
            .padding(horizontal = 8.dp, vertical = 3.dp),
    )
}
