import re

html = open("schedule_dump.html", "r", encoding="utf-8").read()
leagues = set(re.findall(r"<b>([^<]+)</b>", html))
print("All leagues found:")
for l in sorted(leagues):
    print(f"  {l}")

# Check for Russian leagues
for keyword in ["KHL", "VHL", "MHL"]:
    if keyword in html:
        print(f"\n{keyword} FOUND in HTML")
    else:
        print(f"\n{keyword} NOT found in HTML")
