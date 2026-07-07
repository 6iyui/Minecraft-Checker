import requests
import time
import logging
import sys
import os
import random
from datetime import datetime, timezone
from discord_webhook import DiscordWebhook, DiscordEmbed
from typing import List, Tuple, Optional

# Configure logging - REDUCED LOGGING
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('checker.log')
    ]
)
logger = logging.getLogger(__name__)

class MinecraftUsernameChecker:
    def __init__(self, webhook_url: str):
        """
        Initialize the Minecraft username checker.
        """
        self.webhook_url = webhook_url
        self.api_url = "https://api.mojang.com/users/profiles/minecraft/"
        self.available_usernames = []
        self.checked_count = 0
        self.found_count = 0
        self.failed_count = 0
        self.total_to_check = 0
        self.start_time = None
        self.consecutive_failures = 0
        self.base_delay = 0.5
        self.current_delay = 0.5
        self.rate_limited = False
        self.rate_limit_reset = 0
        
    def send_startup_message(self) -> bool:
        """
        Send a startup message to Discord confirming the bot is live.
        """
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="✅ Minecraft Username Checker is LIVE!",
                description="The checker has started successfully and is now running.",
                color="00ff00"  # Green
            )
            
            # FIXED: Use datetime.now(timezone.utc)
            embed.set_timestamp(datetime.now(timezone.utc).isoformat())
            
            # Add info fields
            embed.add_embed_field(
                name="📊 Status",
                value="• **Online**: ✅\n• **Checking**: In progress\n• **Started**: Just now",
                inline=True
            )
            
            embed.add_embed_field(
                name="⚙️ Configuration",
                value=f"• **File**: `words.txt`\n• **Delay**: 2.0 seconds\n• **Mode**: Real-time alerts",
                inline=True
            )
            
            embed.set_footer(
                text="Minecraft Username Checker",
                icon_url="https://www.minecraft.net/content/dam/games/minecraft/key-art/Minecraft_KeyArt_Header_800x320.png"
            )
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code in [200, 204]:
                logger.info("✅ Startup notification sent to Discord!")
                return True
            else:
                logger.error(f"Failed to send startup notification: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending startup notification: {e}")
            return False
    
    def send_available_username(self, username: str) -> bool:
        """
        Send a single available username to Discord immediately.
        """
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            embed = DiscordEmbed(
                title="🎮 AVAILABLE USERNAME FOUND!",
                description=f"**`{username}`** is available!",
                color="00ff00"  # Green
            )
            
            # FIXED: Use datetime.now(timezone.utc)
            embed.set_timestamp(datetime.now(timezone.utc).isoformat())
            
            # Add stats
            elapsed_time = time.time() - self.start_time if self.start_time else 0
            embed.add_embed_field(
                name="📊 Current Stats",
                value=f"• Total Found: **{self.found_count + 1}**\n"
                      f"• Checked: **{self.checked_count}/{self.total_to_check}**\n"
                      f"• Time Elapsed: **{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s**\n"
                      f"• Progress: **{(self.checked_count / self.total_to_check * 100):.1f}%**",
                inline=True
            )
            
            embed.set_footer(
                text="Minecraft Username Checker - Real-time Alert",
                icon_url="https://www.minecraft.net/content/dam/games/minecraft/key-art/Minecraft_KeyArt_Header_800x320.png"
            )
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code in [200, 204]:
                logger.info(f"✅ Sent available username to Discord: {username}")
                return True
            else:
                logger.error(f"Failed to send username to Discord: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending username to Discord: {e}")
            return False
    
    def send_completion_message(self) -> bool:
        """
        Send completion message to Discord with final stats.
        """
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            elapsed_time = time.time() - self.start_time if self.start_time else 0
            
            if self.found_count > 0:
                embed = DiscordEmbed(
                    title="✅ Check Complete!",
                    description=f"Found **{self.found_count}** available username(s)!",
                    color="00ff00"
                )
            else:
                embed = DiscordEmbed(
                    title="❌ Check Complete - No Usernames Found",
                    description="The check completed but no available usernames were found.",
                    color="ff0000"
                )
            
            # FIXED: Use datetime.now(timezone.utc)
            embed.set_timestamp(datetime.now(timezone.utc).isoformat())
            
            embed.add_embed_field(
                name="📊 Final Statistics",
                value=f"• Total Available: **{self.found_count}**\n"
                      f"• Total Checked: **{self.checked_count}/{self.total_to_check}**\n"
                      f"• Failed Checks: **{self.failed_count}**\n"
                      f"• Time Elapsed: **{int(elapsed_time // 60)}m {int(elapsed_time % 60)}s**\n"
                      f"• Success Rate: **{((self.checked_count - self.failed_count) / self.checked_count * 100) if self.checked_count > 0 else 0:.1f}%**",
                inline=True
            )
            
            embed.set_footer(
                text="Minecraft Username Checker - Completed",
                icon_url="https://www.minecraft.net/content/dam/games/minecraft/key-art/Minecraft_KeyArt_Header_800x320.png"
            )
            
            webhook.add_embed(embed)
            response = webhook.execute()
            
            if response.status_code in [200, 204]:
                logger.info("✅ Completion notification sent to Discord!")
                return True
            else:
                logger.error(f"Failed to send completion notification: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending completion notification: {e}")
            return False
    
    def check_username(self, username: str) -> Tuple[bool, str]:
        """
        Check if a Minecraft username is available with retry logic.
        """
        try:
            # Clean the username
            username = username.strip().lower()
            
            # Skip empty or invalid usernames
            if not username or len(username) < 3 or len(username) > 16:
                return False, "Invalid username"
            
            # Check for rate limiting
            if self.rate_limited and time.time() < self.rate_limit_reset:
                wait_time = self.rate_limit_reset - time.time() + 1
                logger.info(f"Rate limited, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                self.rate_limited = False
            
            # Make API request with headers to appear more like a browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(
                f"{self.api_url}{username}",
                headers=headers,
                timeout=10
            )
            
            # Handle rate limiting (429)
            if response.status_code == 429:
                self.rate_limited = True
                reset_time = response.headers.get('X-RateLimit-Reset')
                if reset_time:
                    try:
                        self.rate_limit_reset = float(reset_time)
                    except:
                        self.rate_limit_reset = time.time() + 60
                else:
                    self.rate_limit_reset = time.time() + 30
                return False, "Rate limited"
            
            # Handle forbidden (403)
            if response.status_code == 403:
                self.consecutive_failures += 1
                if self.consecutive_failures > 5:
                    logger.warning("Multiple 403 errors, increasing delay...")
                    self.current_delay = min(self.current_delay * 2, 5.0)
                return False, "Blocked (403)"
            
            self.consecutive_failures = 0
            
            if response.status_code == 204:
                return True, "Available"
            elif response.status_code == 200:
                return False, "Taken"
            elif response.status_code == 404:
                return True, "Available"
            else:
                return False, f"Status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.RequestException:
            self.consecutive_failures += 1
            if self.consecutive_failures > 3:
                self.current_delay = min(self.current_delay * 1.5, 5.0)
            return False, "Request error"
        except Exception:
            return False, "Error"
    
    def read_usernames_from_file(self, filename: str) -> List[str]:
        """
        Read usernames from a text file.
        """
        try:
            if not os.path.exists(filename):
                logger.error(f"File {filename} not found!")
                return []
            
            usernames = []
            with open(filename, 'r', encoding='utf-8') as file:
                for line in file:
                    username = line.strip().lower()
                    if username and 3 <= len(username) <= 16 and username.replace('_', '').isalnum():
                        usernames.append(username)
            
            logger.info(f"Loaded {len(usernames)} valid usernames from {filename}")
            return usernames
            
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return []
    
    def check_all_usernames(self, filename: str, delay: float = 0.5) -> None:
        """
        Check all usernames with adaptive rate limiting.
        """
        # Read usernames first
        usernames = self.read_usernames_from_file(filename)
        
        if not usernames:
            logger.error("No usernames to check!")
            # Send error notification to Discord
            try:
                webhook = DiscordWebhook(url=self.webhook_url)
                embed = DiscordEmbed(
                    title="❌ Error!",
                    description="No usernames found in words.txt file!",
                    color="ff0000"
                )
                # FIXED: Use datetime.now(timezone.utc)
                embed.set_timestamp(datetime.now(timezone.utc).isoformat())
                webhook.add_embed(embed)
                webhook.execute()
            except:
                pass
            return
        
        # Send startup message after loading usernames
        logger.info("Sending startup notification to Discord...")
        self.send_startup_message()
        
        self.total_to_check = len(usernames)
        self.start_time = time.time()
        self.current_delay = delay
        
        logger.info("="*60)
        logger.info(f"Starting check for {self.total_to_check} usernames")
        logger.info(f"Initial delay: {delay}s")
        logger.info("="*60)
        
        # Send initial progress update
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            embed = DiscordEmbed(
                title="🔍 Starting Check",
                description=f"Will check **{self.total_to_check}** usernames",
                color="00ff00"
            )
            # FIXED: Use datetime.now(timezone.utc)
            embed.set_timestamp(datetime.now(timezone.utc).isoformat())
            embed.add_embed_field(
                name="📊 Info",
                value=f"• Mode: Real-time alerts\n• Delay: {delay}s between requests",
                inline=True
            )
            webhook.add_embed(embed)
            webhook.execute()
        except Exception as e:
            logger.error(f"Error sending initial update: {e}")
        
        batch_size = 1000
        for batch_start in range(0, len(usernames), batch_size):
            batch_end = min(batch_start + batch_size, len(usernames))
            batch = usernames[batch_start:batch_end]
            
            logger.info(f"Processing batch {batch_start//batch_size + 1}/{(len(usernames)+batch_size-1)//batch_size}")
            
            for index, username in enumerate(batch, batch_start + 1):
                self.checked_count += 1
                
                if index % 100 == 0 or index == 1:
                    progress_pct = (index / self.total_to_check) * 100
                    elapsed = time.time() - self.start_time
                    rate = index / elapsed if elapsed > 0 else 0
                    logger.info(f"Progress: {index}/{self.total_to_check} ({progress_pct:.1f}%) - "
                               f"Found: {self.found_count} - Rate: {rate:.1f}/s")
                
                is_available, status = self.check_username(username)
                
                if is_available:
                    self.available_usernames.append(username)
                    self.found_count += 1
                    logger.info(f"✅ AVAILABLE: {username}")
                    # Send to Discord immediately
                    self.send_available_username(username)
                elif status not in ["Taken", "Invalid username"]:
                    self.failed_count += 1
                    if self.failed_count % 10 == 0:
                        logger.warning(f"Error count: {self.failed_count}, current delay: {self.current_delay:.2f}s")
                
                if self.current_delay > delay:
                    self.current_delay = max(delay, self.current_delay * 0.99)
                
                jitter = random.uniform(0, 0.1)
                time.sleep(self.current_delay + jitter)
            
            # Save progress after each batch
            if self.available_usernames:
                with open('available_usernames_progress.txt', 'w') as f:
                    f.write('\n'.join(self.available_usernames))
        
        # Send completion message
        self.send_completion_message()
        
        # Save final results
        if self.available_usernames:
            output_file = f"available_usernames_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, 'w') as f:
                f.write('\n'.join(self.available_usernames))
            logger.info(f"Saved {len(self.available_usernames)} usernames to {output_file}")
        
        elapsed_time = time.time() - self.start_time
        logger.info("\n" + "="*60)
        logger.info("📊 CHECK COMPLETE!")
        logger.info(f"✅ Available: {self.found_count}")
        logger.info(f"📝 Checked: {self.checked_count}/{self.total_to_check}")
        logger.info(f"❌ Failed: {self.failed_count}")
        logger.info(f"⏱️ Time: {int(elapsed_time // 60)}m {int(elapsed_time % 60)}s")
        logger.info("="*60)

def main():
    """Main function with webhook URL directly in code."""
    
    # ============================================================
    # YOUR DISCORD WEBHOOK URL - PUT YOUR REGENERATED URL HERE
    # ============================================================
    WEBHOOK_URL = "https://discord.com/api/webhooks/1524009670262657177/UFsSKMLYBKCcex4xyoEz87yC_BgS50OdKOSc658OwlW_VoU9o63ML4oCf7ka2zfHWHoY"
    
    # Configuration
    WORDS_FILE = "words.txt"  # Use your full words.txt file
    REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', '2.0'))  # 2 second delay between requests
    
    # Create checker instance
    checker = MinecraftUsernameChecker(WEBHOOK_URL)
    
    # Run once
    logger.info("Starting username checker...")
    checker.check_all_usernames(WORDS_FILE, REQUEST_DELAY)
    logger.info("Check complete. Exiting...")

if __name__ == "__main__":
    main()
