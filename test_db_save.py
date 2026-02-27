from standalone_comment_monitor.db_handler import CommentDatabase

db = CommentDatabase()
print("Initialized.")
try:
    db.save_data(
        url="test_sync_url_3",
        participants_dict=None,
        last_comment_id="",
        title="My Title 3",
        prizes="Prize 3",
        allow_duplicates=True
    )
    print("Done")
except Exception as e:
    print(f"Error: {e}")
