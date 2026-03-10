import os
import time
from standalone_comment_monitor.db_handler import CommentDatabase
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def verify():
    db = CommentDatabase()
    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    
    # Use a real URL that exists in Supabase posts
    test_url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/64865"
    author = f"FixTester_{int(time.time())}"
    
    print(f"--- Verifying Fixed Sync for URL: {test_url} ---")
    print(f"Author to sync: {author}")
    
    # 1. Trigger save_data (this starts a background thread)
    participants_dict = {
        author: (5, "2024-03-10T12:00:00")
    }
    all_commenters = [
        {'name': author, 'created_at': "2024-03-10T12:00:00"}
    ]
    
    print("1. Calling db.save_data (triggers background sync)...")
    db.save_data(test_url, participants_dict, "last_id_test", all_commenters=all_commenters)
    
    # 2. Wait for background thread to complete
    print("2. Waiting 5 seconds for background sync to complete...")
    time.sleep(5)
    
    # 3. Check Supabase
    print("3. Checking Supabase for the new author...")
    res = supabase.table("participants").select("*").eq("url", test_url).eq("author", author).execute()
    
    if res.data:
        print(f"   Success! Found in Supabase: {res.data[0]}")
    else:
        print("   FAILED! Author not found in Supabase.")
        
        # Check logs
        log_file = "monitor_debug.log"
        if os.path.exists(log_file):
            print("\nChecking monitor_debug.log for errors:")
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                for line in lines[-5:]:
                    print(f"  {line.strip()}")
        else:
            print("\nLog file monitor_debug.log not found.")

if __name__ == "__main__":
    verify()
