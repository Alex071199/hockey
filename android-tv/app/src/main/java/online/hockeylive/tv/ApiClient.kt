package online.hockeylive.tv

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

object ApiClient {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val listAdapter = JsonFormat.json.serializer(ListSerializer(Match.serializer()))

    suspend fun fetchMatches(server: String): List<Match> = withContext(Dispatchers.IO) {
        val all = mutableListOf<Match>()
        for (league in listOf("KHL", "NHL")) {
            val req = Request.Builder()
                .url("$server/api/schedule?league=$league")
                .header("Accept", "application/json")
                .build()
            http.newCall(req).execute().use { resp ->
                if (resp.isSuccessful) {
                    val body = resp.body?.string() ?: continue
                    val items = JsonFormat.json.decodeFromString(listAdapter, body)
                    all += items
                }
            }
        }
        all
    }
}
