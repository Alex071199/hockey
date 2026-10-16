package online.hockeylive.tv

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import android.graphics.BitmapFactory

object TeamLogos {
    private val map = mapOf(
        "Автомобилист" to "АВТОМОБИЛИСТ.png",
        "Авангард" to "АВАНГАРД.png",
        "Адмирал" to "АДМИРАЛ.png",
        "Ак Барс" to "АК БАРС.png",
        "Амур" to "АМУР.png",
        "Барыс" to "БАРЫС.png",
        "Динамо М" to "ДИНАМО М.png",
        "Динамо Минск" to "ДИНАМО МН.png",
        "Динамо Мн" to "ДИНАМО МН.png",
        "Шанхайские Драконы" to "ДРАКОНЫ.png",
        "Драконы" to "ДРАКОНЫ.png",
        "Лада" to "ЛАДА.png",
        "Локомотив" to "ЛОКОМОТИВ.png",
        "Металлург Мг" to "МЕТАЛЛУРГ МГ.png",
        "Нефтехимик" to "НЕФТЕХИМИК.png",
        "Салават Юлаев" to "САЛАВАТ ЮЛАЕВ.png",
        "Северсталь" to "СЕВЕРСТАЛЬ.png",
        "Сибирь" to "СИБИРЬ.png",
        "СКА" to "СКА.png",
        "Спартак" to "СПАРТАК.png",
        "Трактор" to "ТРАКТОР.png",
        "Торпедо" to "ТОРПЕДО.png",
        "ХК Сочи" to "ХК СОЧИ.png",
        "ЦСКА" to "ЦСКА.png",
    )
    private val aliases = mapOf(
        "Динамо Москва" to "Динамо М",
        "Динамо Минск" to "Динамо Мн",
        "Шанхай Драконы" to "Шанхайские Драконы",
        "Shanghai Dragons" to "Шанхайские Драконы",
        "Амур Хабаровск" to "Амур",
        "Сочи" to "ХК Сочи",
    )
    fun fileFor(teamName: String): String? {
        map[teamName]?.let { return it }
        aliases[teamName]?.let { a -> map[a]?.let { return it } }
        return null
    }
}

@Composable
fun TeamLogo(teamName: String, size: Dp = 48.dp) {
    val file = TeamLogos.fileFor(teamName) ?: return
    val context = LocalContext.current
    var bitmap by remember(teamName) { mutableStateOf<android.graphics.Bitmap?>(null) }
    LaunchedEffect(teamName) {
        bitmap = withContext(Dispatchers.IO) {
            try {
                context.assets.open("logos/$file").use { BitmapFactory.decodeStream(it) }
            } catch (e: Exception) { null }
        }
    }
    val bmp = bitmap
    if (bmp != null) {
        Image(
            bitmap = bmp.asImageBitmap(),
            contentDescription = teamName,
            modifier = Modifier.size(size),
            contentScale = ContentScale.Fit,
        )
    } else {
        Box(
            modifier = Modifier
                .size(size)
                .background(Color(0xFF1C1C1C)),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                text = teamName.take(1),
                color = Color(0xFF888888),
                fontSize = (size.value / 2.2f).sp,
                fontWeight = FontWeight.Bold,
            )
        }
    }
}

@Composable
fun LeagueLogo(league: String, height: Dp = 24.dp) {
    val resId = when (league.uppercase()) {
        "KHL" -> R.drawable.league_khl
        "NHL" -> R.drawable.league_nhl
        "VHL" -> R.drawable.league_vhl
        "MHL" -> R.drawable.league_mhl
        else -> return
    }
    Image(
        painter = androidx.compose.ui.res.painterResource(resId),
        contentDescription = league,
        modifier = Modifier
            .size(height)
            .padding(end = 4.dp),
        contentScale = ContentScale.Fit,
    )
}
