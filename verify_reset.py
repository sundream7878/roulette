import os
import time
import sys
from datetime import datetime
# Add current directory to sys.path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def test_reset_persistence():
    db = CommentDatabase()
    test_url = "https://example.com/reset_test_" + str(int(time.time()))
    
    print(f"Testing Reset Persistence for URL: {test_url}")
    
    # 1. Save initial winners
    print("Step 1: Saving initial winners...")
    db.save_data(test_url, {"User1": 1}, "id1", title="Initial Title", winners="OldWinner1,OldWinner2")
    time.sleep(2)
    
    # 2. Reset winners (set to empty string)
    print("Step 2: Resetting winners to empty string...")
    db.save_data(test_url, {"User1": 1}, "id1", title="Initial Title", winners="")
    
    # 3. Simulate a stale cloud pull by calling get_data
    # In a real scenario, Supabase might still have the old winners if the sync hasn't finished
    # but my new get_data should prefer the local empty string over cloud values IF local is newer.
    print("Step 3: Loading data (should remain empty)...")
    data = db.get_data(test_url)
    loaded_winners = data[6] # index 6 is winners
    print(f"Loaded winners: '{loaded_winners}'")
    
    if loaded_winners == "OldWinner1,OldWinner2":
        print("FAILED: Old winners were pulled back!")
    elif loaded_winners == "":
        print("SUCCESS: Empty winners were preserved.")
    else:
        print(f"Unexpected result: '{loaded_winners}'")

if __name__ == "__main__":
    test_reset_persistence()
