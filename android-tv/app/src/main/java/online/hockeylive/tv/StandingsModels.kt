package online.hockeylive.tv

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class StandingsRow(
    val position: Int = 0,
    @SerialName("team_name") val teamName: String = "",
    val logo: String? = null,
    val played: Int = 0,
    val wins: Int = 0,
    @SerialName("ot_wins") val otWins: Int = 0,
    @SerialName("ot_losses") val otLosses: Int = 0,
    val losses: Int = 0,
    @SerialName("goals_for") val goalsFor: Int = 0,
    @SerialName("goals_against") val goalsAgainst: Int = 0,
    @SerialName("goal_diff") val goalDiff: Int = 0,
    val points: Int = 0,
)

@Serializable
data class StandingsGroup(
    val name: String = "",
    val rows: List<StandingsRow> = emptyList(),
)

@Serializable
data class StandingsResponse(
    val league: String = "",
    val season: Int = 0,
    @SerialName("updated_at") val updatedAt: String = "",
    val groups: List<StandingsGroup> = emptyList(),
    val stale: Boolean = false,
)
