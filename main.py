import os, ast, asyncio, requests, time, traceback
from urllib.parse import urlparse, urlsplit
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.methods.utilities.idle import idle
from playwright.async_api import async_playwright

os.system("playwright install")

API_ID = int(os.environ["api_id"])
API_HASH = os.environ["api_hash"]
BOT_TOKEN = os.environ["bot_token"]
STREAMLIT_SESSIONS = ast.literal_eval(os.environ["st_session"])
ALL_URLS = ast.literal_eval(os.environ["all_urls"])
OPEN_URLS = ast.literal_eval(os.environ["open_urls"])
CHAT_IDS = ast.literal_eval(os.environ["chat_ids"])
offset = int(os.environ["offset"])
minute_values = list(range(offset, 60, 5))  
minute_str = ",".join(str(m) for m in minute_values)
app = Client("screenshot_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")

def is_valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return parts.scheme in ("http", "https") and parts.netloc != ""
    except:
        return False

async def screenshot_url_page(url: str, output_path: str, cookie_value: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        parsed = urlparse(url)
        await context.add_cookies([{
            "name": "streamlit_session", "value": cookie_value,
            "domain": parsed.hostname, "path": "/", "secure": True, "httpOnly": False
        }])
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle", timeout=60000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        await asyncio.sleep(1)
        await page.screenshot(path=output_path, full_page=True)
        await browser.close()

async def restart_and_screenshot(session_token: str, app_data: dict, session: requests.Session):
    subdomain = app_data["subdomain"]
    app_id = app_data["appId"]
    url = ALL_URLS[3].format(subdomain=subdomain)
    status_url = ALL_URLS[4].format(subdomain=subdomain)
    restart_url = ALL_URLS[2].format(app_id=app_id)

    try:
        current_status = session.get(status_url).json().get("status")

        if current_status == 12:
            session.headers.update({"x-csrf-token": session.get(ALL_URLS[0]).headers.get("x-csrf-token", "")})
            session.post(restart_url)
        elif current_status == 5:
            for chat_id in CHAT_IDS:
                await app.send_message(chat_id=chat_id, text=f"✅ Already Running `{subdomain}`")
            return
        else:
            for chat_id in CHAT_IDS:
                await app.send_message(chat_id=chat_id, text=f"❌ Error in `{subdomain}`\nStatus: {current_status}")
            return

        start_time = time.time()
        while time.time() - start_time < 60:
            resp = session.get(status_url)
            if resp.status_code == 200 and resp.json().get("status") == 5:
                break
            await asyncio.sleep(2)
        else:
            for chat_id in CHAT_IDS:
                await app.send_message(chat_id=chat_id, text=f"❌ Timeout waiting for `{subdomain}` to restart.")
            return

        screenshot_file = os.path.join("screenshots", f"{subdomain}.png")
        os.makedirs("screenshots", exist_ok=True)
        await screenshot_url_page(url, screenshot_file, cookie_value=session_token)

        for chat_id in CHAT_IDS:
            await app.send_photo(chat_id=chat_id, photo=screenshot_file, caption=f"✅ Screenshot for `{subdomain}`")
        os.remove(screenshot_file)

    except Exception as e:
        error_text = traceback.format_exc()[-2800:]
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text=f"❌ Error in `{subdomain}`:\n`{str(e)}`\n```{error_text}```")

async def restart_streamlit_apps_and_notify(session_token: str):
    try:
        session = requests.Session()
        session.cookies.update({"streamlit_session": session_token})
        user_resp = session.get(ALL_URLS[0])
        session.headers.update({"x-csrf-token": user_resp.headers.get("x-csrf-token", "")})

        workspace_id = next(w["id"] for w in user_resp.json()["workspaces"] if not w["viewOnly"])
        apps = session.get(ALL_URLS[1] + workspace_id).json()
        app_ids = [{'appId': a['appId'], 'subdomain': a['subdomain']} for a in apps['apps'] if a['status'] == 12]

        if not app_ids:
            for chat_id in CHAT_IDS:
                await app.send_message(chat_id=chat_id, text="ℹ️ No apps pending restart.")
            return

        tasks = [restart_and_screenshot(session_token, app_data, session) for app_data in app_ids]
        await asyncio.gather(*tasks)

        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text="✅ Cron job completed successfully.")

    except Exception as e:
        error_text = traceback.format_exc()[-2800:]
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text=f"❌ Fatal error:\n`{str(e)}`\n```{error_text}```")

