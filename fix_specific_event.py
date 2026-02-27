import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

target_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67774"
title = "썬드림 댓글추첨 이벤트( 2월26일 )"
prizes = "로우램프\n로우램프\n스벅쿠폰\n스벅쿠폰\nCU모바일상품권\nCU모바일상품권\n"

# 1. Update SQLite
conn = sqlite3.connect('standalone_comment_monitor/comments.db')
c = conn.cursor()
c.execute("UPDATE posts SET title=?, prizes=? WHERE url=?", (title, prizes, target_url))
conn.commit()
print("Updated SQLite")

# 2. Update Supabase
try:
    res = supabase.table('posts').update({'title': title, 'prizes': prizes}).eq('url', target_url).execute()
    print("Updated Supabase:", res.data)
except Exception as e:
    print(f"Failed to update Supabase: {e}")
