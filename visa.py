# -*- coding: utf8 -*-

import time
import json
import random
import platform
import configparser
import re
from datetime import datetime

import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait as Wait
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


config = configparser.ConfigParser()
config.read('config.ini')

USERNAME = config['USVISA']['USERNAME']
PASSWORD = config['USVISA']['PASSWORD']
SCHEDULE_ID = config['USVISA']['SCHEDULE_ID']
MY_SCHEDULE_DATE = config['USVISA']['MY_SCHEDULE_DATE']
COUNTRY_CODE = config['USVISA']['COUNTRY_CODE'] 
FACILITY_ID = config['USVISA']['FACILITY_ID']

SENDGRID_API_KEY = config['SENDGRID']['SENDGRID_API_KEY']
PUSH_TOKEN = config['PUSHOVER']['PUSH_TOKEN']
PUSH_USER = config['PUSHOVER']['PUSH_USER']

LOCAL_USE = config['CHROMEDRIVER'].getboolean('LOCAL_USE')
HUB_ADDRESS = config['CHROMEDRIVER']['HUB_ADDRESS']

REGEX_CONTINUE = "//a[contains(text(),'Continuar')]"


# def MY_CONDITION(month, day): return int(month) == 11 and int(day) >= 5
def MY_CONDITION(month, day): return True # No custom condition wanted for the new scheduled date

STEP_TIME = 0.5  # time between steps (interactions with forms): 0.5 seconds
RETRY_TIME = 60*10  # wait time between retries/checks for available dates: 10 minutes
EXCEPTION_TIME = 60*30  # wait time when an exception occurs: 30 minutes
COOLDOWN_TIME = 60*60  # wait time when temporary banned (empty list): 60 minutes

DATE_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/days/{FACILITY_ID}.json?appointments[expedite]=false"
TIME_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment/times/{FACILITY_ID}.json?date=%s&appointments[expedite]=false"
APPOINTMENT_URL = f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv/schedule/{SCHEDULE_ID}/appointment"
EXIT = False


def send_notification(msg):
    print(f"Sending notification: {msg}")

    if SENDGRID_API_KEY:
        message = Mail(
            from_email=USERNAME,
            to_emails=USERNAME,
            subject=msg,
            html_content=msg)
        try:
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            print(response.status_code)
            print(response.body)
            print(response.headers)
        except Exception as e:
            print(e.message)

    if PUSH_TOKEN:
        url = "https://api.pushover.net/1/messages.json"
        data = {
            "token": PUSH_TOKEN,
            "user": PUSH_USER,
            "message": msg
        }
        requests.post(url, data)

def get_response_body(driver, target_url_part, timeout=10):
    """
    Captures the response body of a specific request in Selenium using CDP.

    :param driver: Selenium WebDriver instance
    :param target_url_part: Part of the URL to match (e.g., "/appointment/days/")
    :param timeout: Maximum time (in seconds) to wait for the response
    :return: Response body as a string, or None if not found
    """
    start_time = time.time()
    matching_request_id = None

    while time.time() - start_time < timeout:
        logs = driver.get_log("performance")

        # Step 1: Find the request ID for the target request
        for entry in logs:
            log_msg = json.loads(entry["message"])
            message = log_msg["message"]

            if message["method"] == "Network.requestWillBeSent":
                request_url = message["params"]["request"]["url"]

                if target_url_part in request_url:
                    print(f"Matched Request: {request_url}")
                    matching_request_id = message["params"]["requestId"]
                    break  # Stop once we find the target request

        # Step 2: Fetch the response if requestId was found
        if matching_request_id:
            for entry in logs:
                log_msg = json.loads(entry["message"])
                message = log_msg["message"]

                if message["method"] == "Network.responseReceived":
                    if message["params"]["requestId"] == matching_request_id:
                        # Get response body
                        response = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": matching_request_id})
                        return response.get("body", None)

        time.sleep(0.5)  # Short delay before rechecking logs

    print("No matching response found within timeout.")
    return None

