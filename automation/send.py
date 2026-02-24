import argparse
import asyncio
import csv
import sys
import os
import re
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
    with open(BUYERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def read_outreach() -> list[dict]:
    """outreach.csv를 읽어 dict 리스트로 반환한다."""
    with open(OUTREACH_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def write_outreach(rows: list[dict]):
    """outreach.csv를 덮어쓴다."""
    fieldnames = ["이름", "회사", "상태", "첫발송일", "후속발송일", "메모"]
    with open(OUTREACH_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def find_message_file(buyer_name: str) -> str | None:
    """바이어의 메시지 파일을 찾아 내용을 반환한다."""
    # 첫 메시지 파일 찾기
    first_msg = MESSAGES_DIR / f"{buyer_name}_first.md"
    if first_msg.exists():
        return first_msg.read_text(encoding="utf-8")

    # 패턴 매칭으로 찾기
    for f in MESSAGES_DIR.glob(f"{buyer_name}_*.md"):
        return f.read_text(encoding="utf-8")

    return None


def extract_message_body(content: str) -> str:
    """메시지 파일에서 메타데이터를 제거하고 본문만 추출한다."""
    # YAML frontmatter 제거
    pattern = r"^---\s*\n.*?\n---\s*\n"
    body = re.sub(pattern, "", content, flags=re.DOTALL).strip()
    return body


def get_send_targets(buyers: list[dict], outreach: list[dict], name_filter: str | None = None) -> list[dict]:
    """발송 대상 바이어 목록을 반환한다."""
    # outreach에서 상태가 "대기"인 바이어 이름 집합
    waiting_names = set()
    for row in outreach:
        if row.get("상태", "").strip() == "대기":
            waiting_names.add(row["이름"].strip())

    targets = []
    for buyer in buyers:
        name = buyer.get("이름", "").strip()
        url = buyer.get("LinkedIn URL", "").strip()

        if not url:
            continue

        if name_filter and name != name_filter:
            continue

        # outreach에 없거나 "대기" 상태인 바이어만
        in_outreach = any(r["이름"].strip() == name for r in outreach)
        if in_outreach and name not in waiting_names:
            continue

        # 메시지 파일 확인
        msg_content = find_message_file(name)
        if not msg_content:
            continue

        targets.append({
            "name": name,
            "company": buyer.get("회사", ""),
            "url": url,
            "message": extract_message_body(msg_content),
            "full_message": msg_content,
        })

    return targets


def update_outreach_status(name: str, outreach: list[dict]) -> list[dict]:
    """바이어의 outreach 상태를 '발송'으로 업데이트한다."""
    today = datetime.now().strftime("%Y-%m-%d")
    found = False

    for row in outreach:
        if row["이름"].strip() == name:
            row["상태"] = "발송"
            row["첫발송일"] = today
            found = True
            break

    if not found:
        # outreach에 없는 경우 새로 추가
        buyers = read_buyers()
        company = ""
        for b in buyers:
            if b["이름"].strip() == name:
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
    buyers = read_buyers()
    outreach = read_outreach()

    targets = get_send_targets(buyers, outreach, name_filter=args.name)

    if not targets:
        print("[!] 발송 대상이 없습니다.")
        if args.name:
            print(f"    '{args.name}' 바이어의 상태가 '대기'인지, 메시지 파일이 있는지 확인하세요.")
        else:
            print("    outreach.csv에 '대기' 상태 바이어가 있는지 확인하세요.")
            print("    output/messages/ 에 메시지 파일이 있는지 확인하세요.")
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
        msg_preview = t["message"][:60].replace("\n", " ") + "..."
        print(f"  {i}. {t['name']} ({t['company']})")
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
        print(f"  URL: {target['url']}")

        try:
            status = await bot.is_connected(target["url"])
            print(f"  연결 상태: {status}")

            sent = False
            if status == "connected":
                sent = await bot.send_direct_message(target["url"], target["message"])
            elif status == "not_connected":
                sent = await bot.send_connection_request(target["url"], target["message"])
            elif status == "pending":
                print("  [*] 이미 커넥션 요청이 보류 중입니다. 건너뜁니다.")
                results.append({"name": target["name"], "status": "skipped_pending"})
                continue
            else:
                print("  [*] 연결 상태 불명 — 커넥션 요청을 시도합니다.")
                sent = await bot.send_connection_request(target["url"], target["message"])

            if sent:
                success_count += 1
                outreach = update_outreach_status(target["name"], outreach)
                write_outreach(outreach)
                results.append({"name": target["name"], "status": "sent"})
                print(f"  [+] outreach.csv 상태 업데이트 완료")
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
