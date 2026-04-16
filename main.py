"""
DramaNova Bot — Main Orchestrator (sansekai API)
Telegram bot with Auto & Manual modes.

Workflow (LOCKED):
  1. Detection -> API /home or /search
  2. Scraping  -> /detail?dramaId=
  3. Download  -> /getvideo?fileId= + subtitle URL
  4. Subtitle Check -> WAJIB ada, kalau tidak -> SKIP TOTAL
  5. Merge     -> HARDSUB WAJIB
  6. Upload    -> hanya jika merge sukses + hardsubbed
  7. Cleanup   -> hapus semua file sementara
"""
import os
import sys
import asyncio
import logging
import json
import shutil
import subprocess
import time

from telethon import TelegramClient, events

from config import (
    BASE_URL,
    API_TOKEN,
    API_ID,
    API_HASH,
    BOT_TOKEN,
    CHANNEL_ID,
    TOPIC_ID,
    ADMIN_IDS,
    DOWNLOAD_DIR,
    MERGE_DIR,
    TEMP_DIR,
    AUTO_MODE_ENABLED,
    AUTO_CHECK_INTERVAL,
)
from api import DramaNovaAPI
from downloader import Downloader
from merge import merge_all_episodes
from uploader import Uploader

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-22s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dramanova.main")

# ─── Fix Windows asyncio ────────────────────────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ─── Globals ─────────────────────────────────────────────────
client = TelegramClient("dramanova_bot", API_ID, API_HASH)
api = DramaNovaAPI()
downloader = Downloader(api)
uploader = Uploader(client)

# Permanent Queue & History Tracking
PROCESSED_FILE = "processed.json"
processed_ids: set[str] = set()
processing_lock = asyncio.Lock()

def load_processed():
    global processed_ids
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r") as f:
                data = json.load(f)
                processed_ids = set(data)
                log.info(f"📜 Loaded {len(processed_ids)} processed dramas from history.")
        except Exception as e:
            log.warning(f"⚠️ Failed to load processed.json: {e}")

def save_processed():
    try:
        with open(PROCESSED_FILE, "w") as f:
            json.dump(list(processed_ids), f)
    except Exception as e:
        log.error(f"❌ Failed to save processed.json: {e}")

# Call load at startup
load_processed()
auto_mode_active: bool = AUTO_MODE_ENABLED
auto_task: asyncio.Task | None = None


# =====================================================================
# CORE PIPELINE
# =====================================================================

