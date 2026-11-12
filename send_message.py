"""텍스트 파일을 텔레그램으로 보내기. '=====' 줄로 나누면 메시지 여러 개로 보냄.

사용: python send_message.py strategy_message.txt   (TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 환경변수 필요)
"""
import os
import sys
import time

import requests


def main() -> None:
    token, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        sys.exit("TELEGRAM_TOKEN / TELEGRAM_CHAT_ID 가 없습니다.")
    text = open(sys.argv[1], encoding="utf-8").read()
    parts = [p.strip() for p in text.split("\n=====\n") if p.strip()]
    for i, part in enumerate(parts, 1):
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": part, "parse_mode": "HTML",
                                "disable_web_page_preview": True}, timeout=20)
        if not r.ok:
            sys.exit(f"{i}번째 메시지 전송 실패: {r.status_code} {r.json().get('description')}")
        print(f"{i}/{len(parts)} 전송 완료 ({len(part)}자)")
        time.sleep(1)


if __name__ == "__main__":
    main()
