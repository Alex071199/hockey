import re

html = open("schedule_dump.html", "r", encoding="utf-8").read()
# Find text between game rows
# The pattern is: game_hour text, then team names, then gamelinks div
# Let's look for patterns like "Team1 - Team2" in the raw text
matches = re.findall(r"(\d{1,2}:\d{2})</text>([^<]+)", html)
teams = set()
for time_str, rest in matches:
    rest = rest.strip()
    if " - " in rest:
        parts = rest.split(" - ", 1)
        teams.add(parts[0].strip())
        # Second part may have more text, take just the team name
        team2 = parts[1].split("<")[0].strip()
        if team2:
            teams.add(team2)

for t in sorted(teams):
    print(t)
