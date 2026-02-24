# LinkedIn Outreach Automation — 프로젝트 전체 개요

싱가포르 F&B 시장에 한국 건빵(Korean Hardtack Biscuit)을 유통하기 위해 LinkedIn에서 잠재 바이어를 검색하고, 개인화된 메시지를 생성/발송하고, 아웃리치 현황을 추적하는 자동화 시스템.

**기술 스택**: Python 3.12+, Playwright (async), CSV 기반 데이터 관리

---

## 디렉토리 구조

```
D:\Project\LinkedIn\
├── CLAUDE.md                     # Claude CLI용 프로젝트 지시서
├── .gitignore
│
├── data/
│   ├── product.md                # 제품 설명 (한국 건빵)
│   ├── buyers.csv                # 바이어 DB (이름,직함,회사,산업,LinkedIn URL,메모)
│   └── outreach.csv              # 아웃리치 추적 (이름,회사,상태,첫발송일,후속발송일,메모)
│
├── templates/
│   ├── first_contact.md          # 첫 메시지 생성 가이드
│   ├── follow_up.md              # 후속 메시지 생성 가이드
│   └── reply_guide.md            # 답변 유형별 대응 가이드
│
├── output/
│   └── messages/                 # 생성된 메시지 저장소
│       ├── {이름}_first.md       # 첫 연락 메시지
│       ├── {이름}_followup_N.md  # 후속 N차 메시지
│       └── {이름}_reply_N.md     # 답변 대응 메시지
│
├── automation/
│   ├── requirements.txt          # playwright, python-dotenv
│   ├── config.example.py         # 설정 템플릿 (.env에서 딜레이/한도 로드)
│   ├── config.py                 # 실제 설정 (.gitignore 대상)
│   ├── linkedin_bot.py           # 핵심 Playwright 자동화 클래스
│   ├── send.py                   # 메시지 발송 CLI
│   └── search.py                 # 바이어 검색 CLI
│
└── browser_state/                # Chromium 세션 저장 (.gitignore 대상)
    └── profile/                  # persistent context user_data_dir
```

---

## 데이터 파일

### data/buyers.csv
```csv
이름,직함,회사,산업,LinkedIn URL,메모
Jiwoo Shin,Procurement Manager,[Company],F&B Distribution,www.linkedin.com/in/jiwooshinsjw,"싱가포르 수입식품 유통. 한국 식품 라인 보유"
Sooji Lee,Procurement Manager,[Company],F&B Distribution,https://www.linkedin.com/in/sooji-lee-4975483b0/,"싱가포르 수입식품 유통. 한국 식품 라인 보유"
```

### data/outreach.csv
```csv
이름,회사,상태,첫발송일,후속발송일,메모
Jiwoo Shin,[Company],대기,,,
Sooji Lee,[Company],발송,2026-02-24,,
```
- 유효 상태값: 대기, 발송, 응답, 미팅, 거절, 미응답종료, 완료

### data/product.md
한국 건빵 제품 설명서. 핵심: 싱가포르 바/카페/호텔 F&B 채널 대상, K-푸드 트렌드 + 가성비 + 칵테일/커피 페어링 포지셔닝.

---

## 핵심 코드: automation/linkedin_bot.py

`LinkedInBot` 클래스 — Playwright persistent context 기반 LinkedIn 자동화.

### 브라우저 관리
```python
class LinkedInBot:
    def __init__(self, config)        # config 모듈 주입
    async def start(headless=False)   # chromium persistent context 시작
    async def close()                 # 브라우저 종료 (세션 자동 저장)
    async def login()                 # 수동 로그인 → 세션 저장
    async def check_session() -> bool # /feed 이동하여 세션 유효성 확인
```

- `launch_persistent_context(user_data_dir=browser_state/profile)` 사용
- viewport: 1280x800, locale: en-US