async def process_drama(drama_id: str, event=None) -> bool:
    """
    Full pipeline for a single drama.
    Returns True on success.
    """
    async with processing_lock:
        if drama_id in processed_ids:
            return False

        # ─── Setup Progress Tracking ─────────────────────────
        status_msg = None
        target_chat = event.chat_id if event else ADMIN_IDS[0] if ADMIN_IDS else None
        last_update = 0
        
        # Consistent Status Header
        header = f"🚀 **DramaNova Processing**\n🆔 `{drama_id}`\n────────────────────\n"

        if target_chat:
            status_msg = await client.send_message(target_chat, header + "⌛ Inisialisasi...")

        async def update_status(text: str, force: bool = False):
            nonlocal last_update
            if not status_msg: return
            
            now = time.time()
            # Throttle to 1.5s to avoid flood, unless forced (e.g. final result)
            if force or (now - last_update) >= 1.5:
                try:
                    # Prepend header if not already there
                    full_text = text if text.startswith("🚀") else header + text
                    await status_msg.edit(full_text)
                    last_update = now
                except Exception as e:
                    log.debug(f"Update status failed: {e}")
                    pass

        try:
            # ─── Step 1-2: Fetch detail ──────────────────────
            log.info(f"Fetching detail for drama: {drama_id}")
            detail = await api.get_detail(drama_id)
            drama_info = api.extract_drama_info(detail)
            title = drama_info["title"]
            
            # Map episodes correctly using extract_episode_info
            raw_eps = detail.get("episodes", [])
            episodes = [api.extract_episode_info(ep) for ep in raw_eps]
            
            # Formatted Header for all updates
            info_header = (
                f"🆕 **DramaNova Detection!**\n"
                f"🎬 `{title}`\n"
                f"🆔 `{drama_id}`\n"
                f"⌛ Processing...\n"
                f"────────────────────\n"
            )

            if not episodes:
                msg = f"❌ Tidak ada episode ditemukan."
                log.error(msg)
                await update_status(info_header + msg, force=True)
                return False

            # ─── Step 3-4: Download + Subtitle Check ─────────
            episodes_with_subs = [ep for ep in episodes if ep.get("subtitle")]

            if not episodes_with_subs:
                msg = f"❌ Subtitle tidak tersedia (Hardsub wajib) -> SKIP"
                await update_status(info_header + msg, force=True)
                return False

            total_eps = len(episodes_with_subs)
            await update_status(info_header + f"⬇️ Memulai download {total_eps} eps...", force=True)

            # Progress callback for downloader
            async def dl_progress(current_ep, ep_pct):
                await update_status(
                    f"{info_header}"
                    f"⬇️ **Downloading...**\n"
                    f"📦 Episode: {current_ep}/{total_eps}\n"
                    f"📊 Progress: `{ep_pct:.1f}%`"
                )

            downloaded = await downloader.download_all_episodes(
                episodes_with_subs, title, progress_callback=dl_progress
            )

            if not downloaded:
                msg = f"❌ Semua download gagal."
                await update_status(info_header + msg, force=True)
                return False

            # ─── Step 5: Merge (HARDSUB WAJIB) ──────────────
            await update_status(info_header + "🎬 **Merging & Hardsubbing...**\n(Proses ini cukup lama)", force=True)
            
            async def merge_progress(ep_num, pct):
                await update_status(
                    f"{info_header}"
                    f"🎬 **Merging & Hardsubbing...**\n"
                    f"📦 Episode: {ep_num}/{total_eps}\n"
                    f"📊 Progress: `{pct:.1f}%`"
                )

            final_path = await merge_all_episodes(downloaded, title, progress_callback=merge_progress)

            # ─── Step 6: Upload ──────────────────────────────
            
            # Send details message first (Poster + Synopsis)
            await update_status(info_header + "📤 **Mengirim Detail & Poster...**", force=True)
            await uploader.send_details(drama_info)

            # Then upload the video
            async def ul_progress(current, total):
                pct = (current / total) * 100
                await update_status(
                    f"{info_header}"
                    f"📤 **Uploading Video...**\n"
                    f"📊 Progress: `{pct:.1f}%`"
                )

            await update_status(info_header + "📤 **Memulai Upload Video...**", force=True)
            await uploader.upload_video(final_path, drama_title=title, progress_callback=ul_progress)

            # ─── Step 6: Cleanup & Store ─────────────────────
            await update_status(info_header + "✅ **Selesai!** Membersihkan folder...", force=True)
            safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in title).strip()
            if os.path.exists(os.path.join(DOWNLOAD_DIR, safe_title)):
                shutil.rmtree(os.path.join(DOWNLOAD_DIR, safe_title))
            
            processed_ids.add(drama_id)
            save_processed()
            log.info(f"✅ Full Process Done: {title}")
            return True

        except Exception as e:
            msg = f"❌ **Error Encountered!**\n🎬 `{title if 'title' in locals() else drama_id}`\n────────────────────\n⚠️ **Reason:** `{str(e)}`"
            log.error(f"Process failed: {e}", exc_info=True)
            await update_status(msg, force=True)
            return False

        finally:
            # ─── Step 7: Final Cleanup (ALWAYS RUN) ─────────
            try:
                log.info(f"🧹 Cleaning up after title: {drama_id}")
                safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in (title if 'title' in locals() else "")).strip()
                
                # Remove download folder
                if safe_title:
                    dl_path = os.path.join(DOWNLOAD_DIR, safe_title)
                    if os.path.exists(dl_path): shutil.rmtree(dl_path, ignore_errors=True)
                
                # Remove merged files
                if safe_title:
                    m_path = os.path.join(MERGE_DIR, f"{safe_title}_final.mp4")
                    if os.path.exists(m_path): os.remove(m_path)
                    
                # Clean temp directory completely
                for f in os.listdir(TEMP_DIR):
                    if safe_title and safe_title in f:
                        os.remove(os.path.join(TEMP_DIR, f))
            except Exception as cleanup_err:
                log.debug(f"Cleanup error (ignored): {cleanup_err}")


def global_cleanup():
    """Wipe all temporary directories on startup."""
    log.info("🧹 Performing global startup cleanup...")
    for d in [DOWNLOAD_DIR, MERGE_DIR, TEMP_DIR]:
        if os.path.exists(d):
            try:
                # Close any potential open files or Give OS a second to release locks
                shutil.rmtree(d, ignore_errors=True)
                os.makedirs(d, exist_ok=True)
                log.info(f"✨ Wiped: {os.path.basename(d)}")
            except Exception as e:
                log.warning(f"⚠️ Startup cleanup warning for {d}: {e}")

# =====================================================================
# AUTO MODE
# =====================================================================

async def auto_mode_loop():
    """Continuously check /home for new dramas and process them."""
    global auto_mode_active
    log.info("Auto mode started.")
    while auto_mode_active:
        try:
            # Fetch latest from /home
            dramas = await api.get_home(page=1)

            if isinstance(dramas, list):
                # Filter out already processed dramas
                new_dramas = [d for d in dramas if str(d.get("id")) not in processed_ids]
                
                if new_dramas:
                    log.info(f"Found {len(new_dramas)} new dramas in scan.")
                
                for drama in new_dramas:
                    if not auto_mode_active:
                        break
                    
                    drama_id = str(drama.get("id"))
                    title = drama.get("title", "Unknown")

                    log.info(f"⏳ Drama '{title}' entering queue...")
                    # The following line will block until previous process finishes
                    await process_drama(drama_id)

        except Exception as e:
            log.error(f"Auto mode error: {e}", exc_info=True)

        # Sleep in small increments so we can stop quickly
        for _ in range(int(AUTO_CHECK_INTERVAL)):
            if not auto_mode_active:
                break
            await asyncio.sleep(1)

    log.info("Auto mode stopped.")


