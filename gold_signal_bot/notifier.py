# ============================================================
# notifier.py — ส่งแจ้งเตือนผ่าน Telegram (รองรับหลาย user)
# ============================================================

from __future__ import annotations
import requests


# ─── ส่งข้อความ (คนเดียว) ────────────────────────────────────
def send_text(bot_token: str, chat_id: str, text: str) -> bool:
    """ส่งข้อความ text ไปยัง Telegram chat เดียว"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        resp = requests.post(url, data=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[Telegram] ส่งข้อความสำเร็จ ✓ (chat={chat_id})")
            return True
        else:
            print(f"[Telegram] ส่งข้อความล้มเหลว — HTTP {resp.status_code} (chat={chat_id})")
            return False
    except requests.RequestException as e:
        print(f"[Telegram] error — {e}")
        return False


# ─── ส่งรูปภาพ (คนเดียว) ────────────────────────────────────
def send_image(bot_token: str, chat_id: str, image_path: str, caption: str = "") -> bool:
    """ส่งรูปภาพ (photo) พร้อม caption ไปยัง Telegram chat เดียว"""
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    payload = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
    try:
        with open(image_path, "rb") as img:
            files = {"photo": img}
            resp = requests.post(url, data=payload, files=files, timeout=15)
        if resp.status_code == 200:
            print(f"[Telegram] ส่งรูปสำเร็จ ✓ (chat={chat_id})")
            return True
        else:
            print(f"[Telegram] ส่งรูปล้มเหลว — HTTP {resp.status_code} (chat={chat_id})")
            return False
    except FileNotFoundError:
        print(f"[Telegram] ไม่พบไฟล์รูป: {image_path}")
        return False
    except requests.RequestException as e:
        print(f"[Telegram] error — {e}")
        return False


# ─── Broadcast ส่งทุกคน ──────────────────────────────────────
def broadcast_text(bot_token: str, chat_ids: list[str], text: str) -> None:
    """ส่งข้อความไปยังทุก chat_id ใน list"""
    for cid in chat_ids:
        send_text(bot_token, cid, text)


def broadcast_image(bot_token: str, chat_ids: list[str], image_path: str, caption: str = "") -> None:
    """ส่งรูปไปยังทุก chat_id ใน list"""
    for cid in chat_ids:
        send_image(bot_token, cid, image_path, caption)
