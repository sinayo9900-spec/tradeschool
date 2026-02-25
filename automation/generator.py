import csv
import subprocess
import sys
import os
import re
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / "automation" / ".env")

BUYERS_CSV = BASE_DIR / "data" / "buyers.csv"
OUTREACH_CSV = BASE_DIR / "data" / "outreach.csv"
PRODUCT_MD = BASE_DIR / "data" / "product.md"
MESSAGES_DIR = BASE_DIR / "output" / "messages"
TEMPLATES_DIR = BASE_DIR / "templates"

# LLM CLI 설정 및 상태 관리
AVAILABLE_LLMS = ["gemini", "claude", "codex"]
CURRENT_LLM_TYPE = os.getenv("LLM_CLI_TYPE", "gemini").lower()
if CURRENT_LLM_TYPE not in AVAILABLE_LLMS:
    CURRENT_LLM_TYPE = "gemini"

def read_csv(path):
    if not path.exists(): return []
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def get_generation_targets():
    buyers = read_csv(BUYERS_CSV)
    outreach = read_csv(OUTREACH_CSV)
    today = datetime.now()
    targets = []

    for row in outreach:
        name = row.get("이름", "").strip()
        status = row.get("상태", "").strip()
        if not name: continue

        buyer_info = next((b for b in buyers if b.get("이름", "").strip() == name), None)
        if not buyer_info: continue

        # 1. 첫 연락 대상 (대기 상태 + 파일 없음)
        if status == "대기":
            file_path = MESSAGES_DIR / f"{name}_first.md"
            if not file_path.exists():
                targets.append({"name": name, "info": buyer_info, "type": "first", "path": file_path})

        # 2. 후속 연락 대상 (발송 상태 + 7일 경과 + 다음 번호 파일 없음)
        elif status == "발송":
            last_date_str = row.get("후속발송일") or row.get("첫발송일")
            if last_date_str:
                try:
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                    if (today - last_date).days >= 7:
                        # 현재 몇 차까지 있는지 확인
                        existing = list(MESSAGES_DIR.glob(f"{name}_followup_*.md"))
                        next_num = 1
                        if existing:
                            nums = [int(re.search(r"followup_(\d+)", f.name).group(1)) for f in existing if re.search(r"followup_(\d+)", f.name)]
                            next_num = max(nums) + 1 if nums else 1
                        
                        file_path = MESSAGES_DIR / f"{name}_followup_{next_num}.md"
                        if not file_path.exists():
                            targets.append({"name": name, "info": buyer_info, "type": f"followup_{next_num}", "path": file_path})
                except ValueError:
                    pass
    return targets

def call_llm_cli(prompt):
    """설정된 LLM CLI(gemini, claude, codex)를 호출하여 결과를 반환합니다. 
    호출 실패 시 다른 사용 가능한 CLI로 재시도합니다.
    """
    global CURRENT_LLM_TYPE
    
    # 현재 선호하는 CLI부터 시작하여 모든 가용 CLI를 시도
    # 예: [gemini, claude, codex] 순서에서 현재가 claude라면 [claude, codex, gemini] 순으로 시도
    start_idx = AVAILABLE_LLMS.index(CURRENT_LLM_TYPE)
    llms_to_try = AVAILABLE_LLMS[start_idx:] + AVAILABLE_LLMS[:start_idx]

    for llm_type in llms_to_try:
        # CLI 명령어 구성
        if llm_type == "claude":
            cmd = ["claude", "-o", "text"]
        elif llm_type == "codex":
            cmd = ["codex", "-o", "text"]
        else:
            cmd = ["gemini", "-o", "text"]

        try:
            # 표준 입력을 통해 프롬프트를 전달
            result = subprocess.run(
                cmd, 
                input=prompt,
                capture_output=True, 
                text=True, 
                encoding="utf-8",
                shell=True
            )
            
            if result.returncode == 0:
                # 성공 시 현재 전역 LLM 타입을 업데이트하여 다음 호출에서도 이 CLI를 먼저 사용하게 함
                CURRENT_LLM_TYPE = llm_type
                
                # 출력 결과 정제
                output = result.stdout.strip()
                # 불필요한 ANSI 제어 문자 제거 (있는 경우)
                output = re.sub(r'\x1B[@-_][0-?]*[ -/]*[@-~]', '', output)
                return output
            else:
                print(f"    [!] {llm_type} CLI 오류 (코드 {result.returncode}): {result.stderr.strip()[:100]}...")
                print(f"    [*] 다른 CLI로 재시도를 시도합니다.")
        
        except Exception as e:
            print(f"  [!] {llm_type} CLI 호출 실패: {e}")
            print(f"  [*] 다른 CLI로 재시도를 시도합니다.")
            
    print("  [!!] 모든 사용 가능한 LLM CLI 호출에 실패했습니다.")
    return None

def generate_messages():
    targets = get_generation_targets()
    if not targets:
        print("[*] 새롭게 생성할 메시지가 없습니다.")
        return

    product_content = PRODUCT_MD.read_text(encoding="utf-8") if PRODUCT_MD.exists() else ""
    
    print(f"[*] 총 {len(targets)}명의 메시지 생성을 시작합니다...")
    MESSAGES_DIR.mkdir(parents=True, exist_ok=True)

    for t in targets:
        print(f"  - {t['name']} ({t['type']}) 생성 중...")
        
        template_file = TEMPLATES_DIR / ("follow_up.md" if "followup" in t['type'] else "first_contact.md")
        template = template_file.read_text(encoding="utf-8") if template_file.exists() else ""

        prompt = f"""
다음 정보를 바탕으로 LinkedIn 아웃리치 메시지를 생성해서 {t['path'].name} 파일에 저장할 내용만 출력해줘.
형식은 상단에 YAML 메타데이터(바이어, 회사, 유형, 생성일)를 포함한 마크다운 형식이어야 해.

[제품 정보]
{product_content}

[바이어 정보]
이름: {t['name']}
직함: {t['info'].get('직함')}
회사: {t['info'].get('회사')}
메모: {t['info'].get('메모')}

[가이드라인]
{template}

유형: {t['type']}
오늘 날짜: {datetime.now().strftime('%Y-%m-%d')}
"""
        
        content = call_llm_cli(prompt)
        if content:
            # CLI 응답에서 마크다운 블록 제거
            content = re.sub(r"^```markdown\n|```$", "", content, flags=re.MULTILINE).strip()
            
            # 설명글 제거: 첫 번째 --- 구분선부터 끝까지만 추출
            if "---" in content:
                # 첫 번째 --- 이후의 텍스트만 유지
                content = content[content.find("---"):]
                # 마지막 --- 뒤에 실제 메시지 본문이 있을 것이므로, 메타데이터 구조를 강하게 유지
            
            t['path'].write_text(content, encoding="utf-8")
            print(f"    [+] 저장 완료: {t['path'].name}")
        else:
            print(f"    [!] 생성 실패")

if __name__ == "__main__":
    generate_messages()