### 메시지 발송 (send.py에서 사용)
```python
async def is_connected(profile_url) -> str
    # "connected" / "not_connected" / "pending" / "unknown"
    # section[data-member-id] 내 span.dist-value ("1촌"/"1st" 등) 판별

async def send_connection_request(profile_url, note) -> bool
    # 미연결 바이어에게 커넥션 요청 + 300자 노트
    # Connect 버튼 → Add a note → textarea 붙여넣기 → Send

async def send_direct_message(profile_url, message) -> bool
    # 1촌 바이어에게 DM
    # Message 버튼 → contenteditable div 붙여넣기 → Send
```

### 검색/스크래핑 (search.py에서 사용)
```python
async def search_people(query, page=1)
    # URL: /search/results/people/?keywords={query}&page={page}
    # 검색 전 메시지 다이얼로그 닫기 시도
    # 페이지 로드 후 300px 스크롤 (lazy-load 트리거)

async def parse_search_results() -> list[dict]
    # 검색 결과 페이지에서 이름/URL/직함/회사/위치 추출
    # 복수 셀렉터 시도 (LinkedIn이 클래스명 자주 변경):
    #   - 아이템: "li.reusable-search__result-container", "div.entity-result" 등 5개
    #   - 이름링크: "span.entity-result__title-text a", "a.app-aware-link[href*='/in/']" 등 3개
    #   - 직함: "div.entity-result__primary-subtitle" 등 3개
    #   - 위치: "div.entity-result__secondary-subtitle" 등 2개
    # "LinkedIn Member" / "LinkedIn 회원" 필터링
    # 0건이면 debug_search.png + debug_search.html 저장

async def get_profile_about(profile_url) -> str
    # 프로필 About 섹션 텍스트 추출 (300자 제한)
    # section#about 또는 section:has(h2:text('소개')) 또는 :has(h2:text('About'))
    # "더 보기" 버튼 클릭 후 재추출

async def get_latest_post(profile_url) -> str
    # {profile_url}/recent-activity/all/ 에서 첫 포스트 텍스트 (200자 제한)
    # div.feed-shared-update-v2

@staticmethod
def _parse_headline(headline) -> (title, company)
    # " at ", " @ ", " | ", " - " 구분자로 분리
```

### 유틸리티
```python
async def paste_text(element, text)    # 클립보드 → Ctrl+V 붙여넣기
async def random_delay()               # config.MIN_DELAY~MAX_DELAY초 대기
def _normalize_url(url) -> str         # http 접두사 보정
```

---

## CLI: automation/send.py

**기능**: outreach.csv에서 "대기" 상태 바이어 필터링 → 메시지 파일 읽기 → LinkedIn 발송

### 사용법
```bash
python automation/send.py --login              # 첫 로그인
python automation/send.py --dry-run            # 미리보기
python automation/send.py                      # 전체 발송
python automation/send.py --name "이름"        # 특정 바이어만
python automation/send.py --limit 5            # 발송 한도
```

### 핵심 함수
```python
def read_buyers() -> list[dict]           # buyers.csv 로드
def read_outreach() -> list[dict]         # outreach.csv 로드
def write_outreach(rows)                  # outreach.csv 덮어쓰기
def find_message_file(name) -> str|None   # output/messages/{name}_first.md 등 찾기
def extract_message_body(content) -> str  # YAML frontmatter 제거

def get_send_targets(buyers, outreach, name_filter) -> list[dict]
    # 조건: outreach 상태 "대기" + 메시지 파일 존재 + URL 존재

def update_outreach_status(name, outreach) -> list[dict]
    # 상태 → "발송", 첫발송일 → 오늘 날짜

async def run_send(args)
    # 1. 대상 목록 구성 → 표시
    # 2. dry-run이면 종료
    # 3. 사용자 확인 (y/n)
    # 4. 브라우저 시작 → 세션 확인
    # 5. 각 바이어: is_connected → send_connection_request 또는 send_direct_message
    # 6. 성공 시 outreach.csv 즉시 업데이트
    # 7. 바이어 간 random_delay()
    # 8. 완료 리포트 출력
```

---

## CLI: automation/search.py

**기능**: LinkedIn People 검색으로 잠재 바이어 수집 → buyers.csv / outreach.csv 추가

