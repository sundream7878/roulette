import os
import time
from standalone_comment_monitor.db_handler import CommentDatabase
from dotenv import load_dotenv

load_dotenv()

def check_broadcast_logic():
    db = CommentDatabase()
    if not db.supabase:
        print("Error: Supabase not connected.")
        return

    print("--- Checking Supabase Active Post and Settings ---")
    try:
        # 1. Fetch active post directly like _supabase_poll_loop does
        res = db.supabase.table('posts').select('url, title, prizes, memo, winners, allowed_list, updated_at').eq('is_active', True).limit(1).execute()
        
        if not res.data:
            print("No active post found in Supabase.")
            return

        post = res.data[0]
        print(f"Active URL: {post['url']}")
        print(f"Title: {post['title']}")
        print(f"Prizes: {repr(post['prizes'])}")
        print(f"Updated At: {post['updated_at']}")
        
        # 2. Check local memory state (simulation)
        # In the real app, _last_supabase_state is global in monitor_view.py
        # If the app just started, it might have None for title/prizes if it failed to init
        
        print("\n--- Diagnostic Conclusion ---")
        if post['title'] and post['prizes']:
            print("Settings EXIST in Supabase.")
            print("If they are not showing in UI, the issue is likely:")
            print("1. _supabase_poll_loop is NOT running correctly.")
            print("2. _last_supabase_state['updated_at'] already matches, so it doesn't broadcast.")
            print("3. Socket.IO connection issue between Server and Client.")
        else:
            print("Settings are EMPTY or NULL in Supabase for the active post.")

    except Exception as e:
        print(f"Diagnostic failed: {e}")

if __name__ == "__main__":
    check_broadcast_logic()