from hashlib import sha1

def sanitize_url(url: str) -> str:
    # Hash URL to avoid slashes, colons, etc. in filename
    return sha1(url.encode()).hexdigest()[:10]

async def open_and_screenshot_urls():
    os.makedirs("screenshots", exist_ok=True)

    try:
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text=f"📸 Starting screenshots\n🔗 URLs: {len(OPEN_URLS)}\n🧪 Sessions: {len(STREAMLIT_SESSIONS)}")

        for url in OPEN_URLS:
            for i, session_token in enumerate(STREAMLIT_SESSIONS):
                try:
                    safe_name = sanitize_url(url)
                    filename = os.path.join("screenshots", f"open_{i}_{safe_name}.png")

                    for chat_id in CHAT_IDS:
                        await app.send_message(chat_id=chat_id, text=f"⏳ Trying `{url}` (session #{i})\n📁 Filename: `{filename}`")

                    await screenshot_url_page(url, filename, session_token)

                    for chat_id in CHAT_IDS:
                        await app.send_message(chat_id=chat_id, text=f"✅ Screenshot taken for `{url}` (session #{i})")

                    # Log file size before sending
                    if not os.path.exists(filename):
                        raise FileNotFoundError(f"Screenshot file not found: {filename}")
                    file_size = os.path.getsize(filename)
                    if file_size == 0:
                        raise ValueError(f"Screenshot file is empty: {filename}")

                    for chat_id in CHAT_IDS:
                        try:
                            await app.send_photo(chat_id=chat_id, photo=filename, caption=f"📷 Screenshot for `{url}` (session #{i})")
                        except Exception as send_err:
                            err_trace = traceback.format_exc()[-2000:]
                            await app.send_message(
                                chat_id=chat_id,
                                text=f"❌ Failed to send photo for `{url}` (session #{i}):\n🛑 {send_err}\n```{err_trace}```"
                            )

                    os.remove(filename)

                except Exception as e:
                    error_text = traceback.format_exc()[-2800:]
                    for chat_id in CHAT_IDS:
                        await app.send_message(
                            chat_id=chat_id,
                            text=f"❌ Exception while processing:\n🔗 `{url}` (session #{i})\n🛑 `{str(e)}`\n```{error_text}```"
                        )

    except Exception as big_e:
        error_text = traceback.format_exc()[-2800:]
        for chat_id in CHAT_IDS:
            await app.send_message(
                chat_id=chat_id,
                text=f"🚨 FATAL in open_and_screenshot_urls loop:\n🛑 `{str(big_e)}`\n```{error_text}```"
            )


#@app.on_message(filters.private & filters.regex(r'^https?://'))
async def handle_screenshot(client: Client, message: Message):
    url = message.text.strip()
    if not is_valid_url(url):
        await message.reply("❌ Invalid URL.")
        return
    try:
        os.makedirs("screenshots", exist_ok=True)
        output_file = os.path.join("screenshots", f"screenshot_{message.chat.id}.png")
        await screenshot_url_page(url, output_file, cookie_value=STREAMLIT_SESSIONS[0])
        await message.reply_photo(photo=output_file, caption="✅ Screenshot complete")
        os.remove(output_file)
    except Exception as e:
        error_text = traceback.format_exc()[-2800:]
        await message.reply(f"❌ Error:\n`{str(e)}`\n```{error_text}```")

async def main():
    await app.start()
    scheduler.start()

    for chat_id in CHAT_IDS:
        await app.send_message(chat_id=chat_id, text="✅ All jobs scheduled.")

    # Schedule all restart jobs
    for sess in STREAMLIT_SESSIONS:
        scheduler.add_job(
            restart_streamlit_apps_and_notify,
            trigger=CronTrigger(minute=minute_str),
            args=[sess],
            id=f"offset_task_{offset}",
            replace_existing=True
        )

    # Run open URLs once at startup
    try:
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text="🚀 Starting open_and_screenshot_urls...")
        await open_and_screenshot_urls()
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text="✅ Completed open_and_screenshot_urls.")
    except Exception as e:
        error_text = traceback.format_exc()[-2800:]
        for chat_id in CHAT_IDS:
            await app.send_message(chat_id=chat_id, text=f"❌ Error during open_and_screenshot_urls:\n```{error_text}```")

    await idle()
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
