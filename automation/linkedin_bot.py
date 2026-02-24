import asyncio
import random
import os
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

BASE_DIR = Path(__file__).resolve().parent.parent
BROWSER_STATE_DIR = BASE_DIR / "browser_state"


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
        storage_path = BROWSER_STATE_DIR / "state.json"

        if storage_path.exists():
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_STATE_DIR / "profile"),
                headless=headless,
                storage_state=str(storage_path),
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            print("[*] 저장된 세션을 로드했습니다.")
        else:
            BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_STATE_DIR / "profile"),
                headless=headless,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def close(self):
        """브라우저를 종료하고 세션을 저장한다."""
        if self.context:
            storage_path = BROWSER_STATE_DIR / "state.json"
            BROWSER_STATE_DIR.mkdir(parents=True, exist_ok=True)
            await self.context.storage_state(path=str(storage_path))
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
        Returns: "connected", "not_connected", "pending", "unknown"
        """
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(2000)

        # Message 버튼이 보이면 이미 연결됨
        message_btn = self.page.locator("button:has-text('Message')").first
        if await message_btn.is_visible():
            return "connected"

        # Pending 상태 확인
        pending = self.page.locator("button:has-text('Pending')").first
        if await pending.is_visible():
            return "pending"

        # Connect 버튼 확인
        connect_btn = self.page.locator("button:has-text('Connect')").first
        if await connect_btn.is_visible():
            return "not_connected"

        # More 버튼 안에 Connect가 숨어있을 수 있음
        more_btn = self.page.locator("button:has-text('More')").first
        if await more_btn.is_visible():
            await more_btn.click()
            await self.page.wait_for_timeout(500)
            connect_in_menu = self.page.locator("span:has-text('Connect')").first
            if await connect_in_menu.is_visible():
                return "not_connected"

        return "unknown"

    async def send_connection_request(self, profile_url: str, note: str) -> bool:
        """커넥션 요청을 보낸다 (노트 포함)."""
        url = self._normalize_url(profile_url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=15000)
        await self.page.wait_for_timeout(2000)

        try:
            # Connect 버튼 클릭
            connect_btn = self.page.locator("button:has-text('Connect')").first
            if not await connect_btn.is_visible():
                # More 메뉴에서 찾기
                more_btn = self.page.locator("button:has-text('More')").first
                if await more_btn.is_visible():
                    await more_btn.click()
                    await self.page.wait_for_timeout(500)
                    connect_btn = self.page.locator("span:has-text('Connect')").first

            await connect_btn.click()
            await self.page.wait_for_timeout(1000)

            # "Add a note" 버튼 클릭
            add_note_btn = self.page.locator("button:has-text('Add a note')").first
            if await add_note_btn.is_visible():
                await add_note_btn.click()
                await self.page.wait_for_timeout(500)

                # 노트 입력 (300자 제한)
                truncated_note = note[:300]
                textarea = self.page.locator("textarea[name='message']").first
                if not await textarea.is_visible():
                    textarea = self.page.locator("textarea#custom-message").first
                if not await textarea.is_visible():
                    textarea = self.page.locator("textarea").first

                await self.human_type(textarea, truncated_note)
                await self.page.wait_for_timeout(500)

            # 전송 버튼 클릭
            send_btn = self.page.locator("button:has-text('Send')").first
            if not await send_btn.is_visible():
                send_btn = self.page.locator("button[aria-label='Send now']").first
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
            # Message 버튼 클릭
            message_btn = self.page.locator("button:has-text('Message')").first
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
            send_btn = self.page.locator("button.msg-form__send-button").first
            if not await send_btn.is_visible():
                send_btn = self.page.locator("button:has-text('Send')").last
            await send_btn.click()
            await self.page.wait_for_timeout(2000)

            # 메시지 창 닫기
            close_btn = self.page.locator("button[data-control-name='overlay.close_conversation_window']").first
            if await close_btn.is_visible():
                await close_btn.click()

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
