import os
import json
import time
from typing import List, Dict, Any
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from datetime import datetime

class SeleniumCommentScraper:
    """Selenium을 사용한 네이버 카페 댓글 수집"""
    
    def __init__(self):
        self.driver = None
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.cookie_path = os.path.join(self.base_dir, "cookies.json")
    
    def login_to_naver(self) -> bool:
        """
        네이버 로그인 페이지를 열고 사용자가 로그인할 때까지 대기
        로그인이 완료되면 쿠키를 저장함
        """
        print("DEBUG: [Selenium] Starting manual login process...")
        try:
            # 로그인 시에는 headless 모드 해제해야 함
            options = webdriver.ChromeOptions()
            options.add_argument('--window-size=1920,1080')
            options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            # 샌드박스 비활성화 (권한 문제 방지)
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            
            self.driver = webdriver.Chrome(options=options)
            self.driver.get("https://nid.naver.com/nidlogin.login")
            
            print("INFO: 브라우저 창에서 로그인을 완료해 주세요. (60초 대기...)")
            
            # 로그인이 완료되었는지 확인 (URL 변화 또는 로그아웃 버튼 존재 여부 등)
            # 여기서는 URL이 nidlogin.login이 아니게 되거나 60초가 지날 때까지 대기
            start_time = time.time()
            logged_in = False
            
            while time.time() - start_time < 60:
                curr_url = self.driver.current_url
                if "nidlogin.login" not in curr_url and "naver.com" in curr_url:
                    # 로그인 완료로 간주 (간단한 체크)
                    logged_in = True
                    break
                time.sleep(1)
            
            if logged_in:
                print("DEBUG: [Selenium] Login detected. Saving cookies...")
                time.sleep(2) # 쿠키 안정화 대기
                cookies = self.driver.get_cookies()
                with open(self.cookie_path, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f)
                print(f"DEBUG: [Selenium] Cookies saved to {self.cookie_path}")
                return True
            else:
                print("DEBUG: [Selenium] Login timeout or cancelled.")
                return False
                
        except Exception as e:
            print(f"DEBUG: [Selenium] Login error: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None

    def _get_chrome_options(self, headless=True):
        """Chrome 옵션 설정"""
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless')  # 백그라운드 실행
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        return options
    
    def get_comments_from_browser(self, url: str, max_clicks: int = 20) -> List[Dict[str, Any]]:
        """
        브라우저를 통해 댓글 수집
        
        Args:
            url: 네이버 카페 게시글 URL
            max_clicks: "댓글 더보기" 최대 클릭 횟수
            
        Returns:
            댓글 리스트
        """
        print(f"DEBUG: [Selenium] Starting browser collection for {url}")
        
        try:
            options = self._get_chrome_options(headless=True)
            self.driver = webdriver.Chrome(options=options)
            
            # 쿠키 로드
            if os.path.exists(self.cookie_path):
                print(f"DEBUG: [Selenium] Loading cookies from {self.cookie_path}")
                # 쿠키를 넣으려면 먼저 도메인에 접속해야 함
                self.driver.get("https://cafe.naver.com/")
                with open(self.cookie_path, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    for cookie in cookies:
                        try:
                            self.driver.add_cookie(cookie)
                        except:
                            pass
            
            self.driver.get(url)
            
            # 페이지 로드 대기
            time.sleep(2)
            
            # 1. 메인 페이지에서 먼저 댓글 추출 시도 (v2 현대적 레이아웃)
            comments = self._extract_comments_from_dom()
            
            # 2. 메인에서 못 찾았다면 iframe 시도
            if not comments:
                try:
                    iframe = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.ID, "cafe_main"))
                    )
                    self.driver.switch_to.frame(iframe)
                    print("DEBUG: [Selenium] Switched to cafe_main iframe")
                    
                    # iframe 내부에서 더보기 클릭 및 추출
                    self._click_load_more_buttons(max_clicks)
                    self._handle_comment_pagination()
                    comments = self._extract_comments_from_dom()
                except TimeoutException:
                    print("DEBUG: [Selenium] No iframe found")
            else:
                # 메인에서 찾았다면 거기서 더보기 클릭 처리
                self._click_load_more_buttons(max_clicks)
                self._handle_comment_pagination()
                # 다시 추출 (더보기 클릭 후)
                comments = self._extract_comments_from_dom()
            
            print(f"DEBUG: [Selenium] Final extracted {len(comments)} comments from DOM")
            return comments
            
        except Exception as e:
            print(f"DEBUG: [Selenium] Error: {e}")
            import traceback
            traceback.print_exc()
            return []
            
        finally:
            if self.driver:
                self.driver.quit()
                self.driver = None
    
    def _click_load_more_buttons(self, max_clicks: int) -> int:
        """댓글 더보기 버튼 반복 클릭 (신형/구형 UI 대응)"""
        clicks = 0
        
        # 다양한 선택자 시도 (텍스트 기반 및 클래스 기반)
        selectors = [
            "//a[contains(@class, 'comment_area_more')]",
            "//a[contains(text(), '더보기')]",
            "//button[contains(@class, 'btn_more')]",
            "//a[contains(@class, 'more_view')]",
            "//span[contains(text(), '더보기')]/parent::a",
        ]
        
        for _ in range(max_clicks):
            clicked = False
            # 페이지 하단으로 스크롤하여 버튼 노출 유도
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.5)
            except:
                pass

            for selector in selectors:
                try:
                    button = self.driver.find_element(By.XPATH, selector)
                    if button.is_displayed():
                        # 일반 클릭이 안될 경우를 위해 JS 클릭 병행
                        try:
                            button.click()
                        except:
                            self.driver.execute_script("arguments[0].click();", button)
                        
                        clicks += 1
                        clicked = True
                        print(f"DEBUG: [Selenium] Clicked 'load more' button ({clicks})")
                        time.sleep(1.0)  # 로딩 대기시간 증가
                        break
                except :
                    continue
            
            if not clicked:
                break
        
        return clicks
    
    def _extract_comments_from_dom(self) -> List[Dict[str, Any]]:
        """DOM에서 댓글 요소 추출 (신형/구형 UI 통합)"""
        comments = []
        
        # 댓글 컨테이너 선택자 (v2 UI 위주로 강화)
        container_selectors = [
            "//li[contains(@class, 'CommentItem')]", # v2 신형
            "//div[contains(@class, 'CommentItem')]",
            "//div[@class='comment_box']",           # 구형
            "//ul[@class='comment_list']/li",
            "//div[contains(@class, 'comment_item')]",
        ]
        
        comment_elements = []
        for selector in container_selectors:
            try:
                elements = self.driver.find_elements(By.XPATH, selector)
                if len(elements) > len(comment_elements):
                    comment_elements = elements
                    print(f"DEBUG: [Selenium] Found {len(elements)} elements with selector: {selector}")
            except Exception:
                continue
        
        # [보강] 만약 li 개수가 적다면, 더 구체적인 v2 선택자로 재시도
        if len(comment_elements) < 5:
            try:
                v2_elements = self.driver.find_elements(By.CSS_SELECTOR, "li.CommentItem")
                if len(v2_elements) > len(comment_elements):
                    comment_elements = v2_elements
                    print(f"DEBUG: [Selenium] Found {len(v2_elements)} elements with CSS selector: li.CommentItem")
            except: pass
        
        # 각 댓글 요소에서 정보 추출
        for idx, element in enumerate(comment_elements):
            try:
                comment = self._parse_comment_element(element, idx)
                if comment and comment['content']: # 내용이 있는 것만
                    comments.append(comment)
            except Exception as e:
                continue
        
        return comments
    
    def _parse_comment_element(self, element, idx: int) -> Dict[str, Any]:
        """개별 댓글 요소 파싱 (신형 UI 대응)"""
        try:
            # [보강] 실제 네이버 댓글 ID 추출 시도
            # 보통 <li id="comment_12345678"> 또는 data-comment-id 속성에 있음
            real_id = None
            try:
                # [강화] 더 다양한 속성에서 진짜 ID 추출 시도
                elem_id = element.get_attribute("id") # comment_12345678
                if elem_id and "comment_" in elem_id:
                    real_id = elem_id.replace("comment_", "").strip()
                
                if not real_id:
                    # v2 신형 UI 및 기타 속성들
                    real_id = (
                        element.get_attribute("data-id") or 
                        element.get_attribute("data-comment-id") or
                        element.get_attribute("data-cid") or
                        element.get_attribute("commentid")
                    )
                
                if real_id:
                    print(f"DEBUG: [Selenium] Extracted real ID: {real_id}")
            except:
                pass


            # 작성자 닉네임
            nickname_selectors = [
                ".//a[contains(@class, 'comment_nickname')]",
                ".//span[@class='nick']",
                ".//em[contains(@class, 'nickname')]",
                ".//strong[contains(@class, 'name')]",
                ".//span[contains(@class, 'nickname')]",
            ]
            nickname = self._find_text(element, nickname_selectors, f"User{idx}")
            
            # 댓글 내용
            content_selectors = [
                ".//span[contains(@class, 'comment_content')]",
                ".//span[contains(@class, 'text_comment')]", # v2 보강
                ".//div[contains(@class, 'comment_text_view')]",
                ".//p[contains(@class, 'comment_text')]",
                ".//div[@class='comment_text']",
                ".//span[@class='text']",
            ]
            content = self._find_text(element, content_selectors, "")
            
            # 작성 시간
            date_selectors = [
                ".//span[contains(@class, 'comment_info_date')]",
                ".//span[@class='date']",
                ".//span[contains(@class, 'time')]",
            ]
            date_str = self._find_text(element, date_selectors, "")
            
            return {
                "comment_id": real_id if real_id else f"selenium_{idx}",

                "post_id": "",
                "author_nickname": nickname.strip(),
                "author_id": "",
                "content": content.strip(),
                "created_at": date_str,
                "is_deleted": False,
                "is_secret": False,
                "ref_comment_id": None,
                "source": "selenium"
            }
            
        except Exception as e:
            print(f"DEBUG: [Selenium] Parse error: {e}")
            return None
    
    def _find_text(self, element, selectors: List[str], default: str = "") -> str:
        """여러 선택자로 텍스트 찾기"""
        for selector in selectors:
            try:
                found = element.find_element(By.XPATH, selector)
                text = found.text.strip()
                if text:
                    return text
            except Exception:
                continue
        return default

    def _handle_comment_pagination(self):
        """댓글 페이지 번호(1, 2, 3...)가 있는 경우 처리"""
        page = 2
        while page <= 10: # 최대 10페이지까지만 (안전장치)
            try:
                # 다음 페이지 버튼 찾기 (v2 기준 클래스)
                page_xpath = f"//div[contains(@class, 'ArticlePaginate')]//button[text()=' {page} ']"
                next_page = self.driver.find_element(By.XPATH, page_xpath)
                
                # 현재 페이지가 아닐 때만 클릭
                if next_page.get_attribute("aria-pressed") == "false":
                    print(f"DEBUG: [Selenium] Clicking page {page}...")
                    self.driver.execute_script("arguments[0].click();", next_page)
                    time.sleep(1.5)
                    page += 1
                else:
                    break
            except NoSuchElementException:
                # 버튼이 없으면 텍스트 내용으로 다시 시도
                try:
                    alt_xpath = f"//a[contains(@class, 'button_comment_paginate') and text()='{page}']"
                    next_page = self.driver.find_element(By.XPATH, alt_xpath)
                    self.driver.execute_script("arguments[0].click();", next_page)
                    time.sleep(1.5)
                    page += 1
                except:
                    break
            except Exception as e:
                print(f"DEBUG: [Selenium] Pagination error: {e}")
                break
