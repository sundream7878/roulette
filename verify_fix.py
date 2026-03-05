import os
import sys
from datetime import datetime
from dotenv import load_dotenv

# Path adjust
sys.path.append(os.path.join(os.getcwd(), 'standalone_comment_monitor'))
from db_handler import CommentDatabase

load_dotenv()

db = CommentDatabase()
url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67482"

print(f"--- 1. 현재 데이터 확인 (Local Only) ---")
data = db.get_data(url, local_only=True)
print(f"현재 제목: {data[3]}")
print(f"현재 메모: {data[5]}")
print(f"현재 당첨자: {data[6]}")

print(f"\n--- 2. 부분 업데이트 테스트 (메모만 수정) ---")
test_memo = f"수정 테스트 세션: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
# title, prizes 등을 None으로 전달하여 로직이 로컬에서 보존하는지 확인
db.save_data(url, participants_dict=None, last_comment_id=None, memo=test_memo)

print(f"\n--- 3. 업데이트 결과 확인 ---")
# 잠시 대기 (비동기 싱크용)
import time
time.sleep(3)

new_data = db.get_data(url, local_only=True)
print(f"업데이트된 메모: {new_data[5]}")
print(f"보존된 제목: {new_data[3]}")
print(f"보존된 당첨자: {new_data[6]}")

if test_memo == new_data[5] and new_data[3] == data[3]:
    print("\n✅ 로컬 저장 및 필드 보존 성공!")
else:
    print("\n❌ 필드 보존 실패!")

print("\n--- 4. Supabase 실시간 확인 ---")
if db.supabase:
    res = db.supabase.table("posts").select("*").eq("url", url).execute()
    if res.data:
        post = res.data[0]
        print(f"Supabase 메모: {post.get('memo')}")
        if post.get('memo') == test_memo:
            print("✅ Supabase 동기화 성공!")
        else:
            print("❌ Supabase 데이터 불일치!")
    else:
        print("❌ Supabase에서 포스트를 찾을 수 없음!")
