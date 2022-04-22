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
