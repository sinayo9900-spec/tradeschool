import asyncio
import random
import os
from pathlib import Path
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
                await self.human_type(textarea, truncated_note)
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
            await self.human_type(msg_box, message)
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

    async def human_type(self, element, text: str):
        """사람처럼 한 글자씩 타이핑한다."""
        min_delay = getattr(self.config, "MIN_TYPE_DELAY", 50)
        max_delay = getattr(self.config, "MAX_TYPE_DELAY", 150)

        for char in text:
            await element.press_sequentially(char, delay=0)
            delay_ms = random.randint(min_delay, max_delay)
            await self.page.wait_for_timeout(delay_ms)

    async def random_delay(self):
        """메시지 간 랜덤 딜레이."""
        min_d = getattr(self.config, "MIN_DELAY", 60)
        max_d = getattr(self.config, "MAX_DELAY", 120)
        delay = random.uniform(min_d, max_d)
        print(f"  [*] {delay:.0f}초 대기 중...")
        await asyncio.sleep(delay)

    def _normalize_url(self, url: str) -> str:
        """LinkedIn URL을 정규화한다."""
        url = url.strip()
        if not url.startswith("http"):
            url = "https://" + url
        return url
