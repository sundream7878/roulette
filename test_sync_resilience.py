import sys, os
sys.path.insert(0, 'f:/roulette-1')
os.chdir('f:/roulette-1')

from standalone_comment_monitor.db_handler import CommentDatabase
import time

db = CommentDatabase()

# test_resilience URL에 대해 title과 memo를 동시에 저장 시도
# memo 컬럼은 Supabase에 없으므로 (아직 안만들었다면) 에러가 나겠지만,
# 코드 수정으로 인해 memo를 제외하고 title은 저장되어야 함.

test_url = "https://cafe.naver.com/test_resilience"
test_title = f"Resilience Test {int(time.time())}"
test_memo = "This column might be missing"

print(f"Testing save_data with missing column (memo) for URL: {test_url}")
db.save_data(test_url, None, "", title=test_title, memo=test_memo)

print("Waiting for background sync...")
time.sleep(5)

# Supabase에서 데이터 확인
if db.supabase:
    res = db.supabase.table("posts").select("*").eq("url", test_url).execute()
    if res.data:
        print("Success! Data in Supabase:", res.data)
        if res.data[0].get("title") == test_title:
            print("Verified: Title was updated successfully despite missing memo column.")
        else:
            print("Failed: Title was not updated.")
    else:
        print("Failed: No data found in Supabase for the test URL.")
else:
    print("Error: Supabase not connected.")
