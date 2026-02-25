# LinkedIn Outreach Automation (Claude Guide)

이 프로젝트는 Claude CLI가 직접 파일을 읽고, 메시지를 생성하고, 데이터를 관리하는 LinkedIn 아웃리치 자동화 시스템이다.

## 워크플로우

### 1. 바이어 검색 및 수집
- **"바이어 검색해줘"** 또는 **"Singapore F&B 바이어 찾아줘"** → `python automation/search.py --limit 20` 실행 안내.
- 시스템은 Phase 1(목록 수집)과 Phase 2(프로필 상세 분석)를 거쳐 `buyers.csv`에 정확한 직함/회사를 저장함.

### 2. 메시지 자동 생성 및 발송 (통합)
- **"메시지 발송해줘"** → `python automation/send.py` 실행 안내.
- **자동 생성 시스템**:
  - `send.py` 실행 시 내부적으로 `automation/generator.py`가 먼저 호출됨.
  - `generator.py`는 `outreach.csv`를 분석하여 메시지 파일이 없는 바이어를 위해 **LLM_CLI_TYPE** 환경변수에 설정된 CLI(gemini, claude, codex)를 호출하여 메시지를 자동 생성함.
  - 생성된 메시지는 `output/messages/{이름}_first.md` 또는 `_followup_{N}.md`에 저장됨.
- **발송 필터링**:
  1. 상태가 **"대기"**인 바이어.
  2. 상태가 **"발송"**이고, 마지막 발송으로부터 **7일이 경과**한 바이어 (다음 차수 후속 메시지 자동 생성).

### 3. 메시지 생성 규칙 (generator.py 용)
- **파일명 규칙**: `{이름}_first.md`, `{이름}_followup_{N}.md`.
- **내용**: `product.md` 가치 + 바이어 경력 정보 결합.
- **정제 로직**: CLI 응답에서 첫 번째 `---` 구분선부터 끝까지만 저장하여 설명글 제거.

### 4. 현황 관리 및 답변 대응
- **"아웃리치 현황 보여줘"** → `outreach.csv` 읽어서 통계 표시.
- **"OOO이 이렇게 답변했어"** → `templates/reply_guide.md` 참조하여 답변 메시지 생성 제안.

## 기술 지시서

- **검색 쿼리**: Boolean 검색 (`OR`, `AND`, `" "`)을 적극 활용하여 타겟 정밀화.
- **워밍업 제한**: 일일 커넥션 요청 20-25건, 메시지 100건 이내 유지 (알고리즘 보호).
- **프로필 분석**: `generator.py`는 바이어의 `[최근포스트]`와 `[소개]` 데이터를 활용하여 공감대를 형성하는 메시지를 생성해야 함.
- **CLI 호출**: `generator.py`는 `LLM_CLI_TYPE` 환경변수를 따르며, 실패 시 가용 CLI 리스트 내에서 자동 폴백함.

## 주요 명령어
- 로그인: `python automation/send.py --login`
- 바이어 검색: `python automation/search.py --query "검색어" --limit 10`
- 자동 생성 및 발송 (미리보기): `python automation/send.py --dry-run`
- 자동 생성 및 발송 (실제): `python automation/send.py`
