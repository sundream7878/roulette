import sqlite3
import os
import re
from urllib.parse import urlparse, parse_qs

base_dir = r"f:\roulette-1\standalone_comment_monitor"
db_path = os.path.join(base_dir, "comments.db")

def parse_ids(url):
    if "ArticleRead.nhn" in url:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        clubid = query.get("clubid", [None])[0]
        articleid = query.get("articleid", [None])[0]
        if clubid and articleid:
            return str(clubid), str(articleid)
    match = re.search(r'cafes/(\d+)/articles/(\d+)', url)
    if match:
        return match.group(1), match.group(2)
    return None, None

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT url, title, prizes, winners, allow_duplicates, last_comment_id FROM posts")
rows = cursor.fetchall()

print(f"Total posts found: {len(rows)}")

normalized_data = {}

for url, title, prizes, winners, allow_duplicates, last_comment_id in rows:
    clubid, articleid = parse_ids(url)
    if not clubid or not articleid:
        print(f"Skipping non-standardizable URL: {url}")
        continue
    
    norm_url = f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
    
    if norm_url not in normalized_data:
        normalized_data[norm_url] = {
            'title': title,
            'prizes': prizes,
            'winners': winners,
            'allow_duplicates': allow_duplicates,
            'last_comment_id': last_comment_id
        }
    else:
        # Merge - prefer non-None values
        if not normalized_data[norm_url]['title']: normalized_data[norm_url]['title'] = title
        if not normalized_data[norm_url]['prizes']: normalized_data[norm_url]['prizes'] = prizes
        if not normalized_data[norm_url]['winners']: normalized_data[norm_url]['winners'] = winners
        if not normalized_data[norm_url]['last_comment_id'] or (last_comment_id and len(last_comment_id) > len(normalized_data[norm_url]['last_comment_id'])):
             normalized_data[norm_url]['last_comment_id'] = last_comment_id

print(f"Normalized posts count: {len(normalized_data)}")

for url, data in normalized_data.items():
    print(f"Updating/Merging: {url}")
    # Update main record
    cursor.execute('''
        INSERT INTO posts (url, title, prizes, winners, allow_duplicates, last_comment_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            title = COALESCE(excluded.title, posts.title),
            prizes = COALESCE(excluded.prizes, posts.prizes),
            winners = COALESCE(excluded.winners, posts.winners),
            allow_duplicates = COALESCE(excluded.allow_duplicates, posts.allow_duplicates),
            last_comment_id = CASE WHEN excluded.last_comment_id != '' THEN excluded.last_comment_id ELSE posts.last_comment_id END
    ''', (url, data['title'], data['prizes'], data['winners'], data['allow_duplicates'], data['last_comment_id']))

    # We also need to move participants and commenters if they exist under the old URL
    # But for simplicity, we focus on metadata first. 
    # Let's also clean up old noisy URLs that are NOT the canonical one.

for url, _, _, _, _, _ in rows:
    clubid, articleid = parse_ids(url)
    if clubid and articleid:
        norm_url = f"https://cafe.naver.com/ca-fe/web/cafes/{clubid}/articles/{articleid}"
        if url != norm_url:
            print(f"Deleting noisy duplicate: {url}")
            cursor.execute("DELETE FROM posts WHERE url = ?", (url,))
            # We should ideally move foreign keys but sqlite might handle cascade if it was enabled, 
            # though here it's easier to just keep canonical files. 

conn.commit()
conn.close()
print("Migration completed.")
