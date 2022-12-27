from bs4 import BeautifulSoup as bs
import requests


## Get game links
game_links = []
# Set year to pull game from
current_year = 2015

url = f"https://www.baseball-reference.com/leagues/MLB/{current_year}-schedule.shtml"
resp = requests.get(url)
soup = bs(resp.text)
games = soup.findAll('a',text='Boxscore')
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
game_summary = {'game_id' : game_id}
scorebox = soup.find('div', {'class':'scorebox'})
strongs = scorebox.find_all('strong')
strongs
game_summary['away_team_abbr'] = strongs[2]['href'].split('/')[-2]
game_summary['home_team_abbr'] = strongs[6]['href'].split('/')[-2]
game_summary
teams = strongs.find_all('a')
teams
##########
