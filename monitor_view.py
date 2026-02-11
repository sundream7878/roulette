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
        # 댓글 가져오기 (last_comment_id 없이 전체 또는 최신 가져오기)
        # 모듈의 구현에 따라 인자 조절 필요
        comments = monitor_instance.get_new_comments(url)
        
        if not comments:
            return jsonify({'message': '새로운 댓글이 없습니다.', 'count': 0})

        # 아이디 추출 및 저장 (중복 제거)
        new_participants = set()
        for comment in comments:
            # comment 객체의 구조에 따라 수정 (예: comment['writer_id'])
            writer = comment.get('nickname') or comment.get('writer_id')
            if writer:
                new_participants.add(writer)

        # participants.txt에 저장 (기존 파일에 추가 또는 덮어쓰기 선택 가능)
        # 여기서는 단순하게 '이름 1' 형식으로 저장한다고 가정
        with open(PARTICIPANTS_FILE, 'a', encoding='utf-8') as f:
            for name in new_participants:
                f.write(f"{name} 1\n")

        return jsonify({
            'message': f'{len(new_participants)}명의 참가자가 추가되었습니다.',
            'participants': list(new_participants)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500
