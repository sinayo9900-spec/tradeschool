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

### 1. 정교한 바이어 수집 (search.py & linkedin_bot.py)
- **2단계 추출 전략**: Phase 1(목록) → Phase 2(프로필 상세) 분석을 통해 정확한 직함/회사 수집.
- **데이터 안정성**: 모든 데이터에서 줄바꿈(`\n`)을 제거하여 CSV 파손 방지.

### 2. 메시지 자동 생성 (generator.py)
- **멀티 LLM CLI 통합**: `send.py` 실행 시 메시지 파일이 없는 대상(대기자/7일 경과자)을 위해 `LLM_CLI_TYPE` 환경변수값에 따라 Gemini, Claude, Codex CLI 중 하나를 호출하여 개인화된 메시지를 즉석 생성. (기본값: gemini)
- **지능형 프롬프트**: `product.md`, 바이어 프로필 정보, `templates`를 결합하여 최적화된 메시지 구성.
- **정제 로직**: LLM 응답에서 불필요한 설명글을 제거하고 YAML 메타데이터를 포함한 순수 본문만 추출 및 저장.

### 3. 지능형 아웃리치 (send.py)
- **7일 주기 규칙**: 마지막 발송일로부터 7일 경과 시 자동으로 다음 차수 후속 메시지 발송 대상으로 지정.
- **연결 상태 대응**: 1촌 여부에 따라 Direct Message 또는 Connection Request(노트 포함)로 자동 전환.

---

## 실행 프로세스

1. **바이어 검색**: `python automation/search.py --limit 1000`
2. **자동 생성 및 발송**: `python automation/send.py`
   - 내부적으로 `generator.py`를 실행하여 누락된 메시지 파일 자동 생성.
   - 생성된 메시지를 확인 후 일괄 발송.
