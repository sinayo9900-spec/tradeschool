# LinkedIn Outreach Automation

이 프로젝트는 Claude CLI가 직접 파일을 읽고, 메시지를 생성하고, 데이터를 관리하는 LinkedIn 아웃리치 자동화 시스템이다.

## 프로젝트 구조

```
data/product.md       — 제품 설명 (사용자가 작성)
data/buyers.csv       — 바이어 목록 (이름, 직함, 회사, 산업, LinkedIn URL, 메모)
data/outreach.csv     — 아웃리치 현황 (이름, 회사, 상태, 첫발송일, 후속발송일, 메모)
templates/            — 메시지 생성 가이드 (first_contact.md, follow_up.md, reply_guide.md)
output/messages/      — 생성된 메시지 저장소
```

## 워크플로우

사용자가 자연어로 요청하면 아래 패턴에 따라 처리한다.

### 1. 바이어 목록 관리
- **"바이어 목록 보여줘"** → `data/buyers.csv`를 읽어서 표 형태로 표시
- **"바이어 추가: [정보]"** → `data/buyers.csv`에 새 행 추가 + `data/outreach.csv`에도 대기 상태로 추가
- **"[이름] 정보 보여줘"** → buyers.csv에서 해당 바이어 정보 표시

### 2. 메시지 생성
- **"[이름]에게 첫 메시지 만들어줘"** →
  1. `data/product.md` 읽기
  2. `data/buyers.csv`에서 해당 바이어 정보 찾기
  3. `templates/first_contact.md` 가이드 참조
  4. 개인화된 메시지 생성
  5. `output/messages/[이름]_first.md`에 저장
  6. 메시지 내용을 사용자에게 표시

- **"[이름]에게 후속 메시지 만들어줘"** →
  1. `data/product.md` + 바이어 정보 읽기
  2. `data/outreach.csv`에서 이전 발송 이력 확인
  3. `templates/follow_up.md` 가이드 참조
  4. 이전 메시지가 있으면 `output/messages/`에서 읽기
  5. 후속 메시지 생성 및 저장

### 3. 아웃리치 현황 관리
- **"아웃리치 현황 보여줘"** → `data/outreach.csv` 읽어서 통계와 함께 표시
  - 전체/대기/발송/응답/미팅/거절 건수
  - 각 바이어별 상태

- **"[이름] 상태를 [상태]로 변경"** → `data/outreach.csv`에서 해당 행의 상태 컬럼 수정
  - 유효 상태: 대기, 발송, 응답, 미팅, 거절, 미응답종료, 완료

- **"후속 메시지 보낼 사람 알려줘"** → outreach.csv에서 상태가 "발송"이고 첫발송일로부터 5일 이상 경과한 바이어 필터링

### 4. 답변 대응
- **"[이름]이 이렇게 답변했어: [내용]"** →
  1. `templates/reply_guide.md` 참조
  2. 답변 유형 분류 (긍정/질문/거절 등)
  3. 대응 메시지 생성
  4. `output/messages/[이름]_reply_[번호].md`에 저장
  5. `data/outreach.csv` 상태 업데이트 제안

## 메시지 생성 규칙

- **언어**: 바이어 프로필에 따라 한국어 또는 영어
- **톤**: 전문적이지만 친근한 대화체
- **길이**: 첫 메시지 150-300자, 후속 100-200자
- **금지 사항**:
  - "귀사", "폐사" 등 과도한 격식체
  - "혁신적인", "게임체인저" 등 과장 표현
  - 첫 메시지에서 즉시 미팅/데모 요청
  - 동일한 템플릿 반복 사용

## 파일 수정 시 주의사항

- CSV 파일 수정 시 기존 데이터 보존. 해당 행/셀만 정확히 수정
- 메시지 파일 생성 시 상단에 메타데이터 포함:
  ```
  ---
  바이어: [이름]
  회사: [회사]
  유형: 첫 연락 / 후속 1차 / 후속 2차 / 답변 대응
  생성일: [날짜]
  ---
  ```
- outreach.csv 수정 시 변경 내용을 사용자에게 명확히 보고

## 브라우저 자동화 (Playwright)

### 구조

```
automation/
├── requirements.txt        # playwright 의존성
├── config.example.py       # 설정 템플릿
├── config.py               # 실제 설정 (.gitignore 대상)
├── linkedin_bot.py         # 핵심 자동화 클래스
├── send.py                 # 메시지 발송 CLI
└── search.py               # 바이어 검색 CLI
browser_state/              # 로그인 세션 저장 (자동 생성, .gitignore 대상)
```

### send.py — 메시지 자동 발송

outreach.csv에서 "대기" 상태인 바이어를 찾아 output/messages/의 메시지 파일을 LinkedIn으로 발송한다.

- **"로그인 세팅해줘"** → `python automation/send.py --login` 실행 안내
  - 브라우저가 열리면 사용자가 직접 LinkedIn 로그인
  - 세션이 `browser_state/`에 저장됨

- **"메시지 발송해줘"** → `python automation/send.py` 실행 안내
  - outreach.csv에서 "대기" 상태 바이어를 자동 필터링
  - output/messages/에서 메시지 파일을 읽어 발송
  - 연결 상태에 따라 커넥션 요청(노트 포함) 또는 다이렉트 메시지 전송
  - 발송 후 outreach.csv 상태를 "발송"으로 자동 업데이트

- **CLI 옵션**:
  - `--login`: LinkedIn 로그인 (첫 실행 시)
  - `--name "이름"`: 특정 바이어만 발송
  - `--dry-run`: 미리보기 모드 (실제 발송 안 함)
  - `--limit N`: 일일 발송 한도 변경 (기본 20)

### search.py — 바이어 검색 자동화

LinkedIn People 검색으로 잠재 바이어를 자동 수집하여 buyers.csv와 outreach.csv에 추가한다.

- **"바이어 검색해줘"** → `python automation/search.py` 실행 안내

- **실행 플로우** (3단계):
  1. **검색 수집**: 검색어별 페이지 순회 → 이름/직함/회사/URL 추출 → 기존 URL 중복 체크
  2. **프로필 상세**: 각 프로필 방문하여 소개(About) 텍스트 + 최근 포스트 수집
  3. **결과 저장**: buyers.csv에 append + outreach.csv에 "대기" 상태로 append

- **CLI 옵션**:
  - `--login`: LinkedIn 로그인 (첫 실행 시)
  - `--query "검색어"`: 특정 검색어 사용 (없으면 기본 검색어 4개 순회)
  - `--limit N`: 최대 수집 인원 (기본 20)
  - `--dry-run`: 미리보기 모드 (CSV 저장 안 함)
  - `--skip-profiles`: 검색 결과만 수집 (프로필 방문 생략, 빠름)

- **기본 검색어**: Singapore F&B procurement manager, Singapore snack biscuit distribution, Singapore food import buyer, Singapore FMCG procurement

- **중복 방지**: LinkedIn URL 기준 정규화 비교 (lowercase, 쿼리파라미터 제거, https 통일)

### 설정 방법
1. `pip install -r automation/requirements.txt && playwright install chromium`
2. `copy automation\config.example.py automation\config.py` 후 정보 입력
3. `python automation/send.py --login` 으로 로그인
4. `python automation/send.py --dry-run` 으로 발송 미리보기 확인
5. `python automation/search.py --dry-run --limit 5` 로 검색 미리보기 확인
