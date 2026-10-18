package online.hockeylive.tv

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class KhlCalendarItem(
    val id: Long? = null,
    val date: String = "",
    val time: String = "",
    val home: String = "",
    val away: String = "",
    val status: String = "",
    @SerialName("score_home") val scoreHome: Int? = null,
    @SerialName("score_away") val scoreAway: Int? = null,
    @SerialName("start_utc") val startUtc: String = "",
)

@Serializable
data class KhlCalendarResponse(
    val count: Int = 0,
    val matches: List<KhlCalendarItem> = emptyList(),
    val ready: Boolean = false,
)
