import time
from scraper import NaverCommentMonitor

def main():
    # 테스트할 게시글 URL (실제 존재하는 공개 게시글 URL을 넣으세요)
    # 예: 카페 게시글 예시 URL
    target_url = input("모니터링할 네이버 카페 게시글 URL을 입력하세요: ").strip()
    
    if not target_url:
        print("URL이 입력되지 않았습니다.")
        return

    # 모니터 인스턴스 생성
    monitor = NaverCommentMonitor()
    
    # 상태 변수 (마지막으로 읽은 댓글 ID)
    # 처음에는 None으로 시작하여 모든(혹은 최신) 댓글을 긁어오거나,
    # 특정 ID를 지정하여 그 이후부터 긁어올 수 있습니다.
    last_known_id = None
    
    print("-" * 50)
    print(f"모니터링 시작: {target_url}")
    print("Ctrl+C를 누르면 종료됩니다.")
    print("-" * 50)

    try:
        while True:
            print(f"\n[Check] {time.strftime('%H:%M:%S')} - 새로운 댓글 확인 중...")
            
            # 핵심 함수 호출
            comments = monitor.get_new_comments(target_url, last_comment_id=last_known_id)
            
            if comments:
                print(f"✨ 새로운 댓글 {len(comments)}개 발견!")
                for cmt in comments:
                    print(f"  - [ID:{cmt['comment_id']}] {cmt['author_nickname']}: {cmt['content'][:30]}...")
                
                # 커서 업데이트 (가장 마지막에 있는 댓글이 가장 최신 댓글임)
                last_known_id = comments[-1]['comment_id']
                print(f"  -> 마지막 수집 ID 갱신: {last_known_id}")
            else:
                print("  - 새로운 댓글 없음.")
            
            # 다음 확인까지 대기 (테스트용 10초, 실제 서비스는 60초 이상 권장)
            time.sleep(10)
            
    except KeyboardInterrupt:
        print("\n모니터링을 종료합니다.")
    except Exception as e:
        print(f"\n오류 발생: {e}")

if __name__ == "__main__":
    main()
