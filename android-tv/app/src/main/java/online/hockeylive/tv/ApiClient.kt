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
