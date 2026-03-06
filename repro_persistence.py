import os
import time
import sys
# Add current directory to sys.path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def test_persistence():
    db = CommentDatabase()
    test_url = "https://example.com/persistence_test_" + str(int(time.time()))
    
    print(f"Testing URL: {test_url}")
    
    # 1. Save initial data
    print("Step 1: Saving initial data...")
    db.save_data(test_url, {"User1": 1}, "id1", title="Initial Title", winners="Winner1")
    time.sleep(3) # Wait for sync
    
    # 2. Check if saved
    print("Step 2: Verifying data exists...")
    data = db.get_data(test_url)
    print(f"Loaded winners: {data[6]}") # winners is index 6
    
    # 3. Delete data
    print("Step 3: Deleting data...")
    db.clear_data(test_url)
    time.sleep(3) # Wait for cloud delete
    
    # 4. Try to load again
    print("Step 4: Loading after deletion...")
    data = db.get_data(test_url)
    print(f"Loaded winners after delete: {data[6]}")
    
    if data[6]:
        print("FAILED: Winners found after deletion!")
    else:
        print("SUCCESS: Winners are gone.")

def test_race_condition():
    db = CommentDatabase()
    test_url = "https://example.com/race_test_" + str(int(time.time()))
    
    print(f"\nTesting Race Condition for URL: {test_url}")
    
    # Start a sync and then clear
    print("Step 1: Saving and immediately clearing...")
    db.save_data(test_url, {"User1": 1}, "id1", title="Race Title", winners="RaceWinner")
    db.clear_data(test_url)
    
    print("Step 2: Waiting for background syncs to potentially finish...")
    time.sleep(5)
    
    # Check if data reappeared
    print("Step 3: Checking if data reappeared...")
    data = db.get_data(test_url)
    print(f"Loaded winners: {data[6]}")
    
    if data[6]:
        print("FAILED: Race condition caused data to reappear!")
    else:
        print("SUCCESS: Data stayed deleted.")

if __name__ == "__main__":
    test_persistence()
    test_race_condition()
