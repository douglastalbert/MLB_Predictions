"""
Project inspired by rdpharr's MLB Baseball Predictions at https://rdpharr.github.io/project_notes/baseball/benchmark/webscraping/brier/accuracy/calibration/machine%20learning/2020/09/20/baseball_project.html
Most infrastructure
"""

import requests
import re
import datetime as dt

url = 'https://www.baseball-reference.com/leagues/MLB/2019-schedule.shtml'
resp = requests.get(url)
# All the H3 tags contain day names
days = re.findall("<h3>(.*2019)</h3>", resp.text)
dates = [dt.datetime.strptime(d,"%A, %B %d, %Y") for d in days]
print("Number of days MLB was played in 2019:", len(dates))


"""
Get game info
"""
from bs4 import BeautifulSoup as bs
game_data = []
for d in dates:
    # get the web page with game data on it
    game_day = d.strftime('%Y-%m-%d')
    url = f'https://www.covers.com/Sports/MLB/Matchups?selectedDate={game_day}'
    resp = requests.get(url)

    # parse the games
    scraped_games = bs(resp.text).findAll('div',{'class':'cmg_matchup_game_box'})
    for g in scraped_games:
        game = {}
        game['home_moneyline'] = g['data-game-odd']
        game['date'] = g['data-game-date']
        try:
            game['home_score'] =g.find('div',{'class':'cmg_matchup_list_score_home'}).text.strip()
            game['away_score'] =g.find('div',{'class':'cmg_matchup_list_score_away'}).text.strip()
        except:
            game['home_score'] =''
            game['away_score'] =''

        game_data.append(game)
        if len(game_data) % 500==0:
            #show progress
            print(dt.datetime.now(), game_day, len(game_data))
print("Done! Games downloaded:", len(game_data))

#Save data into pickle file
import pickle
pickle.dump(game_data, open('Documents/MLB_Predictions/covers_data_19.pkl','wb'))

"""
Find sportsbook accuracy
"""
from sklearn.metrics import accuracy_score

# the actual outcome of the game, true if the the home team won
outcomes = []
# predictions derived from moneyline odds. True if the home team was the favorite
predictions = []
# probability the home team will win, derived from moneyline odds
# derived from formulas at https://www.bettingexpert.com/academy/advanced-betting-theory/odds-conversion-to-percentage
probabilities = []

for d in game_data:
    try:
        moneyline = int(d['home_moneyline'])
        home_score = int(d['home_score'])
        away_score = int(d['away_score'])
    except:
        #incomplete data
        continue
    if moneyline==100:
        # it's rare to have a tossup since covers is averaging the odds from several sports books
        # but we'll exclude them from our calculations
        continue

    # convert moneyline odds ot their implied probabilities
    if moneyline<0:
        probabilities.append(-moneyline/(-moneyline + 100))
    elif moneyline>100:
        probabilities.append(100/(moneyline + 100))

    outcomes.append(home_score>away_score)
    predictions.append(moneyline<0)

print("Sportsbook accuracy (excluding tossups): {0:.2f}%".format(100*accuracy_score(outcomes,predictions)))

"""
Sportsbook calibration
"""
#collapse-hide
from sklearn.calibration import calibration_curve
from sklearn.metrics import accuracy_score, brier_score_loss
import matplotlib.pyplot as plt

def cal_curve(data, bins):
    # adapted from:
    #https://scikit-learn.org/stable/auto_examples/calibration/plot_calibration_curve.html
    fig = plt.figure(1, figsize=(12, 8))
    ax1 = plt.subplot2grid((3, 1), (0, 0), rowspan=2)
    ax2 = plt.subplot2grid((3, 1), (2, 0))

    ax1.plot([0, 1], [0, 1], "k:", label="Perfectly calibrated")

    for y_test, y_pred, y_proba, name in data:
        brier = brier_score_loss(y_test, y_proba)
        print("{}\tAccuracy:{:.4f}\t Brier Loss: {:.4f}".format(
            name, accuracy_score(y_test, y_pred), brier))
        fraction_of_positives, mean_predicted_value = \
            calibration_curve(y_test, y_proba, n_bins=bins)
        ax1.plot(mean_predicted_value, fraction_of_positives,
                 label="%s (%1.4f)" % (name, brier))
        ax2.hist(y_proba, range=(0, 1), bins=bins, label=name,
                 histtype="step", lw=2)

    ax1.set_ylabel("Fraction of positives")
    ax1.set_ylim([-0.05, 1.05])
    ax1.legend(loc="lower right")
    ax1.set_title('Calibration plots  (reliability curve)')

    ax2.set_xlabel("Mean predicted value")
    ax2.set_ylabel("Count")
    ax2.legend(loc="lower right")

    plt.tight_layout()
    plt.show()

data = [(outcomes, predictions, probabilities, 'SportsBook')]
cal_curve(data, 15)
"""
The graph above tells us several things about the calibration of the casino's predictions. The reliability curve clearly shows that the casino is highly calibrated. Interestingly, it looks like the blue line is shifted down slightly from the "perfectly calibrated" line. It would be a better fit if it was 0.05 higher. This may account for the house advantage.

The histogram below shows what portion of the games fall into each bin. We see a slight predicted advantage to the home team, with more than 50% of the observations above the 50% mark. Otherwise it looks pretty normally distributed.

Above, I said the reliability curve looks highly calibrated. If we are to judge our own efforts against the sportsbook, we can't just be eyeballing this graph all the time. A metric would be nice. One metric that is suited for calibration measurement is the Brier Score, which I'll be using to measure the model effectiveness going forward. Getting a model that scores less than 0.2358 is the target for our efforts.
"""
pickle.dump((outcomes,predictions,probabilities), open('Documents/MLB_Predictions/baseline_19.pkl', 'wb'))
