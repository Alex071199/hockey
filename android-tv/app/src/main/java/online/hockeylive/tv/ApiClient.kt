package online.hockeylive.tv

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

object ApiClient {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val listAdapter = ListSerializer(Match.serializer())

    suspend fun fetchMatches(server: String): List<Match> = withContext(Dispatchers.IO) {
        val req = Request.Builder()
            .url("$server/api/schedule")
            .header("Accept", "application/json")
            .build()
        http.newCall(req).execute().use { resp ->
            if (resp.isSuccessful) {
                val body = resp.body?.string()
                if (body != null) JsonFormat.json.decodeFromString(listAdapter, body) else emptyList()
            } else {
                emptyList()
            }
        }
    }

    suspend fun fetchMatchStats(
        server: String,
        home: String,
        away: String,
        date: String,
        live: Boolean = false,
    ): MatchStatsResponse? = withContext(Dispatchers.IO) {
        // Матч мог начаться в другой день по UTC — пробуем соседние даты
        val enc = { s: String -> java.net.URLEncoder.encode(s, "UTF-8") }
        for (d in dateVariants(date)) {
            var u = "${server.trimEnd('/')}/api/match-stats" +
                "?home=${enc(home)}&away=${enc(away)}&date=$d"
            if (live) u += "&live=true"
            val resp = runCatching {
                http.newCall(Request.Builder().url(u).build()).execute()
            }.getOrNull() ?: continue
            val result: MatchStatsResponse? = resp.use {
                if (it.code == 404) {
                    null
                } else {
                    val body = it.body?.string()
                    if (it.isSuccessful && body != null) {
                        runCatching {
                            JsonFormat.json.decodeFromString(MatchStatsResponse.serializer(), body)
                        }.getOrNull()
                    } else {
                        null
                    }
                }
            }
            if (result != null) return@withContext result
        }
        null
    }

    private fun dateVariants(date: String): List<String> {
        if (!Regex("""\d{4}-\d{2}-\d{2}""").matches(date)) return listOf(date)
        return try {
            val d = java.time.LocalDate.parse(date)
            listOf(
                d.toString(),
                d.minusDays(1).toString(),
                d.plusDays(1).toString(),
            )
        } catch (e: Exception) {
            listOf(date)
        }
    }

    suspend fun fetchKhlCalendar(server: String): KhlCalendarResponse? =
        withContext(Dispatchers.IO) {
            runCatching {
                http.newCall(
                    Request.Builder().url("$server/api/khl/calendar").build()
                ).execute().use { resp ->
                    if (resp.isSuccessful) {
                        resp.body?.string()?.let {
                            JsonFormat.json.decodeFromString(KhlCalendarResponse.serializer(), it)
                        }
                    } else null
                }
            }.getOrNull()
        }

    suspend fun fetchScheduleDate(
        server: String,
        date: String,
        tzOffsetMinutes: Int,
    ): List<Match> = withContext(Dispatchers.IO) {
        runCatching {
            val u = "$server/api/schedule?date=$date&tz_offset=$tzOffsetMinutes"
            http.newCall(Request.Builder().url(u).build()).execute().use { resp ->
                if (resp.isSuccessful) {
                    resp.body?.string()?.let {
                        JsonFormat.json.decodeFromString(listAdapter, it)
                    } ?: emptyList()
                } else emptyList()
            }
        }.getOrDefault(emptyList())
    }

    suspend fun fetchStandings(server: String): StandingsResponse? =
        withContext(Dispatchers.IO) {
            runCatching {
                http.newCall(
                    Request.Builder().url("$server/api/standings?league=KHL").build()
                ).execute().use { resp ->
                    if (resp.isSuccessful) {
                        resp.body?.string()?.let {
                            JsonFormat.json.decodeFromString(StandingsResponse.serializer(), it)
                        }
                    } else null
                }
            }.getOrNull()
        }

