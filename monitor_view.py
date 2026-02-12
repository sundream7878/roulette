import os
import time
from flask import Blueprint, render_template, request, jsonify
from standalone_comment_monitor.scraper import NaverCommentMonitor

monitor_bp = Blueprint('monitor', __name__)
monitor_instance = NaverCommentMonitor()

# 참가자 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARTICIPANTS_FILE = os.path.join(BASE_DIR, 'participants.txt')

@monitor_bp.route('/monitor_page')
def monitor_page():
    return render_template('monitor.html')

@monitor_bp.route('/api/fetch_comments', methods=['POST'])
def fetch_comments():
    data = request.json
    url = data.get('url')
    
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
    
    try:
        print(f"DEBUG: Fetching comments for URL: {url}")
        # 댓글 가져오기
        comments = monitor_instance.get_new_comments(url)
        print(f"DEBUG: Found {len(comments) if comments else 0} comments")
        
        if not comments:
            return jsonify({'message': '새로운 댓글이 없습니다.', 'count': 0})

        # 아이디 추출 및 댓글 개수 카운트 (중복 제거하되 개수는 세기)
        participant_counts = {}
        for comment in comments:
            writer = comment.get('author_nickname') or comment.get('author_id')
            if writer and writer != 'None':
                participant_counts[writer] = participant_counts.get(writer, 0) + 1

        print(f"DEBUG: Extracted {len(participant_counts)} unique participants")
        print(f"DEBUG: Participant counts: {participant_counts}")

        if not participant_counts:
            return jsonify({'message': '수집된 유효한 참가자가 없습니다.', 'participants': []})

        # participants.txt에 저장 (이름과 댓글 개수)
        with open(PARTICIPANTS_FILE, 'a', encoding='utf-8') as f:
            for name, count in participant_counts.items():
                f.write(f"{name} {count}\n")

        # 결과 포맷팅
        participant_list = [f"{name} ({count}개)" for name, count in participant_counts.items()]

        return jsonify({
            'message': f'{len(participant_counts)}명의 참가자가 추가되었습니다. (총 댓글: {sum(participant_counts.values())}개)',
            'participants': participant_list,
            'total_comments': sum(participant_counts.values())
        })

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"DEBUG: Error occurred:\n{error_details}")
        return jsonify({'error': str(e), 'details': error_details}), 500
