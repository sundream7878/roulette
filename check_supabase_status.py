from standalone_comment_monitor.db_handler import CommentDatabase
import os

db = CommentDatabase()
url = "https://cafe.naver.com/ca-fe/web/cafes/27870803/articles/67357"

if db.supabase:
    # Check commenters
    c_res = db.supabase.table('commenters').select('author', count='exact').eq('url', url).execute()
    total_count = c_res.count if hasattr(c_res, 'count') else (len(c_res.data) if c_res.data else 0)
    print(f"Supabase Total Commenters for {url}: {total_count}")
    
    # Check participants
    p_res = db.supabase.table('participants').select('author', count='exact').eq('url', url).execute()
    p_count = p_res.count if hasattr(p_res, 'count') else (len(p_res.data) if p_res.data else 0)
    print(f"Supabase Confirmed Participants for {url}: {p_count}")
else:
    print("Supabase not configured.")
