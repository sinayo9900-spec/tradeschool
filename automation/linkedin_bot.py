import asyncio
import random
import re
import os
from pathlib import Path
from urllib.parse import urlparse, quote
from playwright.async_api import async_playwright, Page, BrowserContext

BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_STATE_DIR = BASE_DIR / "browser_state"

# 프로필 상단 섹션 셀렉터 (data-member-id가 있는 section)
PROFILE_SECTION = "section[data-member-id]"
# 촌수 배지
DIST_BADGE = "span.dist-value"
# 프로필 액션 버튼 영역 (.entry-point 내부)
ACTION_AREA = ".entry-point"


class LinkedInBot:
    def __init__(self, config):
        self.config = config
        self.playwright = None
        self.browser = None
        self.context: BrowserContext = None
        self.page: Page = None

    async def start(self, headless=False):
        """Playwright 브라우저를 시작한다."""
        self.playwright = await async_playwright().start()
        BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
        profile_dir = str(BROWSER_STATE_DIR / "profile")

        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=headless,
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        print("[*] 브라우저 세션을 로드했습니다.")

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def close(self):
        """브라우저를 종료한다. 세션은 user_data_dir에 자동 저장된다."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def login(self):
        """브라우저를 열어 사용자가 직접 로그인하도록 한다."""
        await self.start(headless=False)
        await self.page.goto("https://www.linkedin.com/login")

        print("=" * 50)
        print("브라우저에서 LinkedIn에 로그인해주세요.")
        print("로그인 완료 후 이 터미널에서 Enter를 누르세요.")
        print("=" * 50)

        await asyncio.get_event_loop().run_in_executor(None, input)

        # 로그인 확인
        current_url = self.page.url
        if "feed" in current_url or "mynetwork" in current_url:
            print("[+] 로그인 성공! 세션을 저장합니다.")
        else:
            print(f"[!] 현재 URL: {current_url}")
            print("[!] 로그인이 완료되지 않은 것 같습니다. 그래도 세션을 저장합니다.")

        await self.close()
        print("[+] 세션 저장 완료. 이제 send.py를 실행할 수 있습니다.")

    async def check_session(self) -> bool:
        """저장된 세션이 유효한지 확인한다."""
        try:
            await self.page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=15000)
            await self.page.wait_for_timeout(2000)

            if "login" in self.page.url or "checkpoint" in self.page.url:
                return False
            return True
        except Exception:
            return False

    async def is_connected(self, profile_url: str) -> str:
        """
        프로필 페이지에서 연결 상태를 확인한다.
        span.dist-value 텍스트로 판별: "1촌"/"1st" = connected, "2촌"/"2nd" 등 = not_connected
        Returns: "connected", "not_connected", "pending", "unknown"
        """
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(3000)

        # span.dist-value 에서 촌수 읽기
        dist = self.page.locator(f"{PROFILE_SECTION} {DIST_BADGE}").first
        if await dist.count():
            dist_text = (await dist.text_content()).strip()
            print(f"  [DEBUG] 촌수: {dist_text}")

            if dist_text in ("1촌", "1st"):
                return "connected"
            if dist_text in ("2촌", "2nd", "3촌 이상", "3rd+", "3촌", "3rd"):
                return "not_connected"

        # 보류 확인 — 프로필 액션 영역에서 Pending/보류 버튼
        section = self.page.locator(PROFILE_SECTION)
        section_text = await section.text_content() if await section.count() else ""
        if "Pending" in section_text or "보류" in section_text:
            return "pending"

        # 디버그: 스크린샷 저장
        debug_path = BROWSER_STATE_DIR / "debug_profile.png"
        await self.page.screenshot(path=str(debug_path))
        print(f"  [DEBUG] 프로필 스크린샷 저장: {debug_path}")

        return "unknown"

    async def send_connection_request(self, profile_url: str, note: str) -> bool:
        """커넥션 요청을 보낸다 (노트 포함)."""
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(2000)

        try:
            section = self.page.locator(PROFILE_SECTION)

            # 프로필 섹션 내 Connect / 1촌 맺기 버튼 찾기
            connect_btn = None
            for selector in [
                "button[aria-label*='Connect']",
                "button[aria-label*='1촌 맺기']",
                f"{ACTION_AREA} button:has-text('Connect')",
                f"{ACTION_AREA} button:has-text('1촌 맺기')",
            ]:
                btn = section.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    connect_btn = btn
                    break

            # 추가 메뉴(더보기) 안에 숨어있을 수 있음
            if not connect_btn:
                more_btn = section.locator("button[aria-label='추가 메뉴'], button[aria-label*='More action']").first
                if await more_btn.count() and await more_btn.is_visible():
                    await more_btn.click()
                    await self.page.wait_for_timeout(500)
                    for sel in [
                        "div[aria-label*='Connect']",
                        "div[aria-label*='1촌 맺기']",
                    ]:
                        btn = self.page.locator(sel).first
                        if await btn.count() and await btn.is_visible():
                            connect_btn = btn
                            break

            if not connect_btn:
                print("  [!] Connect 버튼을 찾을 수 없습니다.")
                return False

            await connect_btn.click()
            await self.page.wait_for_timeout(1000)

            # "Add a note" / "메모 추가" 버튼 클릭
            add_note_btn = None
            for selector in [
                "button:has-text('Add a note')",
                "button:has-text('메모 추가')",
                "button:has-text('노트 추가')",
            ]:
                btn = self.page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    add_note_btn = btn
                    break

            if add_note_btn:
                await add_note_btn.click()
                await self.page.wait_for_timeout(500)

                # 노트 입력 (300자 제한)
                truncated_note = note[:300]
                textarea = self.page.locator("textarea").first
                await self.paste_text(textarea, truncated_note)
                await self.page.wait_for_timeout(500)

            # 전송 버튼 클릭
            send_btn = None
            for selector in [
                "button[aria-label*='Send']",
                "button[aria-label*='보내기']",
                "button:has-text('Send')",
                "button:has-text('보내기')",
            ]:
                btn = self.page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    send_btn = btn
                    break

            if not send_btn:
                print("  [!] Send 버튼을 찾을 수 없습니다.")
                return False

            await send_btn.click()
            await self.page.wait_for_timeout(2000)

            print(f"  [+] 커넥션 요청 전송 완료")
            return True

        except Exception as e:
            print(f"  [!] 커넥션 요청 실패: {e}")
            return False

    async def send_direct_message(self, profile_url: str, message: str) -> bool:
        """이미 연결된 사용자에게 다이렉트 메시지를 보낸다."""
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(2000)

        try:
            # 프로필 섹션 내 메시지 보내기 버튼 클릭
            section = self.page.locator(PROFILE_SECTION)
            message_btn = None
            for selector in [
                "button[aria-label*='메시지 보내기']",
                "button[aria-label*='Message']",
                f"{ACTION_AREA} button:has-text('메시지 보내기')",
                f"{ACTION_AREA} button:has-text('Message')",
            ]:
                btn = section.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    message_btn = btn
                    break

            if not message_btn:
                print("  [!] 메시지 버튼을 찾을 수 없습니다.")
                return False

            await message_btn.click()
            await self.page.wait_for_timeout(2000)

            # 메시지 입력 영역 찾기
            msg_box = self.page.locator("div.msg-form__contenteditable[contenteditable='true']").first
            if not await msg_box.is_visible():
                msg_box = self.page.locator("[role='textbox']").first

            await msg_box.click()
            await self.page.wait_for_timeout(300)
            await self.paste_text(msg_box, message)
            await self.page.wait_for_timeout(500)

            # 전송
            send_btn = None
            for selector in [
                "button.msg-form__send-button",
                "button.msg-form__send-btn",
                "button[aria-label*='보내기']",
                "button:has-text('보내기')",
                "button:has-text('Send')",
            ]:
                btn = self.page.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    send_btn = btn
                    break

            if not send_btn:
                print("  [!] 메시지 전송 버튼을 찾을 수 없습니다.")
                return False

            await send_btn.click()
            await self.page.wait_for_timeout(2000)

            print(f"  [+] 다이렉트 메시지 전송 완료")
            return True

        except Exception as e:
            print(f"  [!] 다이렉트 메시지 실패: {e}")
            return False

    # ── 검색 / 프로필 스크래핑 ───────────────────────────

    async def search_people(self, query: str, page: int = 1):
        """LinkedIn People 검색 페이지로 이동한다."""
        # 열린 메시지 다이얼로그 닫기
        try:
            close_btn = self.page.locator("button[data-control-name='overlay.close_conversation_window'], header.msg-overlay-bubble-header button.msg-overlay-bubble-header__control--new-convo-btn, button.msg-overlay-conversation-bubble__close-btn").first
            if await close_btn.count() and await close_btn.is_visible():
                await close_btn.click()
                await self.page.wait_for_timeout(500)
        except Exception:
            pass
        # msg-overlay 전체 닫기 시도
        try:
            for close_sel in [
                "button.msg-overlay-bubble-header__control[aria-label*='닫']",
                "button.msg-overlay-bubble-header__control[aria-label*='Close']",
                "aside.msg-overlay-container button[data-control-name='overlay.minimize_connection_list_bar']",
            ]:
                btn = self.page.locator(close_sel).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    await self.page.wait_for_timeout(300)
        except Exception:
            pass

        encoded = quote(query)
        url = f"https://www.linkedin.com/search/results/people/?keywords={encoded}&page={page}"
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(3000)

        # 페이지 로드 후 스크롤하여 lazy-load 트리거
        await self.page.evaluate("window.scrollBy(0, 300)")
        await self.page.wait_for_timeout(1000)

    async def parse_search_results(self) -> list[dict]:
        """현재 검색 결과 페이지에서 프로필 정보를 추출한다."""
        results = []

        # 여러 셀렉터 시도 (LinkedIn이 클래스명을 자주 변경함)
        ITEM_SELECTORS = [
            "div[data-view-name='people-search-result']",
            "li.reusable-search__result-container",
            "div.entity-result",
            "li div.entity-result",
            "ul.reusable-search__entity-result-list > li",
            "div.search-results-container ul > li",
        ]

        items = None
        count = 0
        used_selector = ""
        for sel in ITEM_SELECTORS:
            candidate = self.page.locator(sel)
            c = await candidate.count()
            if c > 0:
                items = candidate
                count = c
                used_selector = sel
                break

        if count == 0:
            debug_path = BROWSER_STATE_DIR / "debug_search.png"
            await self.page.screenshot(path=str(debug_path))
            # DOM 구조 일부를 덤프하여 디버깅 지원
            try:
                snippet = await self.page.evaluate("""
                    () => {
                        const main = document.querySelector('main') || document.querySelector('.search-results-container') || document.body;
                        return main.innerHTML.substring(0, 3000);
                    }
                """)
                debug_html = BROWSER_STATE_DIR / "debug_search.html"
                debug_html.write_text(snippet, encoding="utf-8")
                print(f"  [DEBUG] 검색 결과 0건 — 스크린샷: {debug_path}")
                print(f"  [DEBUG] HTML 덤프: {debug_html}")
            except Exception:
                print(f"  [DEBUG] 검색 결과 0건 — 스크린샷: {debug_path}")
            return results

        print(f"  [DEBUG] 셀렉터 '{used_selector}' → {count}건 매칭")

        # 이름+URL 추출용 셀렉터 후보
        NAME_LINK_SELECTORS = [
            "a[data-view-name='search-result-lockup-title']",
            "span.entity-result__title-text a",
            "span[dir='ltr'] a",
            "a.app-aware-link[href*='/in/']",
            "a[href*='/in/']",
        ]
        # 직함 셀렉터 후보
        HEADLINE_SELECTORS = [
            "div.entity-result__primary-subtitle",
            "div[data-view-name='people-search-result'] .t-14.t-black.t-normal",
            "div[data-view-name='people-search-result'] [dir='ltr']",
            ".t-14.t-black.t-normal",
            "div.linked-area div.t-14.t-normal",
        ]
        # 위치 셀렉터 후보
        LOCATION_SELECTORS = [
            "div.entity-result__secondary-subtitle",
            "div[data-view-name='people-search-result'] .t-12.t-black--light.t-normal",
            ".t-12.t-black--light.t-normal",
            "div.linked-area div.t-14.t-normal.t-black--light",
        ]

        for i in range(count):
            try:
                item = items.nth(i)

                # 이름 + URL 추출
                name = ""
                profile_url = ""
                for sel in NAME_LINK_SELECTORS:
                    link = item.locator(sel).first
                    if await link.count():
                        raw_name = (await link.text_content() or "").strip()
                        # 숨겨진 텍스트 제거 (예: "View [Name]'s profile")
                        raw_name = raw_name.split("\n")[0].strip()
                        href = await link.get_attribute("href") or ""
                        if raw_name and "/in/" in href:
                            name = raw_name
                            profile_url = href.split("?")[0]
                            break
                
                # 대체 수단: item 자체가 a 태그이거나 내부에 /in/ 링크가 있는 경우
                if not profile_url:
                    link = item.locator("a[href*='/in/']").first
                    if await link.count():
                        profile_url = (await link.get_attribute("href") or "").split("?")[0]
                        name = (await link.text_content() or "").strip().split("\n")[0]

                if not profile_url:
                    continue

                # "LinkedIn Member" 필터링
                if any(x in name for x in ["LinkedIn Member", "LinkedIn 멤버", "LinkedIn 회원"]):
                    continue

                # 직함+회사
                headline = ""
                for sel in HEADLINE_SELECTORS:
                    el = item.locator(sel).first
                    if await el.count():
                        headline = (await el.text_content() or "").strip()
                        if headline: break

                # 위치
                location = ""
                for sel in LOCATION_SELECTORS:
                    el = item.locator(sel).first
                    if await el.count():
                        loc = (await el.text_content() or "").strip()
                        if loc and loc != headline:
                            location = loc
                            break

                title, company = self._parse_headline(headline)

                results.append({
                    "name": name,
                    "title": title,
                    "company": company,
                    "headline": headline,
                    "location": location,
                    "url": profile_url,
                })
                print(f"    [+] 수집 성공: {name} ({profile_url})")
            except Exception as e:
                print(f"  [!] 검색 결과 파싱 오류 (#{i}): {e}")
                continue

        return results

    async def get_profile_about(self, profile_url: str) -> str:
        """프로필의 '소개(About)' 섹션 텍스트를 추출한다."""
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(2000)
        
        # 페이지 상단에서 헤드라인 정보는 미리 가져올 수 있음
        await self.page.evaluate("window.scrollBy(0, 500)")
        await self.page.wait_for_timeout(1000)

        about_text = ""
        for selector in ["section#about", "section:has(h2:text('소개'))", "section:has(h2:text('About'))"]:
            section = self.page.locator(selector).first
            if await section.count():
                # "더 보기" 버튼 클릭 시도
                see_more = section.locator("button:has-text('더 보기'), button:has-text('see more'), button:has-text('See more')").first
                if await see_more.count() and await see_more.is_visible():
                    try:
                        await see_more.click()
                        await self.page.wait_for_timeout(500)
                    except Exception:
                        pass
                about_text = (await section.text_content()).strip()
                # 줄바꿈 및 다중 공백 정리
                about_text = re.sub(r"\s+", " ", about_text)
                break

        return about_text[:300] if about_text else ""

    async def get_profile_headline(self) -> str:
        """프로필 상단의 헤드라인(직함 정보)을 추출한다."""
        selectors = [
            "div.text-body-medium.break-words",
            "div[data-generated-headline-anchor]",
            "h2.text-body-medium",
            ".pv-text-details__left-panel div"
        ]
        for sel in selectors:
            el = self.page.locator(sel).first
            if await el.count():
                text = (await el.text_content() or "").strip()
                if text:
                    return re.sub(r"\s+", " ", text)
        return ""

    async def get_current_experience(self) -> tuple[str, str]:
        """
        현재 열려있는 프로필 페이지에서 최신 경력(직함, 회사)을 추출한다.
        """
        try:
            # Experience 섹션이 보일 때까지 점진적으로 스크롤
            for _ in range(3):
                exp_section = self.page.locator("section#experience, section[data-member-id*='experience'], section:has(h2:text('Experience')), section:has(h2:text('경력'))").first
                if await exp_section.count() and await exp_section.is_visible():
                    break
                await self.page.evaluate("window.scrollBy(0, 1000)")
                await self.page.wait_for_timeout(1000)

            exp_section = self.page.locator("section#experience, section[data-member-id*='experience'], section:has(h2:text('Experience')), section:has(h2:text('경력'))").first
            if not await exp_section.count():
                return "", ""

            # 첫 번째 경력 항목(li) 찾기
            first_item = exp_section.locator("li.pvs-list__item, li").first
            if not await first_item.count():
                return "", ""

            # 직함 추출
            title = ""
            title_selectors = [
                "div.display-flex.align-items-center.mr1.t-bold span[aria-hidden='true']",
                "div.display-flex.align-items-center.mr1.t-bold",
                ".t-bold span[aria-hidden='true']",
                ".t-bold",
                "span[data-view-name='experience-item-title']"
            ]
            for sel in title_selectors:
                el = first_item.locator(sel).first
                if await el.count():
                    title = (await el.text_content() or "").strip()
                    if title: break
            
            title = re.sub(r"\s+", " ", title)

            # 회사명 추출
            company = ""
            company_selectors = [
                "span.t-14.t-normal span[aria-hidden='true']",
                "span.t-14.t-normal",
                ".t-14.t-normal span[aria-hidden='true']",
                "span[data-view-name='experience-item-subtitle']",
            ]
            for sel in company_selectors:
                el = first_item.locator(sel).first
                if await el.count():
                    c_text = (await el.text_content() or "").strip()
                    if c_text:
                        # 회사명만 분리 (중점 기호 등 제거)
                        company = c_text.split("·")[0].split("•")[0].strip()
                        if company: break
            
            company = re.sub(r"\s+", " ", company)

            return title, company
        except Exception as e:
            print(f"  [!] 경력 추출 중 오류: {e}")
            return "", ""

    async def get_latest_post(self, profile_url: str) -> str:
        """프로필의 최근 포스트 텍스트를 추출한다."""
        url = self._normalize_url(profile_url).rstrip("/")
        activity_url = f"{url}/recent-activity/all/"
        await self.page.goto(activity_url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(3000)

        post = self.page.locator("div.feed-shared-update-v2").first
        if await post.count():
            text = (await post.text_content()).strip()
            text = re.sub(r"\s+", " ", text)
            return text[:200] if text else ""
        return ""

    @staticmethod
    def _parse_headline(headline: str) -> tuple[str, str]:
        """직함+회사 문자열을 (title, company)로 분리한다."""
        if not headline:
            return ("", "")
        for sep in [" at ", " @ ", " | ", " - "]:
            if sep in headline:
                parts = headline.split(sep, 1)
                return (parts[0].strip(), parts[1].strip())
        return (headline.strip(), "")

    async def paste_text(self, element, text: str):
        """클립보드에 텍스트를 넣고 붙여넣기한다."""
        await element.click()
        await self.page.evaluate("text => navigator.clipboard.writeText(text)", text)
        await self.page.keyboard.press("Control+V")
        await self.page.wait_for_timeout(500)

    async def random_delay(self):
        """메시지 간 랜덤 딜레이."""
        min_d = getattr(self.config, "MIN_DELAY", 10)
        max_d = getattr(self.config, "MAX_DELAY", 20)
        delay = random.uniform(min_d, max_d)
        print(f"  [*] {delay:.0f}초 대기 중...")
        await asyncio.sleep(delay)

    def _normalize_url(self, url: str) -> str:
        """LinkedIn URL을 정규화한다."""
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        return url
