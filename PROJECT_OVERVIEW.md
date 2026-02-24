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
│   ├── config.example.py         # 설정 템플릿
│   ├── config.py                 # 실제 설정 (.gitignore 대상)
│   ├── linkedin_bot.py           # 핵심 Playwright 자동화 클래스
│   ├── send.py                   # 메시지 발송 CLI (자동 후속 발송 포함)
│   └── search.py                 # 바이어 검색 CLI
│
└── browser_state/                # Chromium 세션 저장 (.gitignore 대상)
    └── profile/                  # persistent context user_data_dir
```

---

## 핵심 기능

### 1. 정교한 바이어 수집 (search.py & linkedin_bot.py)
- **2단계 추출 전략**: 
  - **Phase 1**: 검색 결과 목록에서 이름/URL/헤드라인 추출.
  - **Phase 2**: 프로필 상세 방문. `Experience` 섹션을 정밀 분석하여 정확한 **직함**과 **회사명**을 추출. 실패 시 상단 `Headline`에서 폴백 추출.
- **데이터 정제**: 추출된 텍스트에서 줄바꿈 및 다중 공백을 제거하여 CSV 파손 방지.
- **중복 방지**: LinkedIn URL 정규화 비교를 통해 이미 수집된 바이어 제외.

### 2. 자동화된 아웃리치 (send.py)
- **7일 주기 규칙**: 마지막 발송(첫 연락 또는 후속)으로부터 7일이 경과한 바이어를 자동으로 식별하여 후속 메시지 발송 대상으로 지정.
- **메시지 자동 선택**: 
  - 상태가 '대기'이면 `_first.md` 사용.
  - 상태가 '발송'이면 `_followup_N.md` 중 가장 높은 번호의 파일을 자동 탐색.
- **지능형 연결 상태 대응**: 1촌 여부에 따라 다이렉트 메시지 또는 커넥션 요청(노트 포함)으로 자동 전환.

---

## 데이터 관리 규칙

- **CSV 안정성**: 데이터 추가/수정 시 모든 필드에서 줄바꿈(`\n`)을 강제 제거하여 파일 구조 유지.
- **outreach.csv 상태**: `대기`, `발송`, `응답`, `미팅`, `거절`, `미응답종료`, `완료`.
- **날짜 형식**: `YYYY-MM-DD`.

---

## 실행 프로세스

1. **바이어 검색**: `python automation/search.py --limit 20`
2. **메시지 생성**: Claude CLI를 통해 개인화된 메시지 파일(`.md`) 생성
3. **자동 발송**: `python automation/send.py` (대기자 및 7일 경과자 자동 발송)
