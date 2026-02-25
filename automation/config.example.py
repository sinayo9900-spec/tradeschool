# .env 파일에서 설정을 읽습니다.
# automation/.env 파일에서 딜레이/한도를 조정할 수 있습니다.
# 로그인은 브라우저에서 직접 수행하므로 계정 정보는 불필요합니다.

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "20"))
MIN_DELAY = int(os.getenv("MIN_DELAY", "60"))
MAX_DELAY = int(os.getenv("MAX_DELAY", "120"))
MIN_TYPE_DELAY = int(os.getenv("MIN_TYPE_DELAY", "50"))
MAX_TYPE_DELAY = int(os.getenv("MAX_TYPE_DELAY", "150"))

# LLM CLI 설정 (gemini, claude, codex 중 선택)
LLM_CLI_TYPE = os.getenv("LLM_CLI_TYPE", "gemini")
