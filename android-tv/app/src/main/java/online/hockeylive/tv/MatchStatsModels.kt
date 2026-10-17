package online.hockeylive.tv

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class StatsMatchInfo(
    val home: String = "",
    val away: String = "",
    @SerialName("score_home") val scoreHome: Int = 0,
    @SerialName("score_away") val scoreAway: Int = 0,
    @SerialName("home_team_id") val homeTeamId: Int = 0,
    @SerialName("away_team_id") val awayTeamId: Int = 0,
    val status: String = "",
)

@Serializable
data class StatsPeriods(
    val first: String? = null,
    val second: String? = null,
    val third: String? = null,
    val overtime: String? = null,
    val penalties: String? = null,
)

@Serializable
data class TeamSideStats(
    val shots: Int = 0,
    @SerialName("goals_for") val goalsFor: Int = 0,
    val ppg: Int = 0,
    val shg: Int = 0,
    val ppc: Int = 0,
    @SerialName("faceoffs_won") val faceoffsWon: Int = 0,
    val pim: Int = 0,
    @SerialName("puck_control_pct") val puckControl: Double? = null,
    @SerialName("zone_entries") val zoneEntries: Int = 0,
)

@Serializable
data class StatsPair(
    val home: TeamSideStats? = null,
    val away: TeamSideStats? = null,
)

@Serializable
data class StatGoal(
    val time: String? = null,
    val score: String? = null,
    val period: Int = 0,
    @SerialName("team_id") val teamId: Int = 0,
    val scorer: String = "",
    val assistants: List<String> = emptyList(),
)

@Serializable
data class StatPenalty(
    val time: String? = null,
    val period: Int = 0,
    val reason: String = "",
    val minutes: Int = 0,
    val player: String = "",
    @SerialName("team_id") val teamId: Int = 0,
)

@Serializable
data class RosterPlayer(
    val number: Int? = null,
    val name: String = "",
    val role: String = "",
    val image: String? = null,
    val goals: Int = 0,
)

@Serializable
data class StatsRosters(
    val home: List<RosterPlayer> = emptyList(),
    val away: List<RosterPlayer> = emptyList(),
)

@Serializable
data class MatchStatsResponse(
    val match: StatsMatchInfo? = null,
    val periods: StatsPeriods? = null,
    @SerialName("team_stats") val teamStats: StatsPair? = null,
    val goals: List<StatGoal> = emptyList(),
    val penalties: List<StatPenalty> = emptyList(),
    val rosters: StatsRosters? = null,
)
