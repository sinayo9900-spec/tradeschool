# LinkedIn Outreach Automation (Claude Guide)

이 프로젝트는 Claude CLI가 직접 파일을 읽고, 메시지를 생성하고, 데이터를 관리하는 LinkedIn 아웃리치 자동화 시스템이다.

## 워크플로우

### 1. 바이어 검색 및 수집
- **"바이어 검색해줘"** 또는 **"Singapore F&B 바이어 찾아줘"** → `python automation/search.py --limit 20` 실행 안내.
- 시스템은 Phase 1(목록 수집)과 Phase 2(프로필 상세 분석)를 거쳐 `buyers.csv`에 정확한 직함/회사를 저장함.

### 2. 메시지 생성 규칙 (중요)
- **파일명 규칙**: 
  - 첫 연락: `output/messages/{이름}_first.md`
  - 후속 N차: `output/messages/{이름}_followup_{N}.md` (예: `Jiwoo Shin_followup_1.md`)
- **메타데이터**: 파일 상단에 YAML 형식을 반드시 포함할 것.
- **내용**: `product.md`의 제품 가치와 바이어 프로필의 경력 정보를 결합하여 개인화.

### 3. 자동 아웃리치 발송
- **"메시지 발송해줘"** → `python automation/send.py` 실행 안내.
- **자동 필터링 대상**:
  1. `outreach.csv` 상태가 **"대기"**인 바이어.
  2. 상태가 **"발송"**이고, `첫발송일` 또는 `후속발송일`로부터 **7일이 경과**한 바이어 (후속 메시지 파일이 있어야 함).

### 4. 현황 관리 및 답변 대응
- **"아웃리치 현황 보여줘"** → `outreach.csv` 읽어서 통계 표시.
- **"후속 보낼 사람 알려줘"** → `outreach.csv`에서 발송 후 7일이 지났으나 아직 후속 메시지 파일이 없는 바이어 리스트업.

## 기술 지시서

- **CSV 수정**: 데이터 작성 시 반드시 `replace('\n', ' ')`를 적용하여 줄바꿈을 제거할 것.
- **메시지 탐색**: `send.py`는 가장 높은 번호의 `_followup_{N}.md`을 자동으로 찾음. 따라서 새로운 후속 메시지 생성 시 번호를 순차적으로 부여할 것.
- **오류 대응**: `browser_state/debug_*.png` 파일이 생성되면 스크린샷 상황을 확인하여 셀렉터 수정 검토.

## 주요 명령어
- 로그인: `python automation/send.py --login`
- 바이어 검색: `python automation/search.py --query "검색어" --limit 10`
- 자동 발송 (미리보기): `python automation/send.py --dry-run`
- 자동 발송 (실제): `python automation/send.py`
