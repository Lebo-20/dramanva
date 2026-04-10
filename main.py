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
import shutil
import subprocess

from telethon import TelegramClient, events

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    CHANNEL_ID,
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
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ─── Globals ─────────────────────────────────────────────────
client = TelegramClient("dramanova_bot", API_ID, API_HASH)
api = DramaNovaAPI()
downloader = Downloader(api)
processing_lock = asyncio.Lock()
processed_ids: set[str] = set()
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

        # ─── Setup Admin Notification ────────────────────────
        status_msg = None
        target_chat = event.chat_id if event else ADMIN_IDS[0] if ADMIN_IDS else None
        last_update = 0

        if target_chat:
            status_msg = await client.send_message(target_chat, f"⏳ Memulai proses: ID `{drama_id}`")

        async def update_status(text: str, force: bool = False):
            nonlocal last_update
            if status_msg:
                now = time.time()
                # Throttle updates to 1.5s to avoid Telegram flood limits
                if force or (now - last_update) > 1.5:
                    try:
                        await status_msg.edit(text)
                        last_update = now
                    except Exception:
                        pass

        try:
            # ─── Step 1-2: Fetch detail ──────────────────────
            log.info(f"Fetching detail for drama: {drama_id}")
            detail = await api.get_detail(drama_id)
            drama_info = api.extract_drama_info(detail)
            title = drama_info["title"]
            
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
            
            final_path = merge_all_episodes(downloaded, title)

            # ─── Step 6: Upload ──────────────────────────────
            uploader = Uploader(client)
            
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

            # ─── Step 7: Cleanup ─────────────────────────────
            cleanup(title)
            processed_ids.add(drama_id)

            # Success message matching the screenshot - EDIT DI TEMPAT
            msg = f"✅ **Sukses Auto-Post: {title}**"
            log.info(msg)
            await update_status(msg, force=True)
                
            return True

        except Exception as e:
            msg = f"❌ Error: {title if 'title' in locals() else drama_id}\n`{e}`"
            log.error(msg, exc_info=True)
            await update_status(msg)
            return False


# =====================================================================
# CLEANUP
# =====================================================================

def cleanup(drama_title: str = None):
    """Remove all temporary files."""
    safe_title = "".join(c if c.isalnum() or c in "._- " else "_" for c in (drama_title or "")).strip()

    dirs_to_clean = [TEMP_DIR]
    if safe_title:
        dirs_to_clean.append(os.path.join(DOWNLOAD_DIR, safe_title))

    for d in dirs_to_clean:
        if os.path.exists(d):
            shutil.rmtree(d, ignore_errors=True)
            log.info(f"Cleaned: {d}")

    if safe_title:
        merged_file = os.path.join(MERGE_DIR, f"{safe_title}_final.mp4")
        if os.path.exists(merged_file):
            os.remove(merged_file)


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
                for drama in dramas:
                    if not auto_mode_active:
                        break
                    info = api.extract_drama_info(drama)
                    drama_id = str(info["id"])

                    if drama_id in processed_ids or not drama_id:
                        continue

                    log.info(f"New drama found: {info['title']} ({drama_id})")
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

    msg = await event.reply("Updating bot...")
    try:
        result = subprocess.run(
            ["git", "pull"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
        )
        output = result.stdout.strip() or result.stderr.strip() or "No output"
        await msg.edit(f"Update done:\n```\n{output}\n```")
    except Exception as e:
        await msg.edit(f"Update failed: {e}")


# =====================================================================
# ENTRY POINT
# =====================================================================

async def main():
    global auto_task
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
