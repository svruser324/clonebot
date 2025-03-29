import discord
from discord import app_commands
import asyncio
import os
import colorama
from colorama import Fore, Style
import itertools
from datetime import datetime, timezone
import aiohttp
import json
from discord.ext import commands
from tqdm import tqdm
import time

colorama.init(autoreset=True)

DEFAULT_WEBHOOK_URL = "ur webhook url to log stuff"
LOGS_FILE = "logs.json"
CONFIG_FILE = "config.json"
PROGRESS_FILE = "progress.json"

user_source_guilds = {}
cloning_tasks = {}
cancel_flag = False
last_command_time = 0
current_webhook_url = DEFAULT_WEBHOOK_URL
bot_owner = "future4l"
last_command_name = "None"

def clear_terminal():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_ascii_header():
    clear_terminal()
    header_lines = [
        "       _                    _           _   ",
        "      | |                  | |         | |  ",
        "   ___| | ___  _ __   ___  | |__   ___ | |_ ",
        "  / __| |/ _ \| '_ \ / _ \ | '_ \ / _ \| __|",
        " | (__| | (_) | | | |  __/ | |_) | (_) | |_ ",
        "  \___|_|\___/|_| |_|\___| |_.__/ \___/ \__|",
        "                                            ",
        "                                            ",
        f"               CLONING bot - made by {bot_owner}"
    ]
    colors = [Fore.RED, Fore.YELLOW, Fore.GREEN, Fore.CYAN, Fore.BLUE, Fore.MAGENTA]
    color_cycle = itertools.cycle(colors)
    for line in header_lines:
        colored_line = ''.join([next(color_cycle) + ch for ch in line])
        print(colored_line)
    print(Style.RESET_ALL)

def log_action(action, status, details="", color=Fore.WHITE):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 80
    action_line = f"[{timestamp}] {action.upper():<20} [{status}]"
    details_lines = [f"    {line}" for line in details.split('\n') if line.strip()]
    
    print(separator)
    print(color + action_line)
    if details:
        print(color + '\n'.join(details_lines))
    print(separator + Style.RESET_ALL)

print_ascii_header()

def load_config():
    global current_webhook_url
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
            current_webhook_url = config.get("webhook_url", DEFAULT_WEBHOOK_URL)
            log_action("Config Loaded", "SUCCESS", f"Webhook URL: {current_webhook_url[:30]}...")
    else:
        current_webhook_url = DEFAULT_WEBHOOK_URL
        log_action("Config Load", "DEFAULT", "Using default webhook URL")

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({"webhook_url": current_webhook_url}, f, indent=4)
    log_action("Config Saved", "SUCCESS", f"Webhook URL saved")

