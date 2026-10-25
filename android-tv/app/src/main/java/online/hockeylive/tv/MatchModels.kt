package online.hockeylive.tv

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

@Serializable
data class StreamUrl(
    val url: String = "",
    val quality: String? = null,
    val source: String = "",
) {
    val isHls: Boolean
        get() {
            val u = url.lowercase()
            if (u.contains(".m3u8")) return true
            // sportplustv отдаёт HLS по «голым» ссылкам без расширения
            if (u.contains("sportvideodata") || u.contains("/hls/")) return true
            return false
        }

    val isAcestream: Boolean
        get() = source.equals("acestream", true) || url.startsWith("acestream://", true)

    val displayName: String
        get() = when {
            isAcestream -> "Лучшее качество"
            source == "prime" -> "Прайм"
            source == "sportplustv" -> "Спорт Плюс"
            source == "rutube" -> "Rutube"
            source == "livetv_youtube" -> "YouTube"
            source == "livetv_alieztv" -> "LiveTV"
            else -> source.ifEmpty { "Источник" }
        }
}

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

    val playableSources: List<StreamUrl>
        get() = streamUrls
            .filter { it.url.isNotBlank() }
            .distinctBy { it.source + "|" + it.url }
            .sortedWith(
                compareByDescending<StreamUrl> { it.isAcestream }
                    .thenByDescending { it.source.equals("prime", true) },
            )

    val displayScore: String
        get() = if (homeScore != null && awayScore != null) "$homeScore : $awayScore" else ""
}

object JsonFormat {
    val json = Json { ignoreUnknownKeys = true; isLenient = true }
}
