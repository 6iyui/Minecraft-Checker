#!/usr/bin/env python3
"""
Minecraft Username Checker
---------------------------
Reads usernames from words.txt, checks each one against Mojang's API for
availability, checks NameMC for "locked" status on available names, and
reports results to Discord in real time via webhook.

Designed to run unattended on Railway.app (or any always-on worker host).
"""

import atexit
import logging
import os
import re
import sys
import time
from datetime import datetime

import requests
from discord_webhook import DiscordEmbed, DiscordWebhook

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Prefer an environment variable so the real webhook URL never has to live
# in source control. Falls back to the value you gave me, but you should
# regenerate that webhook and set DISCORD_WEBHOOK_URL in Railway instead.
WEBHOOK_URL = os.environ.get(
    "DISCORD_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1524009670262657177/UFsSKMLYBKCcex4xyoEz87yC_BgS50OdKOSc658OwlW_VoU9o63ML4oCf7ka2zfHWHoY",
)

WORDLIST_FILE = os.environ.get("WORDLIST_FILE", "words.txt")
LOCK_FILE = os.environ.get("LOCK_FILE", "checker.lock")
DELAY_SECONDS = float(os.environ.get("DELAY_SECONDS", "1.5"))
REQUEST_TIMEOUT = float(os.environ.get("REQUEST_TIMEOUT", "10"))

# Minecraft usernames: 3-16 chars, letters/digits/underscore
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")

MOJANG_API = "https://api.mojang.com/users/profiles/minecraft/{username}"
NAMEMC_URL = "https://namemc.com/profile/{username}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# --------------------------------------------------------------------------
# Logging - plain text, no ANSI/rich rendering, safe for Railway's log viewer
# --------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("mc_checker")


# --------------------------------------------------------------------------
# Single-instance lock (so a Railway restart can't spin up a second worker
# checking from the top and double-posting to Discord)
# --------------------------------------------------------------------------

def acquire_lock() -> None:
    if os.path.exists(LOCK_FILE):
        log.error(
            "Lock file '%s' already exists. Another instance may be running. "
            "Exiting to avoid duplicate checks/messages.",
            LOCK_FILE,
        )
        sys.exit(1)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(release_lock)


def release_lock() -> None:
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Wordlist loading
# --------------------------------------------------------------------------

def load_usernames(path: str) -> list[str]:
    if not os.path.exists(path):
        log.error("Wordlist file '%s' not found.", path)
        sys.exit(1)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        raw = [line.strip() for line in f if line.strip()]

    valid = sorted({u for u in raw if USERNAME_RE.match(u)})

    skipped = len(raw) - len(valid)
    if skipped > 0:
        log.warning(
            "Loaded %d valid usernames (deduplicated, sorted). "
            "Skipped %d invalid/duplicate entries.",
            len(valid),
            skipped,
        )
    else:
        log.info("Loaded %d valid usernames (deduplicated, sorted).", len(valid))

    return valid


# --------------------------------------------------------------------------
# Discord helpers
# --------------------------------------------------------------------------

def send_discord_text(content: str) -> None:
    try:
        webhook = DiscordWebhook(url=WEBHOOK_URL, content=content)
        webhook.execute()
    except Exception as exc:  # noqa: BLE001 - never let a Discord hiccup kill the run
        log.warning("Failed to send Discord message: %s", exc)


def send_discord_embed(title: str, description: str, color: str) -> None:
    try:
        webhook = DiscordWebhook(url=WEBHOOK_URL)
        embed = DiscordEmbed(title=title, description=description, color=color)
        embed.set_timestamp()
        webhook.add_embed(embed)
        webhook.execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to send Discord embed: %s", exc)


COLOR_GREEN = "2ecc71"
COLOR_ORANGE = "e67e22"


# --------------------------------------------------------------------------
# Checking logic
# --------------------------------------------------------------------------

class CheckResult:
    TAKEN = "TAKEN"
    AVAILABLE = "AVAILABLE"
    BLOCKED = "BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"


