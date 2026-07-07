import requests
import time
import logging
import sys
import os
from datetime import datetime, timezone
from discord_webhook import DiscordWebhook, DiscordEmbed
from typing import List, Tuple

# Configure logging
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
        self.webhook_url = webhook_url
        self.api_url = "https://api.mojang.com/users/profiles/minecraft/"
        self.namemc_url = "https://api.namemc.com/profile/"
        self.available_usernames = []
        self.checked_count = 0
        self.found_count = 0
        self.total_to_check = 0
        self.start_time = None
        
    def send_startup_message(self):
        """Send startup message to Discord."""
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            embed = DiscordEmbed(
                title="✅ Minecraft Username Checker Started!",
                description=f"Checking **{self.total_to_check}** usernames with 1.5s delay\nChecking NameMC for locked status",
                color="00ff00"
            )
            embed.set_timestamp(datetime.now(timezone.utc))
            embed.set_footer(text="Minecraft Username Checker")
            webhook.add_embed(embed)
            webhook.execute()
            logger.info("✅ Startup message sent to Discord")
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
    
    def send_available_username(self, username: str, is_locked: bool = False):
        """Send available username to Discord immediately."""
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            
            if is_locked:
                embed = DiscordEmbed(
                    title="🔒 LOCKED USERNAME!",
                    description=f"**`{username}`** is available but LOCKED on NameMC!",
                    color="ff9900"  # Orange
                )
            else:
                embed = DiscordEmbed(
                    title="🎮 AVAILABLE USERNAME!",
                    description=f"**`{username}`** is available and NOT locked!",
                    color="00ff00"  # Green
                )
            
            embed.set_timestamp(datetime.now(timezone.utc))
            embed.add_embed_field(
                name="Progress",
                value=f"Found: **{self.found_count + 1}**\nChecked: **{self.checked_count}/{self.total_to_check}**\nProgress: **{(self.checked_count/self.total_to_check*100):.1f}%**",
                inline=True
            )
            
            if is_locked:
                embed.add_embed_field(
                    name="⚠️ Note",
                    value="This username is locked on NameMC. It may become available in the future.",
                    inline=False
                )
            
            webhook.add_embed(embed)
            webhook.execute()
            logger.info(f"✅ Sent available username: {username} (Locked: {is_locked})")
        except Exception as e:
            logger.error(f"Failed to send username: {e}")
    
    def send_completion_message(self):
        """Send completion message to Discord."""
        try:
            webhook = DiscordWebhook(url=self.webhook_url)
            elapsed = int(time.time() - self.start_time) if self.start_time else 0
            hours = elapsed // 3600
            minutes = (elapsed % 3600) // 60
            
            if self.found_count > 0:
                embed = DiscordEmbed(
                    title="✅ Check Complete!",
                    description=f"Found **{self.found_count}** available usernames!",
                    color="00ff00"
                )
            else:
                embed = DiscordEmbed(
                    title="❌ Check Complete",
                    description="No available usernames found.",
                    color="ff0000"
                )
            
            embed.set_timestamp(datetime.now(timezone.utc))
            embed.add_embed_field(
                name="📊 Final Stats",
                value=f"• Checked: **{self.checked_count}**\n• Found: **{self.found_count}**\n• Time: **{hours}h {minutes}m**",
                inline=True
            )
            webhook.add_embed(embed)
            webhook.execute()
            logger.info("✅ Completion message sent to Discord")
        except Exception as e:
            logger.error(f"Failed to send completion message: {e}")
    
    def check_namemc_locked(self, username: str) -> bool:
        """
        Check if a username is locked on NameMC.
        Returns True if locked, False if not locked or error.
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(
                f"{self.namemc_url}{username}",
                headers=headers,
                timeout=10
            )
            
            # If status is 200, the profile exists (might be locked or not)
            if response.status_code == 200:
                # Check if the profile is locked
                # NameMC returns specific HTML/JSON for locked profiles
                try:
                    data = response.json()
                    # Check for locked status in the response
                    if data.get('locked') == True:
                        return True
                    # Check for other indicators of locked profiles
                    if 'locked' in str(response.text).lower():
                        return True
                except:
                    # If we can't parse JSON, check the response text
                    response_text = response.text.lower()
                    if 'locked' in response_text or 'this profile is locked' in response_text:
                        return True
            
            # If 404, profile doesn't exist (not locked)
            elif response.status_code == 404:
                return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking NameMC for {username}: {e}")
            return False
    
    def check_username(self, username: str) -> Tuple[bool, str, bool]:
        """
        Check if a username is available.
        Returns (is_available, status_message, is_locked_on_namemc)
        """
        try:
            username = username.strip().lower()
            if not username or len(username) < 3 or len(username) > 16:
                return False, "Invalid", False
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            # Check Mojang API first
            response = requests.get(
                f"{self.api_url}{username}",
                headers=headers,
                timeout=10
            )
            
            # Available if 204 (No Content) or 404 (Not Found)
            if response.status_code in [204, 404]:
                # Check NameMC for locked status
                is_locked = self.check_namemc_locked(username)
                return True, "Available", is_locked
            # Taken if 200 (OK)
            elif response.status_code == 200:
                return False, "Taken", False
            elif response.status_code == 429:
                return False, "Rate Limited", False
            elif response.status_code == 403:
                return False, "Blocked", False
            else:
                return False, f"Status {response.status_code}", False
                
        except requests.exceptions.Timeout:
            return False, "Timeout", False
        except Exception as e:
            return False, f"Error", False
    
    def read_usernames(self, filename: str) -> List[str]:
        """Read and sort usernames from file to ensure consistent order."""
        try:
            if not os.path.exists(filename):
                logger.error(f"File {filename} not found!")
                return []
            
            with open(filename, 'r', encoding='utf-8') as file:
                usernames = [
                    line.strip().lower() 
                    for line in file 
                    if line.strip() and 3 <= len(line.strip()) <= 16
                ]
            
            # Sort usernames to ensure consistent order
            usernames.sort()
            
            # Remove duplicates
            unique_usernames = []
            seen = set()
            for username in usernames:
                if username not in seen:
                    unique_usernames.append(username)
                    seen.add(username)
            
            logger.info(f"Loaded {len(unique_usernames)} unique usernames from {filename}")
            logger.info(f"Removed {len(usernames) - len(unique_usernames)} duplicates")
            return unique_usernames
            
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return []
    
    def check_all_usernames(self, filename: str, delay: float = 1.5):
        """Check all usernames with specified delay."""
        # Read usernames
        usernames = self.read_usernames(filename)
        
        if not usernames:
            logger.error("No usernames to check!")
            return
        
        self.total_to_check = len(usernames)
        self.start_time = time.time()
        
        # Send startup message
        self.send_startup_message()
        
        logger.info("="*60)
        logger.info(f"Starting check for {self.total_to_check} usernames")
        logger.info(f"Delay: {delay}s between requests")
        logger.info("="*60)
        
        # Check each username in order
        for index, username in enumerate(usernames, 1):
            self.checked_count = index
            
            # Check username
            is_available, status, is_locked = self.check_username(username)
            
            if is_available:
                self.available_usernames.append(username)
                self.found_count += 1
                
                if is_locked:
                    logger.info(f"🔒 [{index}/{self.total_to_check}] {username} - AVAILABLE but LOCKED on NameMC (Found: {self.found_count})")
                else:
                    logger.info(f"✅ [{index}/{self.total_to_check}] {username} - AVAILABLE (Found: {self.found_count})")
                
                self.send_available_username(username, is_locked)
            else:
                logger.info(f"❌ [{index}/{self.total_to_check}] {username} - {status}")
            
            # Delay between requests (except for last one)
            if index < self.total_to_check:
                time.sleep(delay)
        
        # Send completion message
        self.send_completion_message()
        
        # Save results to file
        if self.available_usernames:
            output_file = f"available_usernames_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, 'w') as f:
                f.write('\n'.join(self.available_usernames))
            logger.info(f"Saved {len(self.available_usernames)} usernames to {output_file}")
        
        # Final summary
        elapsed = int(time.time() - self.start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        logger.info("\n" + "="*60)
        logger.info("📊 CHECK COMPLETE!")
        logger.info(f"✅ Available: {self.found_count}")
        logger.info(f"📝 Checked: {self.checked_count}")
        logger.info(f"⏱️ Time: {hours}h {minutes}m")
        logger.info("="*60)

def main():
    # YOUR WEBHOOK URL - REGENERATE THIS!
    WEBHOOK_URL = "https://discord.com/api/webhooks/1524009670262657177/UFsSKMLYBKCcex4xyoEz87yC_BgS50OdKOSc658OwlW_VoU9o63ML4oCf7ka2zfHWHoY"
    
    WORDS_FILE = "words.txt"
    DELAY = 1.5  # 1.5 second delay between requests
    
    logger.info("Starting Minecraft Username Checker...")
    checker = MinecraftUsernameChecker(WEBHOOK_URL)
    checker.check_all_usernames(WORDS_FILE, DELAY)
    logger.info("Check complete!")

if __name__ == "__main__":
    main()
