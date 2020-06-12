from flask import Flask, render_template, send_from_directory
from bs4 import BeautifulSoup
import requests 
import json
import datetime
import csv
import random


app = Flask(__name__, static_url_path='')

# setting up a headers to avoid blocking from web site and immitate real user. Headers are copied from typical request
# sent by my browser and machine (linux)
headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9", 
    "Accept-Encoding": "gzip, deflate, br", 
    "Accept-Language": "ru,en-GB;q=0.9,en-US;q=0.8,en;q=0.7,ru-RU;q=0.6", 
    "Upgrade-Insecure-Requests": "1", 
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/83.0.4103.61 Chrome/83.0.4103.61 Safari/537.36"
}

# setting up proxies for IP rotation. Ususaly one would use services such as Crawlera, but for this interview application
# we would use simple and free implementation. I used free proxies from hidemy.name and as it's free they are UNRELIABLE
# and they change frequently. So if you have problems disable them 
proxies = ["202.138.248.107:8080", "41.65.201.165:8080", "93.179.209.216:57520", "104.154.143.77:3128", "212.83.154.189:5836", "80.243.158.6:8080", "163.172.29.6:5836"]

# IMPORTANT! Uncomment this line to disable proxies and IP rotation (if it takes long time to load page)
# proxies = []


# this function recursively parses comments and returns a text version
def parse_comments(data, tabs):
    text = ""
    if len(data) == 0:
        return text
    for x in data:
        for i in range(0, tabs):
            text = text + "----"
        text = text + x["message"] + "\n\n\n\n" + parse_comments(x["children"], tabs + 1)
    return text

# this function is for getting a list of all news and its urls
def news_all():
    
    
    # this part turned out to be not needing the scrapper as inspecting (and a little bit debugging) the web site
    # one can find and api call (inner HTML javascript) to this endpoint - http://static.zakon.kz/zakon_cache/category/2/2020/06-11_news.json
    # which is essentially the qucik list of all the news in all languages in JSON. In essense, it can be considered as open API
    # as it does not need any API keys or authorization. It will save us computation time. The JSON already contains title, date, short description,
    # url to image and comments count

    # getting today's date to inject in url
    now = datetime.datetime.now()
    day = month = None
    
    # adding 0s before dates 
    if now.day < 10:
        day = '0' + str(now.day)
    else:
        day = str(now.day)

    if now.month < 10:
        month = '0' + str(now.month)
    else:
        month = str(now.month)



    url = 'http://static.zakon.kz/zakon_cache/category/2/' + str(now.year) + '/' + month + '-' + day + '_news.json'
    print(url)

    # getting JSON from zakon news site with IP rotation 
    i = 0
    response = None
    while True:
        try:
            #try with random proxy
            if len(proxies) > 0:
                i = random.randint(0, len(proxies) - 1)
                prox = {"http" : proxies(i), "https" : proxies(i)}
                response = requests.get(url, headers=headers, proxies=prox)
                break
            # if we ran out of proxies don't use them at all
            else:
                response = requests.get(url, headers=headers)
                break
        except:
            # if there is an error remove that proxy and retry
            if len(proxies) > 0:
                del proxies[i]
            else:
                print("Sorry, we have run out of proxies and been blocked :( Update your proxy list or use paid services")
                raise Exception("Connection Error!")



    # check if we get anything, if not return error message (for now)
    if response.status_code != 200:
        return ("Error! Status Code: " + str(response.status_code))
    
    # returning the result as a dict
    return json.loads(response.content)



# ROUTES --------------------------------------------------------------
# main page just for views and graphical interface
@app.route('/')
def main_page():

    news_dict = news_all()
    
    return render_template("index.html", news = news_dict)


# this route is responsible for scraping each news page
@app.route('/news')
def update_json():


    # call '/news' route to update global news list (NEWS) 
    news_dict = news_all()

    # inference through each news item. This time there is not easy API call (i could not find one), so we have to 
    # request each and every news url in the list and add additional data to NEWS document, as usual with IP rotation
    for news in news_dict["items"]:
        i = 0
        response = None
        while True:
            try:
                #try with random proxy
                if len(proxies) > 0:
                    i = random.randint(0, len(proxies) - 1)
                    prox = {"http" : proxies(i), "https" : proxies(i)}
                    response = requests.get(news["url"], headers=headers, proxies=prox)
                    break
                # if we ran out of proxies don't use them at all
                else:
                    response = requests.get(news["url"], headers=headers)
                    break
            except:
                # if there is an error remove that proxy and retry
                if len(proxies) > 0:
                    del proxies[i]
                else:
                    print("Sorry, we have been blocked :( Update your proxy list or use paid services")
                    raise Exception("Connection Error!")

        # check for error code (if we have problems here then zakon.kz's data is corrupted)
        if response.status_code != 200:
            return ("Error! One of the news links are invalid! Status Code: " + str(response.status_code) + " \nURL: " + news["url"])

        # parsing with bs4
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # parsing full text
        n_text = ""
        text = soup.find('div',attrs={'id':'initial_news_story'})
        
        # some news are formatted differently (probably older versions of site)
        if text is None:
            text = soup.find('div',attrs={'class':'WordSection1'})
            if text is None:
                continue
        
        n_text = text.getText()

        # adding new field (full text)
        news["full_text"] = n_text
        

        # parsing comments. Comments are retrieved dynamically with js code from this endpoint: https://zcomments.net/service/init/1
        # The post request is sent to it and comments are retrieved
        # it needs several fields
        n_comments = ""
        if int(news["comm_num"]) > 0:
            url = "https://zcomments.net/service/init/1?page_title=" + news["title"] +  "&page_url=" + news["url"] + "&block_code=zakonnewsid" + news["id"] + "&lang=" + news["lang"]
            resp = requests.post(url)

            # check for error code (if we have problems here then zakon.kz's data is corrupted)
            if response.status_code != 200:
                return ("Error! One of the news links are invalid! Status Code: " + str(response.status_code) + " \Title: " + news["title"])

            # convert JSON to dict
            comm_data = json.loads(resp.content)
            
            n_comments = parse_comments(comm_data["comments"]["items"], 0)
            
                
        news["comments"] = n_comments

    print(news_dict["items"])

    with open('static/news.csv', 'w',) as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['ID', 'Title', 'Date', 'URL', 'Image URL', 'Language', 'Short Text', 'Full Text', 'Comments Count', 'Comments'])
        for news in news_dict["items"]:
            writer.writerow([news["id"], news["title"], news["date_print"], news["url"], news["img"], news["lang"], news["shortstory"], news["full_text"], news["comm_num"], news["comments"]])


    return app.send_static_file('news.csv')