import json
d = json.load(open(r'C:\Users\kopys\Desktop\scrap — livetv\test_deploy2.json', 'r', encoding='utf-8'))
for g in d['groups']:
    print(g['name'] + ':')
    for r in g['rows']:
        pos = r['position']
        name = r['team_name']
        pts = r['points']
        gp = r['played']
        w = r['wins']
        ow = r['ot_wins']
        ol = r['ot_losses']
        l = r['losses']
        gf = r['goals_for']
        ga = r['goals_against']
        print(f'  {pos:2d}. {name:20s} {pts:2d}pts  {gp:2d}GP  {w:2d}W  {ow:2d}OW  {ol:2d}OL  {l:2d}L  {gf:2d}-{ga:2d}')
    print()
