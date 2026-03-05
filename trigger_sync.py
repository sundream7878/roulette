from standalone_comment_monitor.db_handler import CommentDatabase

db = CommentDatabase()
url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67899"

# 로컬 데이터를 가져와서 강제로 Supabase에 동기화
# NEW ORDER: participants, last_id, all_commenters, title, prizes, memo, winners, allow_duplicates, allowed_list
data = db.get_data(url)
participants, last_id, commenters = data[0], data[1], data[2]
title, prizes, memo, winners = data[3], data[4], data[5], data[6]
allow_duplicates, allowed_list = data[7], data[8]

print(f"Triggering sync for {url}")
print(f"  Title: {title}")
print(f"  Prizes: {prizes}")
print(f"  Allowed List: {len(allowed_list) if allowed_list else 'None'}")
print(f"  Participants: {len(participants)}")
print(f"  Commenters: {len(commenters)}")
print(f"  Last ID: {last_id}")

# save_data 호출 (이제 내부에서 로컬 데이터를 보완하여 Supabase로 보냄)
db.save_data(url, participants, last_id, commenters, title, prizes, memo, winners, allow_duplicates, allowed_list)

import time
print("Waiting 10s for background sync thread to finish...")
time.sleep(10)
print("Done.")