def load_progress():
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_progress(data):
    with open(LOGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def clear_progress_file():
    if os.path.exists(LOGS_FILE):
        os.remove(LOGS_FILE)

def load_clone_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            data = json.load(f)
            log_action("Progress Loaded", "RESUMING", 
                      f"Previous progress found: {data.get('current_step', 0)}/{data.get('total_steps', 0)} steps")
            return data
    return {}

def save_clone_progress(data):
    with open(PROGRESS_FILE, "w") as f:
        json.dump(data, f, indent=4)
    log_action("Progress Saved", "UPDATED", 
              f"Step {data.get('current_step', 0)}/{data.get('total_steps', 0)}")

def clear_clone_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
    log_action("Progress Cleared", "RESET", "All progress tracking reset")

def format_time_ago(timestamp):
    if timestamp == 0:
        return "Never"
    now = time.time()
    diff = now - timestamp
    
    if diff < 60:
        return f"{int(diff)} seconds ago"
    elif diff < 3600:
        return f"{int(diff/60)} minutes ago"
    elif diff < 86400:
        return f"{int(diff/3600)} hours ago"
    else:
        return f"{int(diff/86400)} days ago"

async def send_webhook_update(title, description, color=0x00ff00, fields=None):
    global current_webhook_url
    if not current_webhook_url:
        log_action("Webhook Error", "FAILED", "No webhook URL configured!", Fore.RED)
        return
    
    async with aiohttp.ClientSession() as session:
        try:
            embed = discord.Embed(title=title, description=description, color=color)
            embed.timestamp = datetime.now(timezone.utc)
            if fields:
                for name, value in fields:
                    embed.add_field(name=name, value=value, inline=False)
            webhook = discord.Webhook.from_url(current_webhook_url, session=session)
            await webhook.send(embed=embed)
            log_action("Webhook Sent", "SUCCESS", f"Title: {title}\nDescription: {description[:50]}...")
        except Exception as e:
            log_action("Webhook Error", "FAILED", str(e), Fore.RED)

def print_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█', color=0xFFD700):
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    gold_color = "\033[38;2;255;215;0m"
    reset_color = "\033[0m"
    
    progress_line = f"{gold_color}╟{bar}╢{reset_color}"
    percentage_line = f"{gold_color}║ {percent.rjust(6)}% complete {reset_color}"
    info_line = f"{gold_color}║ {prefix.ljust(15)} {suffix.ljust(30)}{reset_color}"
    
    print(f"\r╔{'═' * (length+2)}╗")
    print(f"\r{progress_line}")
    print(f"\r{percentage_line}")
    print(f"\r{info_line}")
    print(f"\r╚{'═' * (length+2)}╝", end='\r')
    
    if iteration == total: 
        print("\n" + " " * 100)

class CloneProgress:
    def __init__(self, total_steps):
        self.start_time = time.time()
        self.current_step = 0
        self.total_steps = total_steps
        self.errors = []
        self.completed_roles = []
        self.completed_channels = []
        self.completed_categories = []
        log_action("Progress Init", "STARTED", f"Total steps: {total_steps}")

    def get_elapsed(self):
        return time.time() - self.start_time

    def get_progress_percent(self):
        return (self.current_step / self.total_steps) * 100 if self.total_steps else 0

    def to_dict(self):
        return {
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "errors": self.errors,
            "elapsed_time": self.get_elapsed(),
            "completed_roles": self.completed_roles,
            "completed_channels": self.completed_channels,
            "completed_categories": self.completed_categories
        }

    def save(self):
        save_clone_progress(self.to_dict())

    def load(self, data):
        if isinstance(data, dict):
            self.current_step = data.get("current_step", 0)
            self.errors = data.get("errors", [])
            self.completed_roles = data.get("completed_roles", [])
            self.completed_channels = data.get("completed_channels", [])
            self.completed_categories = data.get("completed_categories", [])
            log_action("Progress Load", "RESUMED", f"Loaded {self.current_step}/{self.total_steps} steps")

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.emojis_and_stickers = True

class CloneBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        await self.tree.sync()
        log_action("Bot Setup", "READY", "Commands synced and bot is ready")
    
    async def on_message(self, message):
        if message.author.bot:
            return
        await self.process_commands(message)

bot = CloneBot()

@bot.tree.command(name="help", description="Show all available commands")
async def help_command(interaction: discord.Interaction):
    global last_command_time, last_command_name
    
    embed = discord.Embed(title=" CloneBot Help", color=0x7289da)
    embed.description = "Advanced server cloning bot with message cloning ability."
    embed.add_field(name="/source <id>", value="Set source server ID (DM compatible)", inline=False)
    embed.add_field(name="/clone [ignore_channels]", value="Start cloning with optional channel exclusions", inline=False)
    embed.add_field(name="/cancel", value="Stop current cloning operation", inline=False)
    embed.add_field(name="/purge", value="Wipe all channels and roles", inline=False)
    embed.add_field(name="/info", value="Show current confign", inline=False)
    embed.add_field(name="/webhook <url>", value="Change logging webhook URL", inline=False)
    embed.add_field(name="/sync", value="Sync slash commands (owner only)", inline=False)
    embed.add_field(name="/clearjson", value="Clear the progress tracking file", inline=False)
    embed.set_footer(text=f"Bot Owner: @{bot_owner}")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="sync", description="Sync slash commands (owner only)")
async def sync(interaction: discord.Interaction):
    if interaction.user.id != bot.owner_id:
        await interaction.response.send_message("You must be the bot owner to use this command.", ephemeral=True)
        return
    
    try:
        await bot.tree.sync()
        await interaction.response.send_message("Successfully synced slash commands!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Failed to sync commands: {e}", ephemeral=True)

