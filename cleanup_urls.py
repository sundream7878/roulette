import sqlite3
import os

def cleanup_db():
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "standalone_comment_monitor")
    db_path = os.path.join(base_dir, "comments.db")
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # URL 정규화 및 데이터 마이그레이션
    cursor.execute("SELECT url FROM posts")
    urls = cursor.fetchall()
    
    for (url,) in urls:
        if '\n' in url or ' ' in url:
            new_url = url.strip().replace('\n', '').replace('\r', '')
            print(f"Fixing URL: {repr(url)} -> {repr(new_url)}")
            
            try:
                # 1. posts 테이블 업데이트 (이미 존재하면 머지)
                cursor.execute("SELECT url FROM posts WHERE url = ?", (new_url,))
                if cursor.fetchone() and new_url != url:
                    # 이미 존재하면 현재 데이터를 머지하거나 삭제 (나중에 복구됨)
                    print(f"Conflict found for {new_url}, merging...")
                    # 덮어쓰기 전략: 새로운 URL의 데이터를 유지하고 구 데이터를 삭제
                    cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
                else:
                    cursor.execute("UPDATE posts SET url = ? WHERE url = ?", (new_url, url))
                
                # 2. 관련 테이블 업데이트
                cursor.execute("UPDATE participants SET url = ? WHERE url = ?", (new_url, url))
                cursor.execute("UPDATE commenters SET url = ? WHERE url = ?", (new_url, url))
            except Exception as e:
                print(f"Error fixing {url}: {e}")
    
    conn.commit()
    print("Cleanup complete.")
    conn.close()

if __name__ == "__main__":
    cleanup_db()