def get_driver():
    if LOCAL_USE:
        options = webdriver.ChromeOptions()
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # Enable performance logs
        dr = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        dr.execute_cdp_cmd("Network.enable", {})
    else:
        dr = webdriver.Remote(command_executor=HUB_ADDRESS, options=webdriver.ChromeOptions())
    return dr

driver = get_driver()

def login():
    # Bypass reCAPTCHA
    driver.get(f"https://ais.usvisa-info.com/{COUNTRY_CODE}/niv")
    time.sleep(STEP_TIME)
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    print("Login start...")
    href = driver.find_element(By.XPATH, '//*[@id="header"]/nav/div[1]/div[1]/div[2]/div[1]/ul/li[3]/a')
   
    href.click()
    time.sleep(STEP_TIME)
    Wait(driver, 60).until(EC.presence_of_element_located((By.NAME, "commit")))

    print("\tclick bounce")
    a = driver.find_element(By.XPATH, '//a[@class="down-arrow bounce"]')
    a.click()
    time.sleep(STEP_TIME)

    do_login_action()


def do_login_action():
    print("\tinput email")
    user = driver.find_element(By.ID, 'user_email')
    user.send_keys(USERNAME)
    time.sleep(random.randint(1, 3))

    print("\tinput pwd")
    pw = driver.find_element(By.ID, 'user_password')
    pw.send_keys(PASSWORD)
    time.sleep(random.randint(1, 3))

    print("\tclick privacy")
    box = driver.find_element(By.CLASS_NAME, 'icheckbox')
    box .click()
    time.sleep(random.randint(1, 3))

    print("\tcommit")
    btn = driver.find_element(By.NAME, 'commit')
    btn.click()
    time.sleep(random.randint(1, 3))

    Wait(driver, 60).until(
        EC.presence_of_element_located((By.XPATH, REGEX_CONTINUE)))
    print("\tlogin successful!")

def find_oldest_date_from_text(text):
    """
    Extracts dates from a text response and finds the oldest one.

    :param text: String containing dates in 'yyyy-MM-dd' format.
    :return: The oldest date as a string in 'yyyy-MM-dd' format.
    """
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", text)
    if not dates:
        return None  # No valid dates found
    
    date_objects = [datetime.strptime(date, "%Y-%m-%d") for date in dates]
    oldest_date = min(date_objects)
    return oldest_date.strftime("%Y-%m-%d")

def get_nearest_date():
    driver.get(APPOINTMENT_URL)
    response_body = get_response_body(driver, "/appointment/days/")
    nearest_date = find_oldest_date_from_text(response_body)
    return nearest_date

def is_earlier(date):
    my_date = datetime.strptime(MY_SCHEDULE_DATE, "%Y-%m-%d")
    new_date = datetime.strptime(date, "%Y-%m-%d")
    result = my_date > new_date
    print(f'Is {my_date} > {new_date}:\t{result}')
    return result

def push_notification(dates):
    msg = "date: "
    for d in dates:
        msg = msg + d.get('date') + '; '
    send_notification(msg)

if __name__ == "__main__":
    login()
    retry_count = 0
    while 1:
        if retry_count > 6:
            break
        try:
            print("------------------")
            print(datetime.today())
            print(f"Retry count: {retry_count}")
            print()

            date = get_nearest_date()
            if not date:
              msg = "List is empty"
              send_notification(msg)
              EXIT = True
            print("Nearest date: " + str(date))
            if is_earlier(date):
                print(f"New date: {date}")
                send_notification("New available nearest date: " + str(date) + "!!!")

            if(EXIT):
                print("------------------exit")
                break

            if not date:
              msg = "List is empty"
              send_notification(msg)
              #EXIT = True
              time.sleep(COOLDOWN_TIME)
            else:
              time.sleep(RETRY_TIME)

        except:
            retry_count += 1
            time.sleep(EXCEPTION_TIME)

    if(not EXIT):
        send_notification("HELP! Crashed.")
