"""
Telegram Webhook Setup Utility.
Sets or removes the webhook URL for @Yerim_art_bot.
Usage:
  python set_webhook.py https://your-domain.vercel.app/api
  python set_webhook.py delete
"""

import sys
import os
import requests

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not TOKEN:
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    TOKEN = line.split("=", 1)[1].strip()
if not TOKEN:
    TOKEN = "8928648585:AAEDJvB9K-GRSCdGNI6-_EwCMQgS1SI_1gs"

def check_status():
    url = f"https://api.telegram.org/bot{TOKEN}/getWebhookInfo"
    r = requests.get(url).json()
    print("\n[현재 텔레그램 웹훅 상태]")
    print(f"  • 활성화 여부: {'예' if r.get('result', {}).get('url') else '아니오 (로컬 폴링 대기중)'}")
    print(f"  • 등록된 URL: {r.get('result', {}).get('url') or '(없음)'}")
    print(f"  • 대기 중 업데이트 수: {r.get('result', {}).get('pending_update_count', 0)}")
    last_err = r.get('result', {}).get('last_error_message')
    if last_err:
        print(f"  • 마지막 오류: {last_err}")
    print()

def set_webhook(webhook_url: str):
    webhook_url = webhook_url.strip()
    if not webhook_url.startswith("https://"):
        print("[오류] 텔레그램 웹훅 URL은 반드시 'https://' 로 시작해야 합니다.")
        return

    # Delete any pending updates and set webhook
    url = f"https://api.telegram.org/bot{TOKEN}/setWebhook"
    payload = {
        "url": webhook_url,
        "drop_pending_updates": True,
        "allowed_updates": ["message", "callback_query"]
    }
    r = requests.post(url, json=payload).json()
    if r.get("ok"):
        print(f"\n[성공] 텔레그램 웹훅이 등록되었습니다!")
        print(f"  --> 등록 URL: {webhook_url}")
        print("  --> 이제 PC를 종료해도 텔레그램의 모든 명령어와 버튼이 클라우드에서 24시간 작동합니다!\n")
    else:
        print(f"\n[실패] 웹훅 등록 오류: {r.get('description')}\n")

def delete_webhook():
    url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    r = requests.post(url, json={"drop_pending_updates": True}).json()
    if r.get("ok"):
        print("\n[성공] 웹훅이 해제되었습니다. 로컬 컴퓨터의 python bot.py 로 복귀할 수 있습니다.\n")
    else:
        print(f"\n[실패] 웹훅 해제 오류: {r.get('description')}\n")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        check_status()
        print("사용법:")
        print("  python set_webhook.py https://[클라우드주소]/api")
        print("  python set_webhook.py delete (로컬 폴링 모드로 전환 시)")
        sys.exit(0)

    arg = sys.argv[1].strip()
    if arg.lower() in ("delete", "remove", "clear"):
        delete_webhook()
    else:
        set_webhook(arg)
    check_status()