def check_mojang(username: str) -> str:
    try:
        resp = requests.get(
            MOJANG_API.format(username=username),
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return CheckResult.TIMEOUT
    except requests.exceptions.RequestException as exc:
        log.warning("Request error checking %s: %s", username, exc)
        return CheckResult.ERROR

    if resp.status_code == 200:
        return CheckResult.TAKEN
    if resp.status_code in (204, 404):
        return CheckResult.AVAILABLE
    if resp.status_code == 403:
        return CheckResult.BLOCKED
    if resp.status_code == 429:
        return CheckResult.RATE_LIMITED

    log.warning("Unexpected status %s for %s", resp.status_code, username)
    return CheckResult.ERROR


def check_namemc_locked(username: str) -> bool:
    """
    Best-effort check of whether an available name is 'locked' on NameMC
    (i.e. reserved/held and not actually claimable despite Mojang saying
    it's free). NameMC doesn't offer a documented public API for this, so
    this scrapes the profile page. Treat the result as advisory - if the
    page layout changes this may need updating.
    """
    try:
        resp = requests.get(
            NAMEMC_URL.format(username=username),
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.RequestException as exc:
        log.warning("NameMC check failed for %s: %s", username, exc)
        return False

    if resp.status_code != 200:
        return False

    page = resp.text.lower()
    # NameMC shows explicit copy on the profile page when a name that looks
    # available is actually locked/held.
    return "locked" in page and "available" in page


# --------------------------------------------------------------------------
# Main run
# --------------------------------------------------------------------------

def main() -> None:
    acquire_lock()

    usernames = load_usernames(WORDLIST_FILE)
    total = len(usernames)

    stats = {
        "available": 0,
        "locked": 0,
        "taken": 0,
        "blocked": 0,
        "rate_limited": 0,
        "timeout": 0,
        "error": 0,
    }

    send_discord_text(
        f"✅ Minecraft Username Checker Started! Checking {total} usernames "
        f"with {DELAY_SECONDS}s delay"
    )
    log.info("Starting run: %d usernames, %.1fs delay between checks", total, DELAY_SECONDS)

    start_time = datetime.now()

    for idx, username in enumerate(usernames, start=1):
        result = check_mojang(username)

        if result == CheckResult.AVAILABLE:
            locked = check_namemc_locked(username)

            if locked:
                stats["locked"] += 1
                log.info(
                    "🔒 [%d/%d] %s - AVAILABLE but LOCKED (Found: %d)",
                    idx, total, username, stats["locked"],
                )
                send_discord_embed(
                    title="🔒 LOCKED USERNAME!",
                    description=(
                        f"`{username}` is available but **LOCKED** on NameMC!\n\n"
                        f"Progress: {idx}/{total}\n"
                        f"Locked found so far: {stats['locked']}"
                    ),
                    color=COLOR_ORANGE,
                )
            else:
                stats["available"] += 1
                log.info(
                    "✅ [%d/%d] %s - AVAILABLE (Found: %d)",
                    idx, total, username, stats["available"],
                )
                send_discord_embed(
                    title="🎮 AVAILABLE USERNAME!",
                    description=(
                        f"`{username}` is available!\n\n"
                        f"Progress: {idx}/{total}\n"
                        f"Available found so far: {stats['available']}"
                    ),
                    color=COLOR_GREEN,
                )

        elif result == CheckResult.TAKEN:
            stats["taken"] += 1
            log.info("❌ [%d/%d] %s - Taken", idx, total, username)

        elif result == CheckResult.BLOCKED:
            stats["blocked"] += 1
            log.info("❌ [%d/%d] %s - Blocked", idx, total, username)

        elif result == CheckResult.RATE_LIMITED:
            stats["rate_limited"] += 1
            log.info("❌ [%d/%d] %s - Rate Limited", idx, total, username)
            # Back off a bit extra on top of the normal delay when we get 429s
            time.sleep(DELAY_SECONDS * 3)

        elif result == CheckResult.TIMEOUT:
            stats["timeout"] += 1
            log.info("❌ [%d/%d] %s - Timeout", idx, total, username)

        else:
            stats["error"] += 1
            log.info("❌ [%d/%d] %s - Error", idx, total, username)

        time.sleep(DELAY_SECONDS)

    elapsed = datetime.now() - start_time
    log.info("Run complete in %s", elapsed)

    send_discord_text(
        "✅ Check Complete! "
        f"Found {stats['available']} available usernames "
        f"({stats['locked']} locked)!\n"
        f"Taken: {stats['taken']} | Blocked: {stats['blocked']} | "
        f"Rate Limited: {stats['rate_limited']} | Timeout: {stats['timeout']} | "
        f"Errors: {stats['error']}\n"
        f"Total checked: {total} | Elapsed: {elapsed}"
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Interrupted by user. Shutting down.")
    except Exception:
        log.exception("Fatal error - checker crashed.")
        send_discord_text("❌ Checker crashed with an unhandled error. Check Railway logs.")
        raise
