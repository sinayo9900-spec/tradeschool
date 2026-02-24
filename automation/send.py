import argparse
import asyncio
import csv
import sys
import os
import re
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
BUYERS_CSV = BASE_DIR / "data" / "buyers.csv"
OUTREACH_CSV = BASE_DIR / "data" / "outreach.csv"
MESSAGES_DIR = BASE_DIR / "output" / "messages"

# config 로드
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import config
except ImportError:
    print("[!] automation/config.py가 없습니다.")
    print("    config.example.py를 config.py로 복사한 후 정보를 입력하세요.")
    print("    > copy automation\\config.example.py automation\\config.py")
    sys.exit(1)

from linkedin_bot import LinkedInBot


def read_buyers() -> list[dict]:
    """buyers.csv를 읽어 dict 리스트로 반환한다."""
    if not BUYERS_CSV.exists():
        return []
    with open(BUYERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if row and any(row.values())]


def read_outreach() -> list[dict]:
    """outreach.csv를 읽어 dict 리스트로 반환한다."""
    if not OUTREACH_CSV.exists():
        return []
    with open(OUTREACH_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if row and any(row.values())]


def write_outreach(rows: list[dict]):
    """outreach.csv를 덮어쓴다."""
    fieldnames = ["이름", "회사", "상태", "첫발송일", "후속발송일", "메모"]
    with open(OUTREACH_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def find_message_file(buyer_name: str, is_followup: bool = False) -> str | None:
    """바이어의 메시지 파일을 찾아 내용을 반환한다. 후속 메시지인 경우 가장 높은 번호를 찾는다."""
    if not is_followup:
        first_msg = MESSAGES_DIR / f"{buyer_name}_first.md"
        if first_msg.exists():
            return first_msg.read_text(encoding="utf-8")
    else:
        # 후속 메시지 (followup_1, followup_2 ...) 중 가장 큰 번호 찾기
        followups = list(MESSAGES_DIR.glob(f"{buyer_name}_followup_*.md"))
        if followups:
            # 숫자가 가장 높은 파일을 선택
            latest_f = max(followups, key=lambda x: int(re.search(r"followup_(\d+)", x.name).group(1)) if re.search(r"followup_(\d+)", x.name) else 0)
            return latest_f.read_text(encoding="utf-8")
        
        # 만약 followup_N 형식이 아니면 일반 패턴으로 찾기
        for f in MESSAGES_DIR.glob(f"{buyer_name}_followup*.md"):
            return f.read_text(encoding="utf-8")

    return None


def extract_message_body(content: str) -> str:
    """메시지 파일에서 메타데이터를 제거하고 본문만 추출한다."""
    # YAML frontmatter 제거
    pattern = r"^---\s*\n.*?\n---\s*\n"
    body = re.sub(pattern, "", content, flags=re.DOTALL).strip()
    return body


def get_send_targets(buyers: list[dict], outreach: list[dict], name_filter: str | None = None) -> list[dict]:
    """발송 대상 바이어 목록을 반환한다 (대기자 + 7일 경과 후속 대상)."""
    today = datetime.now()
    targets = []

    for row in outreach:
        name = (row.get("이름") or "").strip()
        status = (row.get("상태") or "").strip()
        if not name: continue
        if name_filter and name != name_filter: continue

        # 1. 대상 여부 및 메시지 유형 결정
        is_target = False
        is_followup = False
        
        if status == "대기":
            is_target = True
            is_followup = False
        elif status == "발송":
            # 날짜 체크 (첫발송일 또는 마지막 후속발송일로부터 7일 경과)
            last_date_str = row.get("후속발송일") or row.get("첫발송일")
            if last_date_str:
                try:
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                    days_passed = (today - last_date).days
                    if days_passed >= 7:
                        is_target = True
                        is_followup = True
                except ValueError:
                    pass

        if not is_target:
            continue

        # 2. 바이어 기본 정보 가져오기
        buyer_info = next((b for b in buyers if (b.get("이름") or "").strip() == name), None)
        if not buyer_info or not (buyer_info.get("LinkedIn URL") or "").strip():
            continue

        # 3. 메시지 파일 확인
        msg_content = find_message_file(name, is_followup=is_followup)
        if not msg_content:
            continue

        targets.append({
            "name": name,
            "company": buyer_info.get("회사", ""),
            "url": buyer_info.get("LinkedIn URL", ""),
            "message": extract_message_body(msg_content),
            "full_message": msg_content,
            "is_followup": is_followup
        })

    return targets


def update_outreach_status(name: str, outreach: list[dict], is_followup: bool = False) -> list[dict]:
    """바이어의 outreach 상태 및 날짜를 업데이트한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    found = False

    for row in outreach:
        if (row.get("이름") or "").strip() == name:
            row["상태"] = "발송"
            if is_followup:
                row["후속발송일"] = today
            else:
                row["첫발송일"] = today
            found = True
            break

    if not found:
        # outreach에 없는 경우 새로 추가
        buyers = read_buyers()
        company = ""
        for b in buyers:
            if (b.get("이름") or "").strip() == name:
                company = b.get("회사", "")
                break
        outreach.append({
            "이름": name,
            "회사": company,
            "상태": "발송",
            "첫발송일": today,
            "후속발송일": "",
            "메모": "",
        })

    return outreach


async def run_login():
    """로그인 모드 실행."""
    bot = LinkedInBot(config)
    await bot.login()


async def run_send(args):
    """발송 모드 실행."""
    # 메시지 자동 생성기 실행
    print("[*] 메시지 생성 상태 확인 중...")
    try:
        subprocess.run([sys.executable, str(BASE_DIR / "automation" / "generator.py")], check=True)
    except Exception as e:
        print(f"[!] 메시지 생성기 실행 중 오류 발생: {e}")

    buyers = read_buyers()
    outreach = read_outreach()

    targets = get_send_targets(buyers, outreach, name_filter=args.name)

    if not targets:
        print("[!] 발송 대상이 없습니다.")
        print("    - 상태가 '대기'이고 _first.md 메시지가 있는 바이어")
        print("    - 마지막 발송(첫/후속) 후 7일이 지났고 _followup_N.md 메시지가 있는 바이어")
        return

    # 일일 한도 적용
    limit = args.limit or getattr(config, "DAILY_LIMIT", 20)
    if len(targets) > limit:
        print(f"[!] 대상 {len(targets)}명 중 일일 한도 {limit}명만 발송합니다.")
        targets = targets[:limit]

    # 대상 목록 표시
    print("\n" + "=" * 50)
    print(f"발송 대상 ({len(targets)}명):")
    print("=" * 50)
    for i, t in enumerate(targets, 1):
        type_str = "후속 메시지" if t["is_followup"] else "첫 연락"
        msg_preview = t["message"][:60].replace("\n", " ") + "..."
        print(f"  {i}. {t['name']} ({t['company']}) [{type_str}]")
        print(f"     URL: {t['url']}")
        print(f"     메시지: {msg_preview}")
        print()

    if args.dry_run:
        print("[DRY RUN] 미리보기 모드 - 실제 발송하지 않습니다.")
        return

    # 사용자 확인
    confirm = input("발송하시겠습니까? (y/n): ").strip().lower()
    if confirm != "y":
        print("[*] 발송을 취소했습니다.")
        return

    # 브라우저 시작
    bot = LinkedInBot(config)
    await bot.start(headless=False)

    # 세션 확인
    if not await bot.check_session():
        print("[!] LinkedIn 세션이 만료되었습니다.")
        print("    python automation/send.py --login 으로 다시 로그인하세요.")
        await bot.close()
        return

    # 발송 시작
    success_count = 0
    fail_count = 0
    results = []

    for i, target in enumerate(targets):
        print(f"\n[{i+1}/{len(targets)}] {target['name']} ({target['company']})")
        print(f"  유형: {'후속' if target['is_followup'] else '첫 연락'}")

        try:
            status = await bot.is_connected(target["url"])
            print(f"  연결 상태: {status}")

            sent = False
            if status == "connected":
                sent = await bot.send_direct_message(target["url"], target["message"])
            elif status == "not_connected":
                sent = await bot.send_connection_request(target["url"], target["message"])
            elif status == "pending":
                if target["is_followup"]:
                    print("  [*] 커넥션 보류 중이나 후속 메시지이므로 DM 전송 시도 불가 (취소)")
                    sent = False
                else:
                    print("  [*] 이미 커넥션 요청이 보류 중입니다. 건너뜁니다.")
                    results.append({"name": target["name"], "status": "skipped_pending"})
                    continue
            else:
                sent = await bot.send_connection_request(target["url"], target["message"])

            if sent:
                success_count += 1
                outreach = update_outreach_status(target["name"], outreach, is_followup=target["is_followup"])
                write_outreach(outreach)
                results.append({"name": target["name"], "status": "sent"})
                print(f"  [+] outreach.csv 업데이트 완료 ({'후속발송일' if target['is_followup'] else '첫발송일'})")
            else:
                fail_count += 1
                results.append({"name": target["name"], "status": "failed"})

        except Exception as e:
            print(f"  [!] 오류 발생: {e}")
            fail_count += 1
            results.append({"name": target["name"], "status": "error", "error": str(e)})

        # 마지막이 아닌 경우 딜레이
        if i < len(targets) - 1:
            await bot.random_delay()

    await bot.close()

    # 완료 리포트
    print("\n" + "=" * 50)
    print("발송 완료 리포트")
    print("=" * 50)
    print(f"  성공: {success_count}건")
    print(f"  실패: {fail_count}건")
    print(f"  건너뜀: {len(targets) - success_count - fail_count}건")
    print()
    for r in results:
        status_text = {
            "sent": "성공",
            "failed": "실패",
            "error": f"오류 - {r.get('error', '')}",
            "skipped_pending": "건너뜀 (보류 중)",
            "skipped_unknown": "건너뜀 (상태 불명)",
        }.get(r["status"], r["status"])
        print(f"  - {r['name']}: {status_text}")


def main():
    parser = argparse.ArgumentParser(description="LinkedIn 메시지 자동 발송")
    parser.add_argument("--login", action="store_true", help="LinkedIn 로그인 (첫 실행 시)")
    parser.add_argument("--name", type=str, help="특정 바이어만 발송")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 모드 (실제 발송 안 함)")
    parser.add_argument("--limit", type=int, help=f"일일 발송 한도 (기본: {getattr(config, 'DAILY_LIMIT', 20)})")

    args = parser.parse_args()

    if args.login:
        asyncio.run(run_login())
    else:
        asyncio.run(run_send(args))


if __name__ == "__main__":
    main()
