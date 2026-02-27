import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()
conn = sqlite3.connect('standalone_comment_monitor/comments.db')
c = conn.cursor()

c.execute("SELECT url, title, prizes FROM posts WHERE url LIKE '%67774%'")
user_data = c.fetchone()
print(f"SQLite Data (user reported): {user_data}")
if user_data and user_data[1]:
    title_bytes = user_data[1].encode('cp949', errors='replace')
    print("Raw bytes:", title_bytes)
    print("Decoded as utf-8?", title_bytes.decode('utf-8', errors='replace'))
    
c.execute("SELECT url, title, prizes FROM posts WHERE url='test_encoding_url'")
test_data = c.fetchone()
if test_data and test_data[1]:
    title_bytes = test_data[1].encode('cp949', errors='replace')
    print("Raw bytes:", title_bytes)
    print("Decoded as utf-8?", title_bytes.decode('utf-8', errors='replace'))

