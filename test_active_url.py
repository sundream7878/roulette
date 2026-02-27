from standalone_comment_monitor.db_handler import CommentDatabase

print("Instantiating database...")
db = CommentDatabase()

print("Setting active URL to 'test_sync_url_2'...")
db.set_active_url('test_sync_url_2')

active = db.get_active_url()
print(f"Active URL from DB is: {active}")
