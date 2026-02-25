# 설치 및 사용 가이드

## 1. 의존성 설치

```bash
pip install selenium==4.15.2
```

## 2. ChromeDriver 설치

### Windows
1. Chrome 버전 확인: `chrome://version/`
2. [ChromeDriver 다운로드](https://chromedriver.chromium.org/downloads)
3. 다운로드한 `chromedriver.exe`를 다음 중 하나에 배치:
   - `f:\roulette-1\` (프로젝트 폴더)
   - `C:\Windows\System32\` (시스템 PATH)

### 설치 확인
```bash
chromedriver --version
```

## 3. 서버 재시작

```bash
# 기존 서버 종료 (Ctrl+C)
python comment_dart.py
```

## 4. 테스트

1. 브라우저에서 `http://localhost:5000/monitor_page` 접속
2. 테스트 URL 입력: `https://cafe.naver.com/f-e/cafes/27870803/articles/67767`
3. "참가자 수집" 클릭
4. 터미널에서 로그 확인:

```
DEBUG: [Strategy] Trying multiple API approaches...
DEBUG: [API Result] Collected 12 comments via API
DEBUG: [Selenium Fallback] API collected only 12 comments, trying Selenium...
DEBUG: [Selenium] Extracted 44 comments from DOM
DEBUG: [Merge Result] Total unique comments: 44
```

## 5. Selenium 없이 사용 (선택사항)

ChromeDriver를 설치하지 않으려면 API 전략만 사용:

`scraper.py` 수정:
```python
# 19번 줄
def __init__(self, user_agent: str = None, use_selenium: bool = False):  # False로 변경
```

---

## 문제 해결

### ChromeDriver 버전 불일치
```
SessionNotCreatedException: session not created: This version of ChromeDriver only supports Chrome version XX
```
**해결**: Chrome 버전과 일치하는 ChromeDriver 다운로드

### ChromeDriver를 찾을 수 없음
```
WebDriverException: 'chromedriver' executable needs to be in PATH
```
**해결**: ChromeDriver를 PATH에 추가하거나 프로젝트 폴더에 배치

### Selenium 설치 안 됨
```
ModuleNotFoundError: No module named 'selenium'
```
**해결**: `pip install selenium==4.15.2` 실행
