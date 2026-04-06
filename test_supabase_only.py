import os
import sys
import time
from datetime import datetime
# Add current directory to sys.path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def test_supabase_direct():
    db = CommentDatabase()
    test_url = "https://example.com/supabase_only_test_" + str(int(time.time()))
    
    print(f"Testing Supabase-Only CRUD for URL: {test_url}")
    
    # 1. Save data
    print("Step 1: Saving data directly to Supabase...")
    db.save_data(
        url=test_url,
        participants_dict={"Tester1": 2, "Tester2": 1},
        last_comment_id="test_id_123",
        all_commenters=[{"name": "Tester1", "created_at": "2026-03-06T10:00:00"}, {"name": "Tester2", "created_at": "2026-03-06T10:01:00"}],
        title="Supabase Only Title",
        prizes="Prize 1, Prize 2",
        memo="Memo text",
        winners="WinnerX",
        allow_duplicates=False,
        allowed_list="Tester1,2\nTester2,1"
    )
    
    # 2. Get data back
    print("Step 2: Fetching data back from Supabase...")
    # Wait a bit for eventual consistency if necessary (though our sync is now synchronous-ish with retries)
    time.sleep(2)
    
    participants, last_id, all_c, title, prizes, memo, winners, allow_dup, allowed_list, _ = db.get_data(test_url)
    
    print(f"Fetched Title: {title}")
    print(f"Fetched Winners: {winners}")
    print(f"Participants count: {len(participants)}")
    print(f"Allow Duplicates: {allow_dup}")
    
    success = True
    if title != "Supabase Only Title": success = False
    if winners != "WinnerX": success = False
    if len(participants) != 2: success = False
    if allow_dup is not True and allow_dup is False: pass # Should be False
    else: success = False # It was set to False
    
    if success:
        print("SUCCESS: Supabase-only CRUD verified.")
    else:
        print("FAILED: Data mismatch or missing.")

    # 3. Test clear
    print("Step 3: Testing clear_data...")
    db.clear_data(test_url)
    time.sleep(2)
    _, _, _, title_after, _, _, _, _, _, _ = db.get_data(test_url)
    if title_after is None:
        print("SUCCESS: Data cleared from Supabase.")
    else:
        print(f"FAILED: Data still exists after clear! Title: {title_after}")

if __name__ == "__main__":
    test_supabase_direct()