# =====================================================================
# TELEGRAM COMMANDS
# =====================================================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@client.on(events.NewMessage(pattern=r"^/start$"))
async def cmd_start(event):
    await event.reply(
        "**DramaNova Bot**\n\n"
        "Commands:\n"
        "  `/search <judul>` - Cari drama\n"
        "  `/download <id>` - Download & proses drama\n"
        "  `/auto` - Toggle auto mode ON/OFF\n"
        "  `/panel` - Admin panel\n"
        "  `/update` - Git pull update\n\n"
        "Semua output = hardsub (subtitle wajib terbakar)"
    )


@client.on(events.NewMessage(pattern=r"^/search\s+(.+)$"))
async def cmd_search(event):
    if not is_admin(event.sender_id):
        return

    query = event.pattern_match.group(1).strip()
    msg = await event.reply(f"Mencari: **{query}**...")

    try:
        results = await api.search(query)

        if not results:
            await msg.edit(f"Tidak ditemukan: **{query}**")
            return

        items = results if isinstance(results, list) else []

        if not items:
            await msg.edit(f"Tidak ditemukan: **{query}**")
            return

        text = f"Hasil pencarian: **{query}**\n\n"
        for i, item in enumerate(items[:10], 1):
            info = api.extract_drama_info(item)
            text += (
                f"{i}. **{info['title']}**\n"
                f"   ID: `{info['id']}`\n"
                f"   Episode: {info['total_episodes']}\n\n"
            )
        text += "Gunakan `/download <id>` untuk memproses."
        await msg.edit(text)

    except Exception as e:
        await msg.edit(f"Search error: {e}")


@client.on(events.NewMessage(pattern=r"^/download\s+(\S+)$"))
async def cmd_download(event):
    if not is_admin(event.sender_id):
        return

    drama_id = event.pattern_match.group(1).strip()

    if processing_lock.locked():
        await event.reply("Sedang memproses drama lain. Tunggu selesai.")
        return

    await process_drama(drama_id, event=event)


@client.on(events.NewMessage(pattern=r"^/auto$"))
async def cmd_auto(event):
    """Toggle auto mode on/off at runtime."""
    global auto_mode_active, auto_task
    if not is_admin(event.sender_id):
        return

    if auto_mode_active:
        # Turn OFF
        auto_mode_active = False
        if auto_task and not auto_task.done():
            auto_task.cancel()
            auto_task = None
        await event.reply("Auto mode **OFF**")
        log.info("Auto mode disabled by admin")
    else:
        # Turn ON
        auto_mode_active = True
        auto_task = asyncio.create_task(auto_mode_loop())
        await event.reply(f"Auto mode **ON** - checking /home every {AUTO_CHECK_INTERVAL}s")
        log.info("Auto mode enabled by admin")


@client.on(events.NewMessage(pattern=r"^/panel$"))
async def cmd_panel(event):
    if not is_admin(event.sender_id):
        return

    auto_status = "ON" if auto_mode_active else "OFF"
    processed_count = len(processed_ids)

    text = (
        "**DramaNova Panel**\n\n"
        f"Auto Mode: {auto_status}\n"
        f"Processed: {processed_count} dramas\n"
        f"Hardsub: WAJIB (locked)\n"
        f"CRF: 23 | Preset: ultrafast\n"
        f"API: sansekai.my.id\n"
    )
    await event.reply(text)


@client.on(events.NewMessage(pattern=r"^/update$"))
async def cmd_update(event):
    if not is_admin(event.sender_id):
        return

    msg = await event.reply("🔄 **Checking for updates via git pull...**")
    try:
        # Run git pull
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )
        
        output = result.stdout.strip()
        error = result.stderr.strip()
        
        if "Already up to date" in output:
            await msg.edit("✅ **Bot is already up to date!**")
            return

        # If updated successfully
        await msg.edit(f"✅ **Update success!**\n\n```\n{output}\n```\n\n🔄 **Bot is restarting to apply changes...**")
        
        # Give a small delay for the message to be sent
        await asyncio.sleep(2)
        
        # RESTART BOT
        log.info("Restarting bot after update...")
        os.execv(sys.executable, [sys.executable] + sys.argv)

    except Exception as e:
        log.error(f"Update error: {e}")
        await msg.edit(f"❌ **Update failed:**\n`{e}`")


# =====================================================================
# ENTRY POINT
# =====================================================================

async def main():
    global auto_task
    # Perform initial global cleanup
    global_cleanup()
    
    log.info("Starting DramaNova Bot...")

    await client.start(bot_token=BOT_TOKEN)
    log.info("Bot connected to Telegram")

    if auto_mode_active:
        auto_task = asyncio.create_task(auto_mode_loop())
        log.info("Auto mode enabled (from .env)")
    else:
        log.info("Manual mode - use /auto to toggle")

    log.info("DramaNova Bot is running. Waiting for commands...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Bot stopped.")
