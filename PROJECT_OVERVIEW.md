# LinkedIn Outreach Automation — 프로젝트 전체 개요

싱가포르 F&B 시장에 한국 건빵(Korean Hardtack Biscuit)을 유통하기 위해 LinkedIn에서 잠재 바이어를 검색하고, 개인화된 메시지를 생성/발송하고, 아웃리치 현황을 추적하는 자동화 시스템.

**기술 스택**: Python 3.12+, Playwright (async), Gemini CLI (LLM), CSV 기반 데이터 관리

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
│   ├── config.example.py         # 설정 템플릿
│   ├── config.py                 # 실제 설정 (.gitignore 대상)
│   ├── linkedin_bot.py           # 핵심 Playwright 자동화 클래스
│   ├── generator.py              # Gemini CLI 기반 메시지 자동 생성기
│   ├── send.py                   # 메시지 발송 CLI (자동 생성 및 후속 포함)
│   └── search.py                 # 바이어 검색 CLI
│
└── browser_state/                # Chromium 세션 저장 (.gitignore 대상)
    └── profile/                  # persistent context user_data_dir
```

---

## 핵심 기능

### 1. 정교한 바이어 수집 및 분석 (search.py & linkedin_bot.py)
- **Boolean 검색 활용**: `("Category Manager" OR "Procurement") AND ("Snacks" OR "Biscuits" OR "F&B")` 등 고도화된 쿼리 사용.
- **2단계 추출 및 분석**: Phase 1(목록) → Phase 2(프로필 상세, 최근 게시물, 소개글 요약) 분석을 통해 개인화 데이터 확보.
- **활동성 분석**: 바이어의 최근 포스트를 스크래핑하여 관심사(ESG, 트렌드 등)를 메시지에 반영.

### 2. 메시지 자동 생성 (generator.py)
- **멀티 LLM CLI 통합**: Gemini, Claude, Codex CLI 폴백 메커니즘 적용.
- **전략적 프롬프트**: 바이어의 최근 활동, 회사 보완점, 싱가포르 전문 용어를 결합한 초개인화 메시지 생성.

### 3. 지능형 아웃리치 및 워밍업 (send.py)
- **7일 주기 규칙**: 마지막 발송일로부터 7일 경과된 계정에 후속 메시지 자동 발송.

---

## 실행 프로세스

1. **바이어 검색**: `python automation/search.py --limit 1000`
2. **자동 생성 및 발송**: `python automation/send.py`
   - 내부적으로 `generator.py`를 실행하여 누락된 메시지 파일 자동 생성.
   - 생성된 메시지를 확인 후 일괄 발송.
