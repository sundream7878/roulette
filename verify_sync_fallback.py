import os
import sqlite3
from standalone_comment_monitor.db_handler import CommentDatabase
from dotenv import load_dotenv

load_dotenv()

def verify():
    db = CommentDatabase()
    # Use a known URL from Supabase (from previous check_supabase.py output)
    test_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/64865"
    
    print(f"--- Verification for URL: {test_url} ---")
    
    # 1. Clear local data for this URL to simulate a fresh environment
    print("1. Clearing local data for test URL...")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM participants WHERE url = ?", (test_url,))
        cursor.execute("DELETE FROM commenters WHERE url = ?", (test_url,))
        cursor.execute("DELETE FROM posts WHERE url = ?", (test_url,))
        conn.commit()
    
    # Verify it's empty locally
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM posts WHERE url = ?", (test_url,))
        count = cursor.fetchone()[0]
        print(f"   Local post count after clear: {count}")
    
    # 2. Call get_data which should trigger fallback and hydration
    print("2. Calling db.get_data(test_url)...")
    participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list_str, _ = db.get_data(test_url)
    
    print(f"   Result: Title='{title}', Participants={len(participants)}, Commenters={len(all_commenters)}")
    
    # 3. Verify local SQLite is now hydrated
    print("3. Verifying local SQLite hydration...")
    with db._get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM posts WHERE url = ?", (test_url,))
        row = cursor.fetchone()
        local_title = row[0] if row else "NOT FOUND"
        
        cursor.execute("SELECT count(*) FROM participants WHERE url = ?", (test_url,))
        p_count = cursor.fetchone()[0]
        
        print(f"   Hydrated local Title: '{local_title}'")
        print(f"   Hydrated local Participant count: {p_count}")
        
    if local_title != "NOT FOUND" and p_count > 0:
        print("\n--- Verification SUCCESS! Sync fallback and hydration working correctly. ---")
    else:
        print("\n--- Verification FAILED! Data not hydrated correctly. ---")

if __name__ == "__main__":
    verify()
