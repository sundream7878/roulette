import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase

def verify_sqlite():
    print("Testing SQLite Migration...")
    db = CommentDatabase()
    
    test_url = "https://cafe.naver.com/test/12345"
    participants = {"User1": (1, "2026-03-06T12:00:00"), "User2": (2, None)}
    all_commenters = [{"name": "User1", "created_at": "2026-03-06T12:00:00"}, "User2", "User3"]
    
    print(f"Saving test data for {test_url}...")
    db.save_data(
        url=test_url,
        participants_dict=participants,
        last_comment_id="last_123",
        all_commenters=all_commenters,
        title="Test Event",
        prizes="Prize 1",
        memo="Test Memo",
        allow_duplicates=True
    )
    
    print("Retrieving data...")
    p, last_id, all_c, title, prizes, memo, winners, allow_dup, allowed_list = db.get_data(test_url)
    
    print(f"Results:")
    print(f"  Title: {title}")
    print(f"  Participants: {len(p)}")
    print(f"  Commenters: {len(all_c)}")
    print(f"  Last ID: {last_id}")
    
    if len(p) == 2 and title == "Test Event":
        print("\nSUCCESS: SQLite verified.")
    else:
        print("\nFAILURE: Data mismatch.")

if __name__ == "__main__":
    verify_sqlite()
