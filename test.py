from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# Setup Chrome with DevTools Protocol (CDP)
options = webdriver.ChromeOptions()
options.set_capability("goog:loggingPrefs", {"performance": "ALL"})  # Enable performance logs

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# Enable Network Monitoring
driver.execute_cdp_cmd("Network.enable", {})

# Open the target webpage
driver.get("https://ais.usvisa-info.com/es-co/niv")

# Wait for the page to load
import time
time.sleep(5)  # Adjust as needed

# Extract Network Logs
logs = driver.get_log("performance")

# Filter and print network requests
for entry in logs:
    log_msg = entry["message"]
    if '"Network.requestWillBeSent"' in log_msg:  # Filtering only network requests
        print(log_msg)

# Close browser
driver.quit()
