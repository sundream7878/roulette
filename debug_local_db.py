import sys
import os
import sqlite3
# Add current directory to path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def debug_check():
    db = CommentDatabase()
    active_url = db.get_active_url()
    print(f"Active URL: {active_url}")
    
    if not active_url:
        urls = db.get_all_urls()
        if urls:
            active_url = urls[0]
            print(f"Using latest URL instead: {active_url}")
        else:
            print("No URLs found in DB.")
            return

    p, last_id, all_c, title, prizes, memo, winners, allow_dup, allowed_list = db.get_data(active_url)
    
    print(f"\n--- Data for {active_url} ---")
    print(f"Title: {title}")
    print(f"Participants Count: {len(p)}")
    print(f"Commenters Count: {len(all_c)}")
    print(f"Allowed List (from Col): {allowed_list[:50] if allowed_list else 'None'}...")
    
    # Check raw table counts
    with sqlite3.connect('standalone_comment_monitor/comments.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM participants WHERE url = ?", (active_url,))
        p_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM commenters WHERE url = ?", (active_url,))
        c_count = cursor.fetchone()[0]
        print(f"Raw Table Counts - P: {p_count}, C: {c_count}")

if __name__ == "__main__":
    debug_check()
