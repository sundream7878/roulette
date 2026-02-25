import sys
import os
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# URL to test
URL = "https://cafe.naver.com/f-e/cafes/27870803/articles/67793?boardtype=L&menuid=23&referrerAllArticles=false"

def capture_source():
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(URL)
        time.sleep(3)
        
        # Switch to iframe
        try:
            iframe = driver.find_element(By.ID, "cafe_main")
            driver.switch_to.frame(iframe)
            print("Switched to iframe")
        except:
            print("No iframe found")
            
        # Save source
        with open("page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("Page source saved to page_source.html")
        
        # Try finding any comment-like elements
        print("Searching for common patterns...")
        for pattern in ["CommentItem", "comment_box", "nick", "nickname", "content"]:
            count = len(driver.find_elements(By.XPATH, f"//*[contains(@class, '{pattern}')]"))
            print(f"Pattern '{pattern}': {count} elements")
            
    finally:
        driver.quit()

if __name__ == "__main__":
    capture_source()
