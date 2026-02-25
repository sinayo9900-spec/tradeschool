import argparse
import asyncio
import csv
import sys
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
BUYERS_CSV = BASE_DIR / "data" / "buyers.csv"
OUTREACH_CSV = BASE_DIR / "data" / "outreach.csv"

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

DEFAULT_QUERIES = [
    "Singapore F&B procurement manager",
    "Singapore snack biscuit distribution",
    "Singapore food import buyer",
    "Singapore FMCG procurement",
]

MAX_PAGES_PER_QUERY = 10


def normalize_url(url: str) -> str:
    """LinkedIn URL을 정규화하여 중복 비교에 사용한다."""
    url = url.strip().lower()
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    # 경로만 남기고 쿼리파라미터 제거, 끝 슬래시 제거
    path = parsed.path.rstrip("/")
    return f"https://www.linkedin.com{path}"


def load_existing_urls() -> set[str]:
    """buyers.csv에서 기존 LinkedIn URL을 로드한다."""
    urls = set()
    if not BUYERS_CSV.exists():
        return urls
    with open(BUYERS_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            raw = (row.get("LinkedIn URL") or "").strip()
            if raw:
                urls.add(normalize_url(raw))
    return urls


def append_to_buyers(prospects: list[dict]):
    """buyers.csv에 새 바이어를 추가한다."""
    fieldnames = ["이름", "직함", "회사", "산업", "LinkedIn URL", "메모"]
    write_header = not BUYERS_CSV.exists() or BUYERS_CSV.stat().st_size == 0
    with open(BUYERS_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for p in prospects:
            # 줄바꿈 제거 처리
            writer.writerow({
                "이름": str(p["name"]).replace("\n", " ").strip(),
                "직함": str(p.get("title", "")).replace("\n", " ").strip(),
                "회사": str(p.get("company", "")).replace("\n", " ").strip(),
                "산업": "F&B Distribution",
                "LinkedIn URL": p.get("url", ""),
                "메모": str(p.get("memo", "")).replace("\n", " ").strip(),
            })


def append_to_outreach(prospects: list[dict]):
    """outreach.csv에 새 바이어를 '대기' 상태로 추가한다."""
    fieldnames = ["이름", "회사", "상태", "첫발송일", "후속발송일", "메모"]
    write_header = not OUTREACH_CSV.exists() or OUTREACH_CSV.stat().st_size == 0
    with open(OUTREACH_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        for p in prospects:
            # 줄바꿈 제거 처리
            writer.writerow({
                "이름": str(p["name"]).replace("\n", " ").strip(),
                "회사": str(p.get("company", "")).replace("\n", " ").strip(),
                "상태": "대기",
                "첫발송일": "",
                "후속발송일": "",
                "메모": "",
            })


async def run_login():
    """로그인 모드 실행."""
    bot = LinkedInBot(config)
    await bot.login()


async def run_search(args):
    """검색 모드 실행."""
    queries = [args.query] if args.query else DEFAULT_QUERIES
    limit = args.limit
    dry_run = args.dry_run
    skip_profiles = args.skip_profiles

    # Phase 1: 검색 결과 수집
    print("=" * 50)
    print("Phase 1: 검색 결과 수집")
    print("=" * 50)

    existing_urls = load_existing_urls()
    print(f"[*] 기존 바이어 URL {len(existing_urls)}건 로드 (중복 체크용)")

    bot = LinkedInBot(config)
    await bot.start(headless=False)

    if not await bot.check_session():
        print("[!] LinkedIn 세션이 만료되었습니다.")
        print("    python automation/search.py --login 으로 다시 로그인하세요.")
        await bot.close()
        return

    prospects = []
    seen_urls = set(existing_urls)

    for query in queries:
        if len(prospects) >= limit:
            break

        print(f"\n[검색] \"{query}\"")

        for page_num in range(1, MAX_PAGES_PER_QUERY + 1):
            if len(prospects) >= limit:
                break

            print(f"  페이지 {page_num}...")
            await bot.search_people(query, page=page_num)
            results = await bot.parse_search_results()

            if not results:
                print(f"  결과 없음 — 다음 검색어로 이동")
                break

            new_count = 0
            for r in results:
                if len(prospects) >= limit:
                    break
                norm = normalize_url(r["url"]) if r["url"] else ""
                if not norm or norm in seen_urls:
                    continue
                seen_urls.add(norm)
                prospects.append(r)
                new_count += 1

            print(f"  → 신규 {new_count}건 수집 (누적 {len(prospects)}건)")

            if new_count == 0:
                print(f"  신규 결과 없음 — 다음 검색어로 이동")
                break

            # 페이지 간 딜레이
            if page_num < MAX_PAGES_PER_QUERY and len(prospects) < limit:
                await bot.random_delay()

    print(f"\n[*] Phase 1 완료: {len(prospects)}건 수집")

    # Phase 2: 프로필 상세 수집
    if not skip_profiles and prospects:
        print("\n" + "=" * 50)
        print("Phase 2: 프로필 상세 수집")
        print("=" * 50)

        for i, p in enumerate(prospects):
                print(f"\n  [{i+1}/{len(prospects)}] {p['name']} — {p['url']}")
                try:
                    # 프로필 페이지 방문 및 소개/경력 추출
                    about = await bot.get_profile_about(p["url"])
                    
                    # 1. 상세 경력 추출 시도
                    exp_title, exp_company = await bot.get_current_experience()
                    
                    # 2. 실패 시 상단 헤드라인에서 추출 시도
                    if not exp_title:
                        headline = await bot.get_profile_headline()
                        if headline:
                            exp_title, exp_company = bot._parse_headline(headline)

                    # 경력 정보가 추출되었다면 업데이트
                    if exp_title:
                        p["title"] = exp_title
                    if exp_company:
                        p["company"] = exp_company
                    
                    post = await bot.get_latest_post(p["url"])

                    memo_parts = []
                    if about:
                        memo_parts.append(f"[소개] {about}")
                    if post:
                        memo_parts.append(f"[최근포스트] {post}")
                    if p.get("location"):
                        memo_parts.append(f"[위치] {p['location']}")

                    p["memo"] = " | ".join(memo_parts)
                    print(f"    직함/회사: {p['title']} @ {p['company']}")
                    
                    # 실시간 저장: 한 명의 정보를 완성할 때마다 CSV에 추가
                    if not dry_run:
                        append_to_buyers([p])
                        append_to_outreach([p])
                        print(f"    [+] 실시간 저장 완료")

                except Exception as e:
                    print(f"    [!] 프로필 수집 실패: {e}")
                    if p.get("location"):
                        p["memo"] = f"[위치] {p['location']}"
                    # 실패하더라도 기본 정보는 저장
                    if not dry_run:
                        append_to_buyers([p])
                        append_to_outreach([p])

                # 프로필 간 딜레이
                if i < len(prospects) - 1:
                    await bot.random_delay()

    else:
        # skip-profiles: 위치 정보만 메모에 저장하고 일괄 저장
        for p in prospects:
            if p.get("location"):
                p["memo"] = f"[위치] {p['location']}"
        
        if not dry_run:
            append_to_buyers(prospects)
            append_to_outreach(prospects)
            print(f"\n[+] {len(prospects)}건 일괄 저장 완료")

    await bot.close()
    print(f"\n[*] Phase 2 완료")

    # Phase 3: 결과 표시
    print("\n" + "=" * 50)
    print(f"수집 프로세스 종료 (총 {len(prospects)}건 처리)")
    print("=" * 50)

    if not prospects:
        print("[!] 수집된 바이어가 없습니다.")
        return

    # 테이블 출력 (이미 저장되었으므로 목록만 표시)
    print(f"{'#':<4} {'이름':<20} {'직함':<25} {'회사':<20} {'위치':<15}")
    print("-" * 84)
    for i, p in enumerate(prospects, 1):
        name = str(p["name"])[:18]
        title = str(p.get("title", ""))[:23]
        company = str(p.get("company", ""))[:18]
        location = str(p.get("location", ""))[:13]
        print(f"{i:<4} {name:<20} {title:<25} {company:<20} {location:<15}")



def main():
    parser = argparse.ArgumentParser(description="LinkedIn 바이어 검색 자동화")
    parser.add_argument("--query", type=str, help="검색어 (없으면 기본 검색어 4개 순회)")
    parser.add_argument("--limit", type=int, default=20, help="최대 수집 인원 (기본: 20)")
    parser.add_argument("--dry-run", action="store_true", help="미리보기 모드 (CSV 저장 안 함)")
    parser.add_argument("--skip-profiles", action="store_true", help="검색 결과만 수집 (프로필 방문 생략)")
    parser.add_argument("--login", action="store_true", help="LinkedIn 로그인 모드")

    args = parser.parse_args()

    if args.login:
        asyncio.run(run_login())
    else:
        asyncio.run(run_search(args))


if __name__ == "__main__":
    main()
