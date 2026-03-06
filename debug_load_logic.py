import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from standalone_comment_monitor.db_handler import CommentDatabase
from monitor_view import normalize_url

def debug_load():
    db = CommentDatabase()
    # Replace with the URL the user is likely using (from check_counts.py)
    urls = db.get_all_urls()
    if not urls:
        print("No URLs in DB")
        return
        
    for url in urls:
        norm_url = normalize_url(url)
        print(f"Testing URL: {url}")
        print(f"Normalized:  {norm_url}")
        
        p_dict, last_id, all_c, title, prizes, memo, winners, allow_dup, allowed_list = db.get_data(norm_url)
        
        print(f"  Participants: {len(p_dict)}")
        print(f"  Commenters:   {len(all_c)}")
        print(f"  Title:        {title}")
        print("-" * 20)

if __name__ == "__main__":
    debug_load()
