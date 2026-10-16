package online.hockeylive.tv

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class StreamUrl(
    val url: String = "",
    val quality: String? = null,
    val source: String = "",
)

@Serializable
data class Match(
    val id: Int = 0,
    @SerialName("match_uid") val matchUid: String? = null,
    val league: String = "",
    @SerialName("team_home") val teamHome: String = "",
    @SerialName("team_away") val teamAway: String = "",
    @SerialName("datetime_utc") val datetimeUtc: String = "",
    val status: String = "",
    @SerialName("home_score") val homeScore: Int? = null,
    @SerialName("away_score") val awayScore: Int? = null,
    @SerialName("current_period") val currentPeriod: String? = null,
    @SerialName("stream_urls") val streamUrls: List<StreamUrl> = emptyList(),
) {
    val isLive: Boolean get() = status == "live"

    val aceHashes: List<String>
        get() = streamUrls
            .filter { it.source == "acestream" && it.url.startsWith("acestream://") }
            .map { it.url.removePrefix("acestream://").trim() }
            .filter { it.isNotEmpty() }

    val primeUrl: String?
        get() = streamUrls.firstOrNull { it.source == "prime" }?.url

    val displayScore: String
        get() = if (homeScore != null && awayScore != null) "$homeScore : $awayScore" else ""
}

object JsonFormat {
    val json = Json { ignoreUnknownKeys = true; isLenient = true }
}
