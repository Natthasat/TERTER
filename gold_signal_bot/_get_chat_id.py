import requests

token = "8162489453:AAHXLi65ypLqGYnqeO05Ym0UHtkdRe-od0I"
r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates")
data = r.json()

if data.get("result"):
    seen = set()
    for item in data["result"]:
        msg = item.get("message") or item.get("edited_message")
        if not msg:
            continue
        chat = msg["chat"]
        cid = chat["id"]
        if cid not in seen:
            seen.add(cid)
            name = chat.get("first_name", "") + " " + chat.get("last_name", "")
            print(f"Chat ID: {cid}  |  Name: {name.strip()}")
    print(f"\nTotal unique users: {len(seen)}")
else:
    print("No messages found")
    print(data)
