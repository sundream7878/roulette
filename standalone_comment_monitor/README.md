# 네이버 카페 댓글 모니터링 모듈

이 모듈은 네이버 카페 게시글의 새로운 댓글을 주기적으로 수집(모니터링)하기 위해 만들어진 독립형 파이썬 패키지입니다.
UI나 데이터베이스 없이 순수하게 데이터를 가져오는 역할만 수행하므로, 게임 서버나 웹 서비스의 백엔드에 쉽게 통합할 수 있습니다.

## 📋 특징
- **의존성 최소화**: `requests` 라이브러리만 사용
- **상태 관리**: 마지막 수집한 `comment_id`를 넣으면, 그 이후의 새 댓글만 가져옴
- **중복 방지**: 페이지네이션 및 ID 비교를 통한 중복 데이터 필터링 내장
- **데이터 정규화**: 딕셔너리 형태의 깔끔한 데이터 반환

## 📦 설치
필요한 라이브러리를 설치합니다.
```bash
pip install -r requirements.txt
```

## 🚀 사용 예시 (Usage)

```python
import time
from standalone_comment_monitor import NaverCommentMonitor

def main():
    # 1. 모니터링할 게시글 URL
    target_url = "https://cafe.naver.com/somecafe/123456"
    
    # 2. 모니터 초기화
    monitor = NaverCommentMonitor()
    
    # 3. 마지막 수집 지점 (DB 등에서 불러왔다고 가정)
    last_known_id = None 
    # last_known_id = "12345" # 이 ID 이후의 댓글만 가져옵니다.

    print(f"Monitoring start: {target_url}")

    while True:
        try:
            # 새로운 댓글 수집
            new_comments = monitor.get_new_comments(target_url, last_comment_id=last_known_id)
            
            if new_comments:
                print(f"Found {len(new_comments)} new comments!")
                
                for cmt in new_comments:
                    print(f"[{cmt['created_at']}] {cmt['author_nickname']}: {cmt['content']}")
                    
                    # 마지막 ID 갱신 (가장 최신 댓글이 리스트의 마지막에 있음)
                    last_known_id = cmt['comment_id']
                
                # 실전에서는 여기서 last_known_id를 DB에 저장하거나
                # 게임 서버로 알림(Webhook)을 발송하면 됩니다.
            else:
                print("No new comments.")

        except Exception as e:
            print(f"Error: {e}")

        # 주기적 실행 (예: 60초마다)
        time.sleep(60)

if __name__ == "__main__":
    main()
```

## 📂 파일 구조
- `scraper.py`: 핵심 로직 (API 호출, 페이지네이션, 필터링)
- `parsers.py`: URL 파싱 유틸리티
- `requirements.txt`: 필요 라이브러리 목록
- `example.py`: 실행 가능한 예제 코드
