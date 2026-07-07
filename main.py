import requests
import time
import logging
import sys
import os
from datetime import datetime
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
        """
        Initialize the Minecraft username checker.
        
        Args:
            webhook_url (str): Discord webhook URL
        """
        self.webhook_url = webhook_url
        self.api_url = "https://api.mojang.com/users/profiles/minecraft/"
        self.available_usernames = []
        self.checked_count = 0
        self.found_count = 0
        self.failed_count = 0
        self.total_to_check = 0
        self.start_time = None
        
    def check_username(self, username: str) -> Tuple[bool, str]:
        """
        Check if a Minecraft username is available.
        
        Args:
            username (str): Username to check
            
        Returns:
            Tuple[bool, str]: (is_available, status_message)
        """
        try:
            # Clean the username
            username = username.strip().lower()
            
            # Skip empty usernames
            if not username:
                return False, "Empty username"
            
            # Validate username length
            if len(username) < 3 or len(username) > 16:
                return False, "Invalid length (must be 3-16 chars)"
            
            # Check if username contains only valid characters
            if not username.replace('_', '').isalnum():
                return False, "Invalid characters"
            
            # Make API request to Mojang
            response = requests.get(
                f"{self.api_url}{username}",
                timeout=10
            )
            
            # If status code is 204 (No Content), username is available
            if response.status_code == 204:
                return True, "Available"
            # If status code is 200, username is taken
            elif response.status_code == 200:
                return False, "Taken"
            # If status code is 404, username doesn't exist (available)
            elif response.status_code == 404:
                return True, "Available"
            else:
                return False, f"Unexpected status {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, "Timeout"
        except requests.exceptions.RequestException as e:
            return False, f"Request error: {str(e)}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def read_usernames_from_file(self, filename: str) -> List[str]:
        """
        Read usernames from a text file.
        
        Args:
            filename (str): Path to the words.txt file
            
        Returns:
            list: List of usernames to check
        """
        try:
            # Check if file exists
            if not os.path.exists(filename):
                logger.error(f"File {filename} not found!")
                return []
            
            with open(filename, 'r', encoding='utf-8') as file:
                # Read all lines, strip whitespace, and filter out empty lines
                usernames = [line.strip() for line in file if line.strip()]
            
            # Filter valid usernames (3-16 chars, alphanumeric + underscores)
            valid_usernames = []
            for username in usernames:
                if 3 <= len(username) <= 16 and username.replace('_', '').isalnum():
                    valid_usernames.append(username)
                else:
                    logger.warning(f"Skipping invalid username: {username}")
            
            logger.info(f"Loaded {len(valid_usernames)} valid usernames from {filename}")
            return valid_usernames
            
        except FileNotFoundError:
            logger.error(f"File {filename} not found!")
            return []
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return []
    
    def send_to_discord(self, usernames: List[str]) -> bool:
        """
        Send available usernames to Discord as an embed.
        
        Args:
            usernames (list): List of available usernames
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not usernames:
            logger.info("No available usernames to send to Discord")
            return False
        
        try:
            # Split into chunks of 25 (Discord embed field limit)
            chunks = [usernames[i:i+25] for i in range(0, len(usernames), 25)]
            
            for i, chunk in enumerate(chunks):
                # Create webhook
                webhook = DiscordWebhook(url=self.webhook_url)
                
                # Create embed
                embed = DiscordEmbed(
                    title="🎮 Available Minecraft Usernames!",
                    description=f"Found **{len(usernames)}** available username(s)",
                    color="00ff00"
                )
                
                # Set timestamp
                embed.set_timestamp(datetime.utcnow().isoformat())
                
                # Set thumbnail
                embed.set_thumbnail(
                    url="https://www.minecraft.net/content/dam/games/minecraft/key-art/Minecraft_KeyArt_Header_800x320.png"
                )
                
                # Add field with usernames
                embed.add_embed_field(
                    name=f"📝 Available Usernames (Part {i+1}/{len(chunks)})",
                    value="\n".join([f"• `{name}`" for name in chunk]),
                    inline=False
                )
                
                # Add stats
                elapsed_time = time.time() - self.start_time if self.start_time else 0
                embed.add_embed_field(
                    name="📊 Statistics",
                    value=f"• Total Available: **{len(usernames)}**\n"
                          f"• Total Checked: **{self.checked_count}/{self.total_to_check}**\n"
                          f"• Failed Checks: **{self.failed_count}**\n"
                          f"• Time Elapsed: **{int(elapsed_time)}s**\n"
                          f"• Success Rate: **{((self.checked_count - self.failed_count) / self.checked_count * 100) if self.checked_count > 0 else 0:.1f}%**",
                    inline=True
                )
                
                # Add webhook to embed
                webhook.add_embed(embed)
                
                # Send webhook
                response = webhook.execute()
                
                if response.status_code == 200 or response.status_code == 204:
                    logger.info(f"Sent part {i+1}/{len(chunks)} to Discord successfully")
                    return True
                else:
                    logger.error(f"Failed to send to Discord: Status {response.status_code}")
                    return False
                
        except Exception as e:
            logger.error(f"Error sending to Discord: {e}")
            return False
    
    def check_all_usernames(self, filename: str, delay: float = 0.5) -> None:
        """
        Check all usernames from the file.
        
        Args:
            filename (str): Path to the words.txt file
            delay (float): Delay between requests (seconds)
        """
        # Read usernames from file
        usernames = self.read_usernames_from_file(filename)
        
        if not usernames:
            logger.error("No usernames to check! Exiting...")
            return
        
        self.total_to_check = len(usernames)
        self.start_time = time.time()
        
        logger.info("="*60)
        logger.info(f"Starting username check for {self.total_to_check} usernames")
        logger.info(f"Delay between requests: {delay}s")
        logger.info("="*60)
        
        # Check each username
        for index, username in enumerate(usernames, 1):
            self.checked_count += 1
            
            # Log progress every 5 checks
            if index % 5 == 0 or index == 1:
                progress_pct = (index / self.total_to_check) * 100
                logger.info(f"Progress: {index}/{self.total_to_check} ({progress_pct:.1f}%) - "
                           f"Found: {self.found_count} available")
            
            # Check username
            is_available, status = self.check_username(username)
            
            if is_available:
                self.available_usernames.append(username)
                self.found_count += 1
                logger.info(f"✅ AVAILABLE: {username} (Found {self.found_count} so far)")
            else:
                if "Taken" in status:
                    logger.debug(f"❌ TAKEN: {username}")
                else:
                    self.failed_count += 1
                    logger.warning(f"⚠️ {username}: {status}")
            
            # Rate limiting - be nice to Mojang's API
            if index < self.total_to_check:
                time.sleep(delay)
        
        # Calculate final statistics
        elapsed_time = time.time() - self.start_time
        success_rate = ((self.checked_count - self.failed_count) / self.checked_count * 100) if self.checked_count > 0 else 0
        
        # Print final summary
        logger.info("\n" + "="*60)
        logger.info("📊 CHECK COMPLETE!")
        logger.info(f"✅ Total Available: {self.found_count}")
        logger.info(f"📝 Total Checked: {self.checked_count}/{self.total_to_check}")
        logger.info(f"❌ Failed Checks: {self.failed_count}")
        logger.info(f"⏱️ Time Elapsed: {int(elapsed_time)} seconds")
        logger.info(f"📈 Success Rate: {success_rate:.1f}%")
        logger.info("="*60)
        
        # Save available usernames to file
        if self.available_usernames:
            output_file = f"available_usernames_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.available_usernames))
            logger.info(f"Saved {len(self.available_usernames)} usernames to {output_file}")
            
            # Send to Discord
            if self.webhook_url:
                logger.info("Sending available usernames to Discord...")
                success = self.send_to_discord(self.available_usernames)
                if success:
                    logger.info("Successfully sent results to Discord")
                else:
                    logger.warning("Failed to send results to Discord")
        else:
            logger.info("No available usernames found")
            # Optionally send a "no results" message
            if self.webhook_url:
                try:
                    webhook = DiscordWebhook(url=self.webhook_url)
                    embed = DiscordEmbed(
                        title="❌ No Available Usernames Found",
                        description="The check completed but no available usernames were found.",
                        color="ff0000"
                    )
                    embed.add_embed_field(
                        name="📊 Statistics",
                        value=f"• Total Checked: **{self.checked_count}**\n"
                              f"• Failed Checks: **{self.failed_count}**\n"
                              f"• Time Elapsed: **{int(elapsed_time)}s**",
                        inline=True
                    )
                    webhook.add_embed(embed)
                    webhook.execute()
                    logger.info("Sent 'no results' notification to Discord")
                except Exception as e:
                    logger.error(f"Failed to send no results notification: {e}")

def main():
    """Main function to run the checker."""
    
    # Configuration from environment variables (Railway.app)
    WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', '')
    WORDS_FILE = os.getenv('WORDS_FILE', 'words.txt')
    REQUEST_DELAY = float(os.getenv('REQUEST_DELAY', '0.5'))
    RUN_INTERVAL = int(os.getenv('RUN_INTERVAL', '0'))  # 0 = run once
    
    # Validate webhook URL
    if not WEBHOOK_URL:
        logger.warning("No Discord webhook URL provided! Results will only be logged.")
    
    # Create checker instance
    checker = MinecraftUsernameChecker(WEBHOOK_URL)
    
    # Check if this is a one-time run or scheduled
    if RUN_INTERVAL > 0:
        logger.info(f"Running in scheduled mode - checking every {RUN_INTERVAL} seconds")
        while True:
            try:
                logger.info("Starting new check cycle...")
                checker.check_all_usernames(WORDS_FILE, REQUEST_DELAY)
                logger.info(f"Check cycle complete. Waiting {RUN_INTERVAL} seconds before next check...")
                time.sleep(RUN_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Received interrupt signal. Shutting down...")
                break
            except Exception as e:
                logger.error(f"Error in check cycle: {e}")
                logger.info(f"Waiting {RUN_INTERVAL} seconds before retry...")
                time.sleep(RUN_INTERVAL)
    else:
        # One-time run
        logger.info("Running in one-time mode...")
        checker.check_all_usernames(WORDS_FILE, REQUEST_DELAY)
        logger.info("Check complete. Exiting...")

if __name__ == "__main__":
    main()