@bot.tree.command(name="clearjson", description="Clear the progress tracking file")
async def clearjson(interaction: discord.Interaction):
    global last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/clearjson"
    
    try:
        clear_clone_progress()
        embed = discord.Embed(
            title="✅ Progress File Cleared",
            description="The progress tracking file has been reset",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
    except Exception as e:
        embed = discord.Embed(
            title="❌ Error Clearing File",
            description=str(e),
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="info", description="Show current bot configuration")
async def info_command(interaction: discord.Interaction):
    global last_command_time, user_source_guilds, current_webhook_url, last_command_name
    
    embed = discord.Embed(title="ℹ️ Bot Information", color=0x7289da)
    embed.add_field(name="Owner", value=f"@{bot_owner}", inline=True)
    embed.add_field(name="Webhook URL", value=f"`{current_webhook_url[:30]}...`" if current_webhook_url else "Not set", inline=True)
    
    if interaction.user.id in user_source_guilds:
        source_guild_id = user_source_guilds[interaction.user.id]
        source_guild = bot.get_guild(source_guild_id)
        if source_guild:
            embed.add_field(name="Source Server", value=f"{source_guild.name}\n(ID: {source_guild.id})", inline=False)
            set_by = await bot.fetch_user(interaction.user.id)
            embed.add_field(name="Set By", value=f"{set_by.name}#{set_by.discriminator}", inline=True)
    
    embed.add_field(name="Last Command", value=f"{last_command_name} ({format_time_ago(last_command_time)})", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="webhook", description="Change the logging webhook URL")
@app_commands.describe(url="The new webhook URL")
async def webhook_command(interaction: discord.Interaction, url: str):
    global current_webhook_url, last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/webhook"
    
    if not url.startswith("https://discord.com/api/webhooks/"):
        embed = discord.Embed(
            title="❌ Invalid Webhook",
            description="URL must start with `https://discord.com/api/webhooks/`",
            color=0xff0000
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    current_webhook_url = url
    save_config()
    
    embed = discord.Embed(
        title="✅ Webhook Updated",
        description=f"New webhook URL set:\n`{url[:50]}...`",
        color=0x00ff00
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    await send_webhook_update("Webhook Test", 
                            "This is a test message to confirm the new webhook is working",
                            fields=[("Changed By", interaction.user.mention)])

@bot.tree.command(name="source", description="Set the source server ID for cloning")
@app_commands.describe(guild_id="The source server guild ID to clone from")
async def source(interaction: discord.Interaction, guild_id: str):
    global last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/source"
    
    try:
        user_source_guilds[interaction.user.id] = int(guild_id)
        embed = discord.Embed(
            title="✅ Source Set",
            description=f"Source server configured: `{guild_id}`",
            color=0x00ff00
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await send_webhook_update("Source Configured", 
                                f"User {interaction.user} set source to {guild_id}",
                                fields=[("Operator", interaction.user.mention)])
    except ValueError:
        embed = discord.Embed(
            title="❌ Invalid ID",
            description="Guild ID must be a numeric value",
            color=0xff0000
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="clone", description="Clone the source server to this server")
@app_commands.describe(ignore_channels="Comma-separated channel IDs to exclude messages from")
async def clone(interaction: discord.Interaction, ignore_channels: str = None):
    global cancel_flag, last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/clone"
    cancel_flag = False
    
    if not interaction.guild:
        embed = discord.Embed(
            title="🚫 Server Only",
            description="This command must be used in a server",
            color=0xff0000
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    source_guild_id = user_source_guilds.get(interaction.user.id)
    if not source_guild_id:
        embed = discord.Embed(
            title="❌ No Source",
            description="Use `/source` first to set origin server",
            color=0xff0000
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    ignored_channel_ids = []
    if ignore_channels:
        try:
            ignored_channel_ids = [int(cid.strip()) for cid in ignore_channels.split(',')]
        except ValueError:
            embed = discord.Embed(
                title="❌ Invalid Channels",
                description="Channel IDs must be numeric values",
                color=0xff0000
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

    source_guild = bot.get_guild(source_guild_id)
    target_guild = interaction.guild

    if not source_guild:
        embed = discord.Embed(
            title="Source Missing",
            description="Bot not in source server or server deleted",
            color=0xff0000
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    if interaction.channel.id in cloning_tasks:
        embed = discord.Embed(
            title="⏳ Operation Ongoing",
            description="Clone already running in this channel",
            color=0xffd700
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    try:
        embed = discord.Embed(
            title=" Clone Started",
            description=f"Cloning from **{source_guild.name}** to **{target_guild.name}**",
            color=0x00ff00
        )
        embed.add_field(name="Ignored Channels", value=str(ignored_channel_ids) if ignored_channel_ids else "None")
        await interaction.response.send_message(embed=embed)
        initial_msg = await interaction.original_response()

        total_steps = len(source_guild.roles) + len(source_guild.channels)
        for tc in source_guild.text_channels:
            if tc.id not in ignored_channel_ids:
                total_steps += 500

        progress = CloneProgress(total_steps)
        existing_progress = load_clone_progress()
        if existing_progress:
            progress.load(existing_progress)
            print(f"{Fore.YELLOW}Resuming from previous progress at {progress.get_progress_percent():.1f}%{Style.RESET_ALL}")
            
        cloning_tasks[interaction.channel.id] = progress

        await send_webhook_update("Clone Started", 
            f"**Source**: {source_guild.name} ({source_guild.id})\n"
            f"**Target**: {target_guild.name} ({target_guild.id})",
            fields=[
                ("Initiator", interaction.user.mention),
                ("Ignored Channels", ', '.join(map(str, ignored_channel_ids)) if ignored_channel_ids else "None"),
                ("Status", "Resuming from previous progress" if existing_progress else "Starting fresh clone")
            ])

        await clone_server(source_guild, target_guild, progress, interaction.channel, ignored_channel_ids)

        del cloning_tasks[interaction.channel.id]
        clear_clone_progress()
        
        embed = discord.Embed(
            title="✅ Clone Complete",
            description=f"Successfully cloned {source_guild.name}",
            color=0x00ff00
        )
        embed.add_field(name="Duration", value=f"{progress.get_elapsed():.2f} seconds")
        await initial_msg.edit(embed=embed)
        
        await send_webhook_update("Clone Completed", 
            f"Successfully cloned {source_guild.name} to {target_guild.name}",
            color=0x00ff00,
            fields=[("Duration", f"{progress.get_elapsed():.2f} seconds")])

    except Exception as e:
        embed = discord.Embed(
            title="❌ Clone Failed",
            description=str(e),
            color=0xff0000
        )
        await interaction.followup.send(embed=embed)
        await send_webhook_update("Clone Failed", f"Error: {str(e)}", 0xff0000)
        if interaction.channel.id in cloning_tasks:
            del cloning_tasks[interaction.channel.id]

@bot.tree.command(name="cancel", description="Cancel the current cloning operation")
async def cancel(interaction: discord.Interaction):
    global cancel_flag, last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/cancel"
    cancel_flag = True
    embed = discord.Embed(
        title="⏹️ Cancellation Sent",
        description="Stopping current clone operation...",
        color=0xffd700
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="purge", description="Delete all roles and channels in this server")
async def purge(interaction: discord.Interaction):
    global last_command_time, last_command_name
    last_command_time = time.time()
    last_command_name = "/purge"
    
    if not interaction.guild:
        embed = discord.Embed(
            title="🚫 Server Only",
            description="This command requires server context",
            color=0xff0000
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    embed = discord.Embed(
        title="🔥 Purge Initiated",
        description="This will delete ALL channels and roles!\nConfirm with ✅ within 30 seconds",
        color=0xff0000
    )
    msg = await interaction.response.send_message(embed=embed)
    confirm_msg = await interaction.original_response()
    
    def check(reaction, user):
        return user == interaction.user and str(reaction.emoji) == '✅'

    try:
        await confirm_msg.add_reaction('✅')
        reaction, user = await bot.wait_for('reaction_add', timeout=30.0, check=check)
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="🕒 Purge Canceled",
            description="Confirmation timeout",
            color=0xffd700
        )
        return await confirm_msg.edit(embed=embed)

    try:
        total_items = len(interaction.guild.channels) + len([r for r in interaction.guild.roles if r.name != "@everyone" and not r.managed])
        deleted_items = 0
        
        for channel in interaction.guild.channels:
            try:
                await channel.delete()
                deleted_items += 1
                print_progress_bar(deleted_items, total_items, prefix='Purging:', suffix='Complete', length=50)
                await asyncio.sleep(1)
            except Exception as e:
                print(f"{Fore.RED}Error deleting channel: {e}")

        for role in interaction.guild.roles:
            if role.name != "@everyone" and not role.managed:
                try:
                    await role.delete()
                    deleted_items += 1
                    print_progress_bar(deleted_items, total_items, prefix='Purging:', suffix='Complete', length=50)
                    await asyncio.sleep(1)
                except Exception as e:
                    print(f"{Fore.RED}Error deleting role: {e}")

        print()
        embed = discord.Embed(
            title="✅ Purge Complete",
            description="All channels and roles removed",
            color=0x00ff00
        )
        await confirm_msg.edit(embed=embed)
        await send_webhook_update("Server Purged", 
                                f"All content removed from {interaction.guild.name}",
                                color=0x00ff00)

    except Exception as e:
        embed = discord.Embed(
            title="❌ Purge Failed",
            description=str(e),
            color=0xff0000
        )
        await confirm_msg.edit(embed=embed)
        await send_webhook_update("Purge Failed", str(e), 0xff0000)

async def clone_server(source_guild, target_guild, progress, log_channel, ignored_channel_ids):
    global cancel_flag
    role_mapping = {}
    existing_progress = load_clone_progress()
    
    log_action("Clone Start", "INITIALIZED", 
              f"Source: {source_guild.name} ({source_guild.id})\n"
              f"Target: {target_guild.name} ({target_guild.id})\n"
              f"Ignored Channels: {ignored_channel_ids or 'None'}")

    total_roles = len(source_guild.roles)
    for i, role in enumerate(reversed(source_guild.roles)):
        if cancel_flag:
            log_action("Clone Operation", "CANCELLED", "User requested cancellation", Fore.YELLOW)
            raise Exception("Operation cancelled by user")
        if role.is_default():
            continue
        
        if role.id in progress.completed_roles:
            existing_role = discord.utils.get(target_guild.roles, name=role.name)
            if existing_role:
                role_mapping[role.id] = existing_role.id
                log_action("Role Skip", "EXISTS", f"Skipped existing role: {role.name}", Fore.CYAN)
            continue
        
        existing_role = discord.utils.get(target_guild.roles, name=role.name)
        if existing_role:
            role_mapping[role.id] = existing_role.id
            progress.completed_roles.append(role.id)
            log_action("Role Match", "EXISTS", f"Matched existing role: {role.name}", Fore.CYAN)
            continue

        try:
            new_role = await target_guild.create_role(
                name=role.name,
                permissions=role.permissions,
                color=role.color,
                hoist=role.hoist,
                mentionable=role.mentionable
            )
            role_mapping[role.id] = new_role.id
            progress.completed_roles.append(role.id)
            progress.current_step += 1
            progress.save()
            save_clone_progress(progress.to_dict())
            
            log_action("Role Created", "SUCCESS", f"Created role: {role.name}", Fore.GREEN)
            print_progress_bar(i+1, total_roles, prefix='Cloning Roles:', suffix=f'{role.name}')
        except Exception as e:
            error_msg = f"Role {role.name}: {str(e)}"
            progress.errors.append(error_msg)
            progress.save()
            save_clone_progress(progress.to_dict())
            log_action("Role Error", "FAILED", error_msg, Fore.RED)

    category_mapping = {}
    total_categories = len(source_guild.categories)
    for i, category in enumerate(source_guild.categories):
        if cancel_flag:
            raise Exception("Operation cancelled by user")
        
        if category.id in progress.completed_categories:
            category_mapping[category.id] = discord.utils.get(target_guild.categories, name=category.name)
            continue
            
        overwrites = {}
        for target, permission in category.overwrites.items():
            if isinstance(target, discord.Role):
                if target.id in role_mapping:
                    overwrites[target_guild.get_role(role_mapping[target.id])] = permission

        try:
            new_category = await target_guild.create_category(
                name=category.name,
                overwrites=overwrites,
                position=category.position
            )
            category_mapping[category.id] = new_category
            progress.completed_categories.append(category.id)
            progress.current_step += 1
            progress.save()
            save_clone_progress(progress.to_dict())
            
            print_progress_bar(i+1, total_categories, prefix='Cloning Categories:', suffix=f'{category.name}', length=50)
        except Exception as e:
            progress.errors.append(f"Category {category.name}: {str(e)}")
            progress.save()
            save_clone_progress(progress.to_dict())

    total_channels = len(source_guild.channels)
    for i, channel in enumerate(source_guild.channels):
        if cancel_flag:
            raise Exception("Operation cancelled by user")
        
        if channel.id in progress.completed_channels:
            continue
            
        if isinstance(channel, discord.TextChannel):
            try:
                clone_messages = channel.id not in ignored_channel_ids

                new_channel = await target_guild.create_text_channel(
                    name=channel.name,
                    category=category_mapping.get(channel.category_id),
                    position=channel.position,
                    topic=channel.topic,
                    slowmode_delay=channel.slowmode_delay,
                    overwrites=await clone_overwrites(channel.overwrites, role_mapping, target_guild)
                )
                progress.completed_channels.append(channel.id)
                progress.current_step += 1
                progress.save()
                save_clone_progress(progress.to_dict())
                
                print_progress_bar(i+1, total_channels, prefix='Cloning Channels:', suffix=f'{channel.name}', length=50)

                if clone_messages:
                    await clone_channel_messages(channel, new_channel, progress)

            except Exception as e:
                progress.errors.append(f"Text Channel {channel.name}: {str(e)}")
                progress.save()
                save_clone_progress(progress.to_dict())

        elif isinstance(channel, discord.VoiceChannel):
            try:
                await target_guild.create_voice_channel(
                    name=channel.name,
                    category=category_mapping.get(channel.category_id),
                    position=channel.position,
                    bitrate=channel.bitrate,
                    user_limit=channel.user_limit
                )
                progress.completed_channels.append(channel.id)
                progress.current_step += 1
                progress.save()
                save_clone_progress(progress.to_dict())
                
                print_progress_bar(i+1, total_channels, prefix='Cloning Channels:', suffix=f'{channel.name}', length=50)
            except Exception as e:
                progress.errors.append(f"Voice Channel {channel.name}: {str(e)}")
                progress.save()
                save_clone_progress(progress.to_dict())

    total_members = len(source_guild.members)
    for i, member in enumerate(source_guild.members):
        if cancel_flag:
            raise Exception("Operation cancelled by user")
            
        try:
            target_member = target_guild.get_member(member.id)
            if target_member:
                roles = [target_guild.get_role(role_mapping[role.id]) for role in member.roles 
                        if role.id in role_mapping and not role.is_default()]
                await target_member.edit(roles=roles)
                progress.current_step += 1
                progress.save()
                save_clone_progress(progress.to_dict())
                
                if i % 10 == 0:
                    print_progress_bar(i+1, total_members, prefix='Updating Members:', suffix=f'{member.name}', length=50)
        except Exception as e:
            progress.errors.append(f"Member {member.name}: {str(e)}")
            progress.save()
            save_clone_progress(progress.to_dict())

async def clone_overwrites(overwrites, role_mapping, target_guild):
    new_overwrites = {}
    for target, overwrite in overwrites.items():
        if isinstance(target, discord.Role):
            if target.id in role_mapping:
                new_role = target_guild.get_role(role_mapping[target.id])
                if new_role:
                    new_overwrites[new_role] = overwrite
        elif isinstance(target, discord.Member):
            new_member = target_guild.get_member(target.id)
            if new_member:
                new_overwrites[new_member] = overwrite
    return new_overwrites

async def clone_channel_messages(source_channel, target_channel, progress):
    try:
        message_count = 0
        async for message in source_channel.history(limit=500, oldest_first=True):
            if progress.current_step % 10 == 0 and cancel_flag:
                raise Exception("Operation cancelled by user")
            
            files = []
            for attachment in message.attachments:
                files.append(await attachment.to_file())
            
            reference = None
            if message.reference and message.reference.message_id:
                try:
                    referenced_msg = await source_channel.fetch_message(message.reference.message_id)
                    if referenced_msg:
                        reference = discord.MessageReference(
                            message_id=referenced_msg.id,
                            channel_id=target_channel.id,
                            fail_if_not_exists=False
                        )
                except Exception as e:
                    log_action("Reference Error", "WARNING", f"Could not clone reference: {str(e)}", Fore.YELLOW)

            await target_channel.send(
                content=message.content,
                files=files,
                embeds=message.embeds,
                reference=reference
            )
            message_count += 1
            progress.current_step += 1
            progress.save()
            save_clone_progress(progress.to_dict())
            
            if message_count % 10 == 0:
                print_progress_bar(message_count, 500, prefix=f'Cloning Messages in {source_channel.name}:', suffix='Complete', length=50)
            
            await asyncio.sleep(1)
    except Exception as e:
        progress.errors.append(f"Messages in {source_channel.name}: {str(e)}")
        progress.save()
        save_clone_progress(progress.to_dict())

load_config()

bot.run("ur bot token")
