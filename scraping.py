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
game_summary['away_team_abbr'] = strongs[2]['href'].split('/')[-2]
game_summary['home_team_abbr'] = strongs[6]['href'].split('/')[-2]
meta = scorebox.find('div', {'class': 'scorebox_meta'}).find_all('div')
#TODO: Add additional summary info for total / score forecasting
game_summary['date'] = meta[0].text.strip()
game_summary['start_time'] = meta[1].text[12:-6].strip()
game_summary

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

#Home Batting Table (Table 1)
h_foot = stats_tables[2].find('tfoot')
#TODO: update with individual player stats
home_team_batting_stats = {x['data-stat']:x.text.strip() for x in h_foot.findAll('td')}

##########
