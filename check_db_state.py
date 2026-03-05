import sqlite3
import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def check_local():
    print("--- Local SQLite State ---")
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standalone_comment_monitor")
    db_path = os.path.join(base_dir, "comments.db")
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT url, title, prizes, memo, allowed_list FROM posts")
    rows = cursor.fetchall()
    print(f"Posts in Local: {len(rows)}")
    for row in rows:
        print(f"URL: {repr(row[0])}")
        print(f"  Title: {row[1]}")
        print(f"  Prizes: {row[2]}")
        print(f"  Memo: {row[3]}")
        print(f"  Allowed List Length: {len(row[4]) if row[4] else 'None/Empty'}")
    
    cursor.execute("SELECT COUNT(*) FROM participants")
    print(f"Total Participants in Local: {cursor.fetchone()[0]}")
    
    cursor.execute("SELECT COUNT(*) FROM commenters")
    print(f"Total Commenters in Local: {cursor.fetchone()[0]}")
    
    conn.close()

def check_supabase():
    print("\n--- Supabase Cloud State ---")
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY missing")
        return
    
    supabase = create_client(url, key)
    
    res = supabase.table("posts").select("*").execute()
    print(f"Posts in Supabase: {len(res.data)}")
    for post in res.data:
        print(f"URL: {post.get('url')}")
        print(f"  Title: {post.get('title')}")
        print(f"  Prizes: {post.get('prizes')}")
        print(f"  Memo: {post.get('memo')}")
        print(f"  Allowed List Length: {len(post.get('allowed_list')) if post.get('allowed_list') else 'None/Empty'}")
        print(f"  Last Comment ID: {post.get('last_comment_id')}")

    res = supabase.table("participants").select("count").execute()
    print(f"Total Participants in Supabase: {len(res.data)}")
    
    res = supabase.table("commenters").select("author").execute()
    print(f"Total Commenters in Supabase: {len(res.data)}")

if __name__ == "__main__":
    check_local()
    check_supabase()
