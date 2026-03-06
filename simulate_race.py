import os
import time
import sys
from datetime import datetime
# Add current directory to sys.path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def simulate_race():
    db = CommentDatabase()
    test_url = "https://example.com/race_sim_" + str(int(time.time()))
    
    print(f"Simulating Race for URL: {test_url}")
    
    # 1. Start a "stale" job with an old timestamp
    old_time = datetime(2020, 1, 1) # Very old
    print("Step 1: Manually triggering a sync job with timestamp from 2020...")
    
    # This simulates a thread that was stuck and finally runs
    db._sync_to_supabase(test_url, {}, "id_old", title="OLD TITLE", winners="GhostWinner", job_timestamp=old_time)
    
    # 2. Immediately create a "fresh" record locally
    print("Step 2: Creating a fresh local record NOW...")
    db.save_data(test_url, {}, "id_new", title="NEW TITLE", winners="")
    
    # 3. Wait for the background thread
    print("Step 3: Waiting for background thread to potentially overwrite...")
    time.sleep(5)
    
    # 4. Check results
    print("Step 4: Checking data...")
    # Checking Supabase directly if possible, or just checking if get_data pulls it back
    data = db.get_data(test_url)
    print(f"Loaded title: '{data[3]}'")
    print(f"Loaded winners: '{data[6]}'")
    
    if data[3] == "OLD TITLE":
        print("FAILED: Stale sync job overwrote the new data!")
    else:
        print("SUCCESS: New data was protected from the stale sync job.")

if __name__ == "__main__":
    simulate_race()