    /**
     * Календарь на ближайшие `days` дней (сегодня + остальные) по локальной
     * дате устройства: КХЛ — официальный полный календарь сезона,
     * НХЛ — посуточные запросы к /api/schedule (сервер режет по tz_offset).
     *
     * Строки /api/schedule (они несут stream_urls/current_period) вкладываются
     * в официальные календарные строки КХЛ — иначе клик по матчу КХЛ из
     * календаря не находит источники и открывает плеер нельзя.
     */
    suspend fun fetchCalendarMatches(server: String, days: Int = 7): List<Match> {
        val zone = java.time.ZoneId.systemDefault()
        val today = java.time.LocalDate.now(zone)
        val windowStart = today.atStartOfDay(zone).toInstant()
        val windowEnd = today.plusDays(days.toLong()).atStartOfDay(zone).toInstant()
        val tzOffsetMin = java.util.TimeZone.getDefault().rawOffset / 60_000

        // Расписание по всем дням окна: КХЛ и НХЛ, с потоками и текущим периодом
        val sched = mutableListOf<Match>()
        for (i in 0 until days) {
            val d = today.plusDays(i.toLong()).toString()
            sched += fetchScheduleDate(server, d, tzOffsetMin)
                .filter {
                    it.league.equals("KHL", true) || it.league.equals("NHL", true)
                }
        }

        fun instantOf(m: Match): java.time.Instant? =
            runCatching { java.time.Instant.parse(m.datetimeUtc) }.getOrNull()

        fun norm(s: String) = s.trim().lowercase()

        fun sameTeam(a: String, b: String): Boolean {
            val x = norm(a)
            val y = norm(b)
            return x.isNotEmpty() && y.isNotEmpty() && (x == y || x.contains(y) || y.contains(x))
        }

        // Индекс расписания: лига + момент старта -> строки (одновременные игры
        // в одной лиге разрешаем по совпадению названий команд)
        val schedByKey = HashMap<String, MutableList<Match>>()
        for (m in sched) {
            val inst = instantOf(m) ?: continue
            schedByKey
                .getOrPut("${m.league.uppercase()}|$inst") { mutableListOf() }
                .add(m)
        }
        val schedMatched = HashSet<Match>()

        fun findSched(m: Match): Match? {
            val inst = instantOf(m) ?: return null
            val candidates = schedByKey["${m.league.uppercase()}|$inst"]
                ?.takeIf { it.isNotEmpty() } ?: return null
            candidates.firstOrNull { s ->
                (sameTeam(m.teamHome, s.teamHome) && sameTeam(m.teamAway, s.teamAway)) ||
                    (sameTeam(m.teamHome, s.teamAway) && sameTeam(m.teamAway, s.teamHome))
            }?.let { return it }
            return if (candidates.size == 1) candidates.first() else null
        }

        val out = mutableListOf<Match>()

        fetchKhlCalendar(server)?.let { cal ->
            for (e in cal.matches) {
                val inst = runCatching { java.time.Instant.parse(e.startUtc) }.getOrNull() ?: continue
                if (inst < windowStart || inst >= windowEnd) continue
                val official = Match(
                    id = (e.id ?: 0L).toInt(),
                    matchUid = "KHL_${e.id}",
                    league = "KHL",
                    teamHome = e.home,
                    teamAway = e.away,
                    datetimeUtc = e.startUtc,
                    status = when (e.status) {
                        "finished" -> "finished"
                        "in_progress" -> "live"
                        else -> "planned"
                    },
                    homeScore = e.scoreHome,
                    awayScore = e.scoreAway,
                )
                // Вкладываем потоки/период из расписания (у официального календаря их нет)
                val s = findSched(official)
                if (s != null) {
                    schedMatched.add(s)
                    out.add(
                        official.copy(
                            streamUrls = s.streamUrls,
                            currentPeriod = s.currentPeriod,
                        ),
                    )
                } else {
                    out.add(official)
                }
            }
        }

        // Строки расписания, не совпавшие с официальным календарём (НХЛ и прочее)
        for (m in sched) {
            if (m in schedMatched) continue
            val inst = instantOf(m) ?: continue
            if (inst < windowStart || inst >= windowEnd) continue
            out.add(m)
        }

        return out
            .distinctBy {
                it.matchUid ?: "${it.league}_${it.datetimeUtc}_${it.teamHome}_${it.teamAway}"
            }
            .sortedBy { it.datetimeUtc }
    }

    /** Активация по одноразовому 6-значному коду. true — ок; false — код не годится. */
    suspend fun activateCode(server: String, code: String, deviceId: String): Boolean =
        withContext(Dispatchers.IO) {
            val body = """{"code":"$code","device_id":"$deviceId"}"""
                .toRequestBody("application/json".toMediaType())
            val req = Request.Builder()
                .url("${server.trimEnd('/')}/api/tv/activate")
                .post(body)
                .header("Accept", "application/json")
                .build()
            http.newCall(req).execute().use { resp ->
                when {
                    resp.isSuccessful -> true
                    resp.code == 400 || resp.code == 410 -> false
                    else -> throw java.io.IOException("HTTP ${resp.code}")
                }
            }
        }

    /** Сервер знает это устройство? (восстановление авторизации после обновления) */
    suspend fun isDeviceActivated(server: String, deviceId: String): Boolean =
        withContext(Dispatchers.IO) {
            val u = "${server.trimEnd('/')}/api/tv/status?device_id=$deviceId"
            val resp = runCatching {
                http.newCall(Request.Builder().url(u).build()).execute()
            }.getOrNull() ?: return@withContext false
            resp.use {
                if (!it.isSuccessful) return@use false
                val body = it.body?.string() ?: return@use false
                body.contains("\"authorized\":true")
            }
        }
}