### 사용법
```bash
python automation/search.py --login                           # 로그인
python automation/search.py --dry-run --limit 5               # 미리보기
python automation/search.py --skip-profiles --limit 10        # 검색만 (프로필 방문 생략)
python automation/search.py --query "Singapore food import"   # 특정 검색어
python automation/search.py                                   # 기본 검색어 4개 순회, 20명
```

### 기본 검색어
```python
DEFAULT_QUERIES = [
    "Singapore F&B procurement manager",
    "Singapore snack biscuit distribution",
    "Singapore food import buyer",
    "Singapore FMCG procurement",
]
```

### 핵심 함수
```python
def normalize_url(url) -> str              # lowercase + 쿼리파라미터 제거 + https 통일
def load_existing_urls() -> set[str]       # buyers.csv URL 로드 (중복 체크용)
def append_to_buyers(prospects)            # buyers.csv에 append ("a" 모드)
def append_to_outreach(prospects)          # outreach.csv에 append ("a" 모드, 상태="대기")

async def run_search(args)
    # Phase 1 — 검색 수집:
    #   각 검색어 × 페이지 1~10 순회
    #   parse_search_results() → URL 중복 체크 → limit까지 수집
    #   페이지 간 random_delay()
    #
    # Phase 2 — 프로필 상세 (--skip-profiles 시 생략):
    #   각 프로필 방문 → get_profile_about() + get_latest_post()
    #   메모 구성: "[소개] ... | [최근포스트] ... | [위치] ..."
    #   실패해도 건너뛰고 계속 진행
    #   프로필 간 random_delay()
    #
    # Phase 3 — 결과 표시 + 저장:
    #   테이블 출력
    #   --dry-run 아니면 CSV append
```

---

## config (automation/config.example.py)

```python
# .env에서 로드
DAILY_LIMIT = 20       # 일일 발송 한도
MIN_DELAY = 60         # 액션 간 최소 딜레이 (초)
MAX_DELAY = 120        # 액션 간 최대 딜레이 (초)
MIN_TYPE_DELAY = 50    # (미사용) 타이핑 딜레이
MAX_TYPE_DELAY = 150   # (미사용) 타이핑 딜레이
```

---

## 메시지 파일 형식

```markdown
---
바이어: Sooji Lee
회사: [Company]
유형: 첫 연락
생성일: 2026-02-24
---

Hi Sooji, I noticed you're working in F&B distribution here in Singapore...
```

---

## 현재 이슈

### search.py — 검색 결과 파싱 실패 (0건)
- **증상**: `parse_search_results()`가 검색 결과 0건 반환
- **원인**: LinkedIn이 HTML 클래스명을 변경하여 기존 셀렉터가 매칭 안 됨
- **디버그 파일**: `browser_state/debug_search.png` (스크린샷), `browser_state/debug_search.html` (DOM 덤프)
- **스크린샷 상태**: 검색 결과는 페이지에 정상 표시됨 (LinkedIn 회원, R. M., Melisa Lee 등). 메시지 다이얼로그 오버레이가 열려 있었음.
- **시도한 수정**:
  - 복수 아이템 셀렉터 5개 시도 (reusable-search__result-container, entity-result 등)
  - 복수 이름/직함/위치 셀렉터 각 2~3개
  - 메시지 다이얼로그 자동 닫기
  - 페이지 스크롤 300px (lazy-load 트리거)
  - 0건 시 HTML 덤프 저장 추가
- **필요한 작업**: `debug_search.html` 분석 → 실제 DOM 구조에 맞는 정확한 셀렉터 확인

---

## 워크플로우 전체 흐름

```
1. 로그인:     python automation/send.py --login
2. 바이어 검색: python automation/search.py --limit 20
                → buyers.csv + outreach.csv에 추가 (상태: 대기)
3. 메시지 생성: Claude CLI에 "OOO에게 첫 메시지 만들어줘" 요청
                → product.md + buyers.csv + templates/first_contact.md 참조
                → output/messages/{이름}_first.md 저장
4. 메시지 발송: python automation/send.py
                → 대기 상태 바이어에게 자동 발송
                → outreach.csv 상태 → "발송"
5. 후속 관리:   Claude CLI로 현황 확인, 후속 메시지 생성, 답변 대응
```
