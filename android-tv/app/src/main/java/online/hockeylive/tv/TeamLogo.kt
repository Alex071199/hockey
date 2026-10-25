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
        // КХЛ
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
        // НХЛ
        "Анахайм Дакс" to "Анахайм Дакс.png",
        "Баффало Сейбрз" to "Баффало Сейбрз.png",
        "Бостон Брюинз" to "Бостон Брюинз.png",
        "Ванкувер Кэнакс" to "Ванкувер Кэнакс.png",
        "Вашингтон Кэпиталз" to "Вашингтон Кэпиталз.png",
        "Вегас Голден Найтс" to "Вегас Голден Найтс.png",
        "Виннипег Джетс" to "Виннипег Джетс.png",
        "Даллас Старз" to "Даллас Старз.png",
        "Детройт Ред Уингз" to "Детройт Ред Уингз.png",
        "Калгари Флэймз" to "Калгари Флэймз.png",
        "Каролина Харрикейнз" to "Каролина Харрикейнз.png",
        "Коламбус Блю Джекетс" to "Коламбус Блю Джекетс.png",
        "Колорадо Эвеланш" to "Колорадо Эвеланш.png",
        "Лос-Анджелес Кингз" to "Лос-Анджелес Кингз.png",
        "Миннесота Уайлд" to "Миннесота Уайлд.png",
        "Монреаль Канадиенс" to "Монреаль Канадиенс.png",
        "Нью-Джерси Девилз" to "Нью-Джерси Девилз.png",
        "Нью-Йорк Айлендерс" to "Нью-Йорк Айлендерс.png",
        "Нью-Йорк Рейнджерс" to "Нью-Йорк Рейнджерс.png",
        "Нэшвилл Предаторз" to "Нэшвилл Предаторз.png",
        "Оттава Сенаторз" to "Оттава Сенаторз.png",
        "Питтсбург Пингвинз" to "Питтсбург Пингвинз.png",
        "Сан-Хосе Шаркс" to "Сан-Хосе Шаркс.png",
        "Сент-Луис Блюз" to "Сент-Луис Блюз.png",
        "Сиэтл Кракен" to "Сиэтл Кракен.png",
        "Тампа-Бэй Лайтнинг" to "Тампа-Бэй Лайтнинг.png",
        "Торонто Мейпл Лифс" to "Торонто Мейпл Лифс.png",
        "Филадельфия Флайерз" to "Филадельфия Флайерз.png",
        "Флорида Пантерз" to "Флорида Пантерз.png",
        "Чикаго Блэкхокс" to "Чикаго Блэкхокс.png",
        "Эдмонтон Ойлерз" to "Эдмонтон Ойлерз.png",
        "Юта Маммот" to "Юта Маммот.png",
        // ВХЛ
        "АКМ Тульская область" to "АКМ Тульская область.png",
        "Барс" to "Барс.png",
        "Буран" to "Буран.png",
        "Горняк-УГМК Верхняя Пышма" to "Горняк-УГМК Верхняя Пышма.png",
        "Дизель Пенза" to "Дизель Пенза.png",
        "Динамо-Алтай" to "Динамо-Алтай.png",
        "Динамо СПб" to "Динамо СПб.png",
        "Зауралье" to "Зауралье.png",
        "Звезда Москва" to "Звезда Москва.png",
        "Ижсталь" to "Ижсталь.png",
        "Калуга" to "Калуга.png",
        "Кристалл Саратов" to "Кристалл Саратов.png",
        "Магнитка Магнитогорск" to "Магнитка Магнитогорск.png",
        "Металлург Новокузнецк" to "Металлург Новокузнецк.png",
        "Молот" to "Молот.png",
        "Нефтяник" to "Нефтяник.png",
        "Норильск" to "Норильск.png",
        "Олимпия Кирово-Чепецк" to "Олимпия Кирово-Чепецк.png",
        "Омские Крылья" to "Омские Крылья.png",
        "Рубин" to "Рубин.png",
        "Рязань-ВДВ" to "Рязань-ВДВ.png",
        "СКА-ВМФ" to "СКА-ВМФ.png",
        "Сокол Красноярск" to "Сокол Красноярск.png",
        "Торос" to "Торос.png",
        "Химик Воскресенск" to "Химик Воскресенск.png",
        "ХК Тамбов" to "ХК Тамбов.png",
        "Челмет" to "Челмет.png",
        "ЦСК ВВС" to "ЦСК ВВС.png",
        "Югра" to "Югра.png",
        "Южный Урал" to "Южный Урал.png",
        // МХЛ
        "АКМ-Юниор Новомосковск" to "АКМ-Юниор Новомосковск.png",
        "Авто" to "Авто.png",
        "Академия Михайлова" to "Академия Михайлова.png",
        "Академия СКА" to "Академия СКА.png",
        "Алмаз" to "Алмаз.png",
        "Амурские Тигры" to "Амурские Тигры.png",
        "Белые Медведи" to "Белые Медведи.png",
        "Динамо-Шинник" to "Динамо-Шинник.png",
        "Ирбис" to "Ирбис.png",
        "Красная Армия" to "Красная Армия.png",
        "Красная машина Атлант" to "Красная машина Атлант.png",
        "Красная машина Юниор" to "Красная машина Юниор.png",
        "Красноярские Рыси" to "Красноярские Рыси.png",
        "Крылья Советов" to "Крылья Советов.png",
        "Кузнецкие Медведи" to "Кузнецкие Медведи.png",
        "Локо" to "Локо.png",
        "Локо-76" to "Локо-76.png",
        "МХК Атлант" to "МХК Атлант.png",
        "МХК Динамо М" to "МХК Динамо М.png",
        "МХК Динамо СПб" to "МХК Динамо СПб.png",
        "МХК Молот" to "МХК Молот.png",
        "МХК Спартак" to "МХК Спартак.png",
        "МХК Спартак МАХ" to "МХК Спартак МАХ.png",
        "Мамонты Югры" to "Мамонты Югры.png",
        "Омские Ястребы" to "Омские Ястребы.png",
        "Реактор" to "Реактор.png",
        "СКА-1946" to "СКА-1946.png",
        "Сахалинские Акулы" to "Сахалинские Акулы.png",
        "Сибирские Снайперы" to "Сибирские Снайперы.png",
        "Снежные Барсы" to "Снежные Барсы.png",
        "Спартак МАХ" to "Спартак МАХ.png",
        "Спутник Альметьевск" to "Спутник Альметьевск.png",
        "Стальные Лисы" to "Стальные Лисы.png",
        "Тайфун" to "Тайфун.png",
        "Толпар" to "Толпар.png",
        "Чайка" to "Чайка.png",
    )
    private val aliases = mapOf(
        "Динамо Москва" to "Динамо М",
        "Динамо Минск" to "Динамо Мн",
        "Шанхай Драконы" to "Шанхайские Драконы",
        "Shanghai Dragons" to "Шанхайские Драконы",
        "Амур Хабаровск" to "Амур",
        "Сочи" to "ХК Сочи",
        // ВХЛ: короткие названия с сайта лиги
        "АКМ" to "АКМ Тульская область",
        "Горняк-УГМК" to "Горняк-УГМК Верхняя Пышма",
        "Горняк" to "Горняк-УГМК Верхняя Пышма",
        "Дизель" to "Дизель Пенза",
        "Кристалл" to "Кристалл Саратов",
        "ХК Калуга" to "Калуга",
        "Звезда" to "Звезда Москва",
        "Олимпия" to "Олимпия Кирово-Чепецк",
        "Химик" to "Химик Воскресенск",
        "Магнитка" to "Магнитка Магнитогорск",
        "Тамбов" to "ХК Тамбов",
        "Сокол" to "Сокол Красноярск",
        "Динамо Санкт-Петербург" to "Динамо СПб",
        "ХК Норильск" to "Норильск",
        "Металлург" to "Металлург Новокузнецк",
        // МХЛ: варианты названий
        "АКМ-Юниор" to "АКМ-Юниор Новомосковск",
        "Спутник Ал" to "Спутник Альметьевск",
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
