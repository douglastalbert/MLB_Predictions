from bs4 import BeautifulSoup as bs
import requests


## Get game links
game_links = []
# Set year to pull game from
current_year = 2015

url = f"https://www.baseball-reference.com/leagues/MLB/{current_year}-schedule.shtml"
resp = requests.get(url)
soup = bs(resp.text)
games = soup.findAll('a', text='Boxscore')
game_links.extend([x['href'] for x in games])
print("Number of games to download: ", len(game_links))
game_links[0]


#TEST get data from a single games
url = 'https://www.baseball-reference.com' + game_links[0]
response = requests.get(url)
game_id = url.split('/')[-1][:-6]
game_id
soup = bs(response.text)

#Game Summary
game_summary = {'game_id': game_id}
scorebox = soup.find('div', {'class': 'scorebox'})
strongs = scorebox.find_all('strong')
game_summary['away_team_abbr'] = strongs[0].find('a')['href'].split('/')[-2]
game_summary['home_team_abbr'] = strongs[1].find('a')['href'].split('/')[-2]
meta = scorebox.find('div', {'class': 'scorebox_meta'}).find_all('div')
#TODO: Add additional summary info for total / score forecasting
game_summary['date'] = meta[0].text.strip()
game_summary['start_time'] = meta[1].text[12:-6].strip()

#Table dict
    #Note: need to preprocess because tables appear in comments in the HTML
    #Note: fuck baseball reference for making this so unnecessarily difficult
uncommented_html = ''
for h in response.text.split('\n'):
    # if '<!--     <div' in h: h.replace('<!--     <div', '')
    # if h.strip() == '<!--': h.replace('<!--', '')
    # if h.strip() == '-->': h.replace('-->', '')
    if '<!--     <div' in h: continue
    if h.strip() == '<!--': continue
    if h.strip() == '-->': continue
    uncommented_html += h + '\n'
soup = bs(uncommented_html)
stats_tables = soup.find_all('table', {'class' : 'stats_table'})

#Away Batting Table (Table 1)
a_foot = stats_tables[1].find('tfoot')
#TODO: update with individual player stats
away_team_batting_stats = {x['data-stat']:x.text.strip() for x in a_foot.findAll('td')}

#Home Batting Table (Table 2)
h_foot = stats_tables[2].find('tfoot')
#TODO: update with individual player stats
home_team_batting_stats = {x['data-stat']:x.text.strip() for x in h_foot.findAll('td')}

#Away / Home Team Pitching Tables (Table 3/4)
ap_foot = stats_tables[3].find('tfoot')
away_team_pitching_stats = {x['data-stat']:x.text.strip() for x in ap_foot.findAll('td')}
hp_foot = stats_tables[4].find('tfoot')
home_team_pitching_stats = {x['data-stat']:x.text.strip() for x in hp_foot.findAll('td')}

#Away Individual Pitcher Table
ap_table = stats_tables[3]
away_pitcher_stats = []
ap_rows = ap_table.find_all('tr')[1:-1]
for r in ap_rows:
    summary = {x['data-stat']:x.text.strip() for x in r.find_all('td')}
    summary['name'] = r.find('th', {'data-stat':'player'}).find('a')['href'].split('/')[-1][:-6].strip()
    away_pitcher_stats.append(summary)

#Home Individual Pitcher Table
hp_table = stats_tables[4]
home_pitcher_stats = []
hp_rows = hp_table.find_all('tr')[1:-1]
for r in hp_rows:
    summary = {x['data-stat']:x.text.strip() for x in r.find_all('td')}
    summary['name'] = r.find('th', {'data-stat':'player'}).find('a')['href'].split('/')[-1][:-6].strip()
    home_pitcher_stats.append(summary)

#Away Individual Hitter Table
ab_table = stats_tables[1]
away_hitter_stats = []
ab_rows = ab_table.find_all('tr')[1:-1]
for r in ab_rows:
    if '\xa0\xa0\xa0' in r.find('th').text: continue
    summary = {x['data-stat']:x.text.strip() for x in r.find_all('td')}
    summary['name'] = r.find('th', {'data-stat':'player'}).find('a')['href'].split('/')[-1][:-6].strip()
    away_hitter_stats.append(summary)

#Home Individual Hitter Table
hb_table = stats_tables[2]
home_hitter_stats = []
hb_rows = hb_table.find_all('tr')[1:-1]
for r in hb_rows:
    if '\xa0\xa0\xa0' in r.find('th').text: continue
    summary = {x['data-stat']:x.text.strip() for x in r.find_all('td')}
    summary['name'] = r.find('th', {'data-stat':'player'}).find('a')['href'].split('/')[-1][:-6].strip()
    home_hitter_stats.append(summary)

##########
