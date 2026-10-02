import os, time, random, asyncio, json, re
import aiohttp
from collections import defaultdict, deque
from datetime import timedelta, datetime, timezone
import discord
from discord.ext import commands

PREFIX = ","
COLOR = 0x000001
TOKEN = os.getenv("DISCORD_TOKEN")

# Moderation role permissions
# 1555623587879063613 -> warn, mute, ban, kick, purge, lock
# 1555566558766436452 -> warn, mute
# 1555566599417626776 -> warn, mute
# 1555566624185258105 -> warn, mute, kick
# 1555566658100273237 -> warn, mute, kick
BAN_ROLE = 1555623587879063613
MUTE_ROLES = {
    1555623587879063613,
    1555566558766436452,
    1555566599417626776,
    1555566624185258105,
    1555566658100273237,
}
WARN_ROLES = set(MUTE_ROLES)
KICK_ROLES = {
    1555623587879063613,
    1555566624185258105,
    1555566658100273237,
}
PURGE_ROLES = {1555623587879063613}
LOCK_ROLES = {1555623587879063613}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.presences = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
start_time = time.time()
warning_data = defaultdict(lambda: defaultdict(list))
afk_data = {}
welcome_channels = {}
welcome_config = defaultdict(lambda: {
    "enabled": False,
    "channel": None,
    "title": "Welcome to {server}!",
    "description": "welcome {user} to **{server}**!\n\nmember **#{membercount}**",
    "color": "#000001",
    "image": None,
    "thumbnail": "{user_avatar}",
})
WELCOME_CONFIG_FILE = "welcome_config.json"
VANITY_CONFIG_FILE = "vanity_config.json"
vanity_config = defaultdict(lambda: {
    "enabled": False,
    "role": None,
    "title": "Vanity Unlocked!",
    "description": "{user} has `/bleeed` in their status and received {role}!",
    "color": "#000001",
    "image": None,
    "thumbnail": "{user_avatar}",
})
AUTOROLE_CONFIG_FILE = "autorole_config.json"
AUTOREACT_CONFIG_FILE = "autoreact_config.json"

def _save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        print(f"config save failed for {path}: {exc}")

def load_autorole_config():
    try:
        with open(AUTOROLE_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, rid in raw.items():
            autoroles[int(gid)] = int(rid) if rid else None
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        pass

def save_autorole_config():
    _save_json_file(AUTOROLE_CONFIG_FILE, {str(k): v for k, v in autoroles.items()})

def load_autoreact_config():
    try:
        with open(AUTOREACT_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, rules in raw.items():
            autoreacts[int(gid)] = {
                str(trigger): list(emojis) for trigger, emojis in (rules or {}).items()
            }
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        pass

def save_autoreact_config():
    _save_json_file(AUTOREACT_CONFIG_FILE, {
        str(gid): {str(trigger): list(emojis) for trigger, emojis in rules.items()}
        for gid, rules in autoreacts.items()
    })

def load_vanity_config():
    try:
        with open(VANITY_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, cfg in raw.items():
            base = dict(vanity_config[int(gid)])
            base.update(cfg or {})
            base["enabled"] = bool(base.get("enabled", False))
            base["role"] = int(base["role"]) if base.get("role") else None
            vanity_config[int(gid)] = base
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        pass

def save_vanity_config():
    try:
        with open(VANITY_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): dict(v) for k, v in vanity_config.items()}, f, indent=2)
    except OSError as exc:
        print(f"vanity config save failed: {exc}")

load_vanity_config()

def load_welcome_config():
    global welcome_config
    try:
        with open(WELCOME_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, cfg in raw.items():
            base = dict(welcome_config[int(gid)])
            base.update(cfg)
            welcome_config[int(gid)] = base
            if base.get("channel"):
                welcome_channels[int(gid)] = int(base["channel"])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        pass

def save_welcome_config():
    try:
        with open(WELCOME_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({str(k): dict(v) for k, v in welcome_config.items()}, f, indent=2)
    except OSError as exc:
        print(f"welcome config save failed: {exc}")

def get_welcome_config(guild_id):
    return welcome_config[guild_id]

def welcome_replace(text, member):
    replacements = {
        "{user}": member.mention,
        "{mention}": member.mention,
        "{username}": member.name,
        "{displayname}": member.display_name,
        "{server}": member.guild.name,
        "{membercount}": str(member.guild.member_count or len(member.guild.members)),
        "{id}": str(member.id),
        "{user_id}": str(member.id),
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def parse_color(value):
    value = value.strip().lower().replace("0x", "#")
    if not value.startswith("#"):
        value = "#" + value
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        return None
    return int(value[1:], 16)

def build_welcome_embed(member):
    cfg = get_welcome_config(member.guild.id)
    color = parse_color(cfg.get("color", "#000001")) or COLOR
    e = discord.Embed(
        title=welcome_replace(cfg.get("title", "Welcome to {server}!"), member),
        description=welcome_replace(cfg.get("description", "welcome {user} to **{server}**!"), member),
        color=color,
    )
    image = cfg.get("image")
    thumbnail = cfg.get("thumbnail")
    if image:
        e.set_image(url=welcome_replace(image, member))
    if thumbnail:
        thumb_url = member.display_avatar.url if thumbnail == "{user_avatar}" else welcome_replace(thumbnail, member)
        e.set_thumbnail(url=thumb_url)
    return e

load_welcome_config()


boost_roles = {}
autoresponders = defaultdict(dict)
autoroles = {}
autoreacts = defaultdict(dict)
antinuke_config = defaultdict(lambda: {"enabled": False, "threshold": 3, "window": 10, "action": "ban"})
antiraid_config = defaultdict(lambda: {"enabled": False, "threshold": 8, "window": 10})
raid_joins = defaultdict(deque)
filter_words = defaultdict(set)
filter_enabled = defaultdict(bool)
tickets = {}
giveaways = {}
reminders = {}

load_autorole_config()
load_autoreact_config()


def make_embed(title=None, description=None, *, footer=False, timestamp=False, ctx=None, icon=False):
    """Minimalist Greed-inspired visual system with original BLEEED layouts."""
    e = discord.Embed(color=COLOR)
    if title:
        heading = f"# {title}"
        e.description = heading if not description else f"{heading}\n{description}"
    elif description:
        e.description = description
    return e

def info_embed(ctx, title, fields, *, thumbnail=True):
    e = make_embed(title, ctx=ctx)
    for name, value, inline in fields:
        # Keep field labels short and structured; Discord renders markdown in fields.
        e.add_field(name=f"**{name}**", value=value, inline=inline)
    if thumbnail and getattr(ctx.guild, "icon", None):
        e.set_thumbnail(url=ctx.guild.icon.url)
    return e


def result_embed(title, label, value, *, extra=None):
    lines = [f"# {title}", f"**{label}**\n{value}"]
    if extra:
        for name, content in extra:
            lines.append(f"**{name}**\n{content}")
    return discord.Embed(description="\n\n".join(lines), color=COLOR)

def role_ok(member, role_ids):
    # Server Administrators always pass BLEEED's role-based moderation checks.
    return member.guild_permissions.administrator or any(r.id in role_ids for r in member.roles)


def target_ok(ctx, member):
    if member == ctx.author or member == ctx.guild.owner:
        return False
    me = ctx.guild.me
    if me is None:
        return False
    # The bot must be able to act on the target. The invoker must also outrank
    # the target unless they are the server owner/administrator.
    if member.top_role >= me.top_role:
        return False
    if not ctx.author.guild_permissions.administrator and member.top_role >= ctx.author.top_role:
        return False
    return True


def bot_can(ctx, permission):
    me = ctx.guild.me
    return bool(me and getattr(me.guild_permissions, permission, False))


def fmt_user(member):
    return f"{member.mention} (`{member.id}`)"


def has_manage(ctx):
    return ctx.author.guild_permissions.manage_guild


COMMAND_INFO = {
    "help": ("Show bot help or detailed command help.", "help [command]", "help 8ball", ["h"]),
    "commands": ("Browse all bleeed commands by category.", "commands", "commands", ["cmd"]),
    "ping": ("Check bleeed's latency.", "ping", "ping", []),
    "uptime": ("Show how long bleeed has been online.", "uptime", "uptime", []),
    "avatar": ("Show a user's avatar.", "avatar [member]", "avatar @user", ["av"]),
    "banner": ("Show a user's profile banner.", "banner [member]", "banner @user", []),
    "botinfo": ("Show bot information.", "botinfo", "botinfo", []),
    "userinfo": ("Show information about a member.", "userinfo [member]", "userinfo @user", ["ui"]),
    "serverinfo": ("Show information about the server.", "serverinfo", "serverinfo", ["si"]),
    "channelinfo": ("Show information about a channel.", "channelinfo [channel]", "channelinfo #general", []),
    "roleinfo": ("Show information about a role.", "roleinfo <role>", "roleinfo @Members", []),
    "membercount": ("Show the server member count.", "membercount", "membercount", []),
    "roles": ("List server roles.", "roles", "roles", []),
    "emojis": ("List custom server emojis.", "emojis", "emojis", []),
    "stickers": ("List server stickers.", "stickers", "stickers", []),
    "permissions": ("Show your permissions or another member's.", "permissions [member]", "permissions @user", []),
    "guildicon": ("Show the server icon.", "guildicon", "guildicon", []),
    "boost": ("Show the server boost count.", "boost", "boost", []),
    "welcome": ("Configure and customize welcome embeds.", "welcome <channel|title|description|color|image|thumbnail|preview|reset>", "welcome title Welcome to {server}!", []),
    "disablewelcome": ("Disable welcome messages.", "disablewelcome", "disablewelcome", []),
    "booster": ("Configure the automatic booster role.", "booster [role]", "booster @Booster", []),
    "boosterremove": ("Remove the automatic booster role.", "boosterremove", "boosterremove", ["booster-off"]),
    "ar": ("Manage server autoresponders.", "ar <add|remove|list|clear> [data]", "ar add hello | hi there", ["autoresponder"]),
    "autorole": ("Configure a role automatically given to new members.", "autorole [role]", "autorole @Member", []),
    "autoreact": ("Configure automatic reactions to a trigger.", "autoreact <add|remove|list|clear> [data]", "autoreact add hello | 👋", []),
    "ban": ("Ban a member.", "ban <member> [reason]", "ban @user spamming", ["b"]),
    "unban": ("Unban a user by ID.", "unban <user_id>", "unban 123456789", ["ub"]),
    "kick": ("Kick a member.", "kick <member> [reason]", "kick @user spamming", ["k"]),
    "mute": ("Timeout a member.", "mute <member> [minutes] [reason]", "mute @user 10 spam", ["timeout", "to"]),
    "unmute": ("Remove a member's timeout.", "unmute <member>", "unmute @user", ["um", "untimeout"]),
    "warn": ("Warn a member.", "warn <member> [reason]", "warn @user spam", ["w"]),
    "warnings": ("View a member's warnings.", "warnings [member]", "warnings @user", []),
    "purge": ("Delete recent messages.", "purge [amount]", "purge 25", ["p", "clear"]),
    "lock": ("Lock the current channel.", "lock", "lock", ["l"]),
    "unlock": ("Unlock the current channel.", "unlock", "unlock", ["ul"]),
    "snipe": ("Show the most recently deleted message in this channel.", "snipe", "snipe", ["s"]),
    "antinuke": ("Configure protection against destructive moderator actions.", "antinuke <enable|disable|status|threshold|action>", "antinuke enable", []),
    "antiraid": ("Configure basic join-spike protection.", "antiraid <enable|disable|status|threshold>", "antiraid enable", []),
    "filter": ("Configure a simple server word filter.", "filter <add|remove|list|on|off|clear> [word]", "filter add badword", []),
    "security": ("Show current security settings.", "security", "security", []),
    "8ball": ("Ask a question to the 8ball.", "8ball <question>", "8ball will i ever get married?", ["8", "ball"]),
    "coinflip": ("Flip a coin.", "coinflip", "coinflip", []),
    "roll": ("Roll a die.", "roll [sides]", "roll 20", []),
    "choose": ("Choose between options separated by |.", "choose <a | b | ...>", "choose pizza | pasta", []),
    "rps": ("Play rock paper scissors.", "rps <rock|paper|scissors>", "rps rock", []),
    "joke": ("Tell a short joke.", "joke", "joke", []),
    "fact": ("Give a random fact.", "fact", "fact", []),
    "rate": ("Give something a random rating.", "rate <thing>", "rate my setup", []),
    "roast": ("Give a lighthearted roast.", "roast [member]", "roast @user", []),
    "compliment": ("Give a friendly compliment.", "compliment [member]", "compliment @user", []),
    "wyr": ("Ask a would-you-rather question.", "wyr <question>", "wyr cats or dogs?", []),
    "mock": ("Convert text into alternating-case mock text.", "mock <text>", "mock skill issue", []),
    "reverse": ("Reverse text.", "reverse <text>", "reverse hello", []),
    "hug": ("Give someone a virtual hug.", "hug [member]", "hug @user", []),
    "pat": ("Give someone a virtual pat.", "pat [member]", "pat @user", []),
    "slap": ("Give someone a harmless cartoon slap.", "slap [member]", "slap @user", []),
    "love": ("Send some virtual love.", "love [member]", "love @user", []),
    "simp": ("Generate a silly simp percentage.", "simp [member]", "simp @user", []),
    "gayrate": ("Generate a silly percentage.", "gayrate [member]", "gayrate @user", []),
    "howlucky": ("Generate today's silly luck percentage.", "howlucky", "howlucky", []),
    "ship": ("Generate a silly compatibility percentage.", "ship <member> <member>", "ship @a @b", []),
    "shipname": ("Create a combined ship name.", "shipname <member> <member>", "shipname @a @b", []),
    "truth": ("Give a random truth prompt.", "truth", "truth", []),
    "dare": ("Give a safe, harmless dare.", "dare", "dare", []),
    "wouldyou": ("Generate a random would-you-rather prompt.", "wouldyou", "wouldyou", []),
    "8ball": ("Ask a question to the 8ball.", "8ball <question>", "8ball will i ever get married?", ["8", "ball"]),
    "afk": ("Set or update your AFK reason.", "afk [reason]", "afk eating", ["afkset"]),
    "poll": ("Create a simple yes/no poll.", "poll <question>", "poll should we open chat?", []),
    "ticket": ("Create a private support ticket.", "ticket [reason]", "ticket help with verification", []),
    "close": ("Close the current ticket channel.", "close", "close", []),
    "giveaway": ("Start a button-based giveaway.", "giveaway <duration> <winners> <prize>", "giveaway 1h 1 Nitro", []),
    "gaw": ("Start a giveaway.", "gaw <duration> <winners> <prize>", "gaw 30m 2 Gift Card", []),
    "announce": ("Send a server announcement embed.", "announce <message>", "announce server event tonight!", []),
    "slowmode": ("Set the current channel slowmode.", "slowmode <seconds>", "slowmode 5", []),
    "nick": ("Change a member's nickname.", "nick <member> [nickname]", "nick @user New Name", []),
    "addrole": ("Give a role to a member.", "addrole <member> <role>", "addrole @user @VIP", []),
    "removerole": ("Remove a role from a member.", "removerole <member> <role>", "removerole @user @VIP", []),
    "vanity": ("Give a configured role to members who put /bleeed in their custom status.", "vanity [role|off|status]", "vanity @bleeed", []),
    "deleterole": ("Delete a server role.", "deleterole <role>", "deleterole @OldRole", ["delrole", "roledelete"]),
    "changerole": ("Change a role's name, color, icon, hoist, or mentionable setting.", "changerole <role> <changes>", "changerole @VIP name=VIP color=#efcead icon=⭐", ["editrole", "rolechange"]),
    "create": ("Create a server role, text channel, or voice channel.", "create <role|channel|vc> <name>", "create role VIP", []),
    "create role": ("Create a new server role.", "create role <name>", "create role VIP", []),
    "create channel": ("Create a new text channel.", "create channel <name>", "create channel general", []),
    "create vc": ("Create a new voice channel.", "create vc <name>", "create vc Gaming", ["create voice"]),
    "remind": ("Create a personal reminder.", "remind <duration> <message>", "remind 30m check chat", []),
}

# Extra utility commands
COMMAND_INFO.update({
    "serverstats": ("Show a compact server statistics overview.", "serverstats", "serverstats", []),
    "firstmessage": ("Find the oldest message in the current channel.", "firstmessage", "firstmessage", []),
    "invites": ("List server invites.", "invites", "invites", []),
    "inviteinfo": ("Look up an invite code.", "inviteinfo <code>", "inviteinfo abcDEF", []),
    "voiceinfo": ("Show your current voice-channel information.", "voiceinfo", "voiceinfo", ["vcinfo"]),
    "say": ("Send a message as bleeed. Staff only.", "say <message>", "say hello everyone", []),
    "topic": ("Set the current channel topic.", "topic <text>", "topic community chat", []),
    "unwarn": ("Remove one warning from a member.", "unwarn <member> <number>", "unwarn @user 1", []),
    "clearwarnings": ("Clear all warnings for a member.", "clearwarnings <member>", "clearwarnings @user", []),
    "servericon": ("Show the server icon.", "servericon", "servericon", ["icon"]),
})

CATEGORIES = [
    ("Information", ["help", "commands", "ping", "uptime", "avatar", "banner", "botinfo", "userinfo", "serverinfo", "channelinfo", "roleinfo", "membercount", "roles", "emojis", "stickers", "permissions", "guildicon", "servericon", "boost", "serverstats", "firstmessage", "invites", "inviteinfo", "voiceinfo"]),
    ("Server", ["welcome", "disablewelcome", "booster", "boosterremove", "ar", "autorole", "autoreact", "poll", "ticket", "close", "giveaway", "gaw", "announce", "remind", "vanity"]),
    ("Roles", ["addrole", "removerole", "deleterole", "changerole", "create", "create role", "create channel", "create vc"]),
    ("Security", ["antinuke", "antiraid", "filter", "security"]),
    ("Moderation", ["ban", "unban", "kick", "mute", "unmute", "warn", "warnings", "unwarn", "clearwarnings", "purge", "lock", "unlock", "snipe", "slowmode", "nick", "topic", "say"]),
    ("Fun", ["8ball", "coinflip", "roll", "choose", "rps", "joke", "fact", "rate", "wyr", "mock", "reverse", "truth", "dare", "wouldyou"]),
    ("Social", ["hug", "pat", "slap", "love", "simp", "gayrate", "howlucky", "ship", "shipname", "roast", "compliment"]),
    ("Utility", ["afk"]),
]


def command_text(name):
    return f"`{name}`"


def build_pages():
    # Keep every documented command visible. Anything added later that is not
    # assigned to a category automatically appears on the final page.
    lookup = dict(CATEGORIES)
    page_groups = [
        ["Information", "Server"],
        ["Roles", "Security"],
        ["Moderation"],
        ["Fun", "Social", "Utility"],
    ]
    used = set()
    pages = []
    for group in page_groups:
        blocks = []
        for title in group:
            names = [name for name in lookup.get(title, []) if name in COMMAND_INFO]
            used.update(names)
            if names:
                blocks.append(f"# {title}\n" + " ".join(command_text(name) for name in names))
        pages.append("\n\n".join(blocks))

    leftovers = [name for name in COMMAND_INFO if name not in used]
    if leftovers:
        pages.append("# More\n" + " ".join(command_text(name) for name in leftovers))
    return pages


class CommandsView(discord.ui.View):
    def __init__(self, pages, author_id):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.page.label = f"{self.index + 1}/{len(self.pages)}"

    def embed(self):
        description = (
            "-# Experience the ultimate Discord bot designed for seamless management and community engagement.\n\n"
            f"{self.pages[self.index]}\n\n"
            f"-# Use `{PREFIX}help (command)` for details on a specific command"
        )
        return make_embed("bleeed help", description)

    async def check_user(self, interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("only the command author or staff can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="‹", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="1/3", style=discord.ButtonStyle.secondary, disabled=True)
    async def page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="›", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help • bleeed"))
    try:
        await bot.tree.sync()
        print("slash commands synced")
    except Exception as exc:
        print(f"slash sync failed: {exc}")
    print(f"bleeed online as {bot.user} ({bot.user.id})")
    try:
        await sync_all_vanity()
    except Exception as exc:
        print(f"initial vanity sync failed: {exc}")


@bot.event
async def on_member_join(member):
    cfg = antiraid_config[member.guild.id]
    if cfg["enabled"]:
        q = raid_joins[member.guild.id]
        now = time.time(); q.append(now)
        while q and now - q[0] > cfg["window"]: q.popleft()
        if len(q) >= cfg["threshold"]:
            channel = member.guild.system_channel
            if channel:
                await channel.send(embed=make_embed("anti-raid alert", f"join spike detected: **{len(q)}** members joined within {cfg['window']} seconds."))
    role_id = autoroles.get(member.guild.id)
    if role_id:
        role = member.guild.get_role(role_id)
        if role and role < member.guild.me.top_role:
            try: await member.add_roles(role, reason="bleeed autorole")
            except discord.HTTPException: pass
    cfg = get_welcome_config(member.guild.id)
    channel_id = cfg.get("channel") or welcome_channels.get(member.guild.id)
    if cfg.get("enabled") and channel_id:
        channel = member.guild.get_channel(int(channel_id))
        if channel:
            try:
                await channel.send(embed=build_welcome_embed(member))
            except discord.HTTPException as exc:
                print(f"welcome send failed: {exc}")


@bot.event
async def on_member_update(before, after):
    if before.premium_since is None and after.premium_since is not None:
        role_id = boost_roles.get(after.guild.id)
        if role_id:
            role = after.guild.get_role(role_id)
            if role and role < after.guild.me.top_role:
                try: await after.add_roles(role, reason="bleeed booster role")
                except discord.HTTPException: pass
        if after.guild.system_channel:
            await after.guild.system_channel.send(embed=make_embed("boost", f"thank you {after.mention} for boosting **{after.guild.name}**! ♡"))


def vanity_replace(text, member, role=None):
    if text is None:
        return None
    role_mention = role.mention if role else (f"<@&{getattr(role, 'id', 0)}>" if role else "")
    replacements = {
        "{user}": member.mention,
        "{mention}": member.mention,
        "{username}": member.name,
        "{displayname}": member.display_name,
        "{server}": member.guild.name,
        "{membercount}": str(member.guild.member_count or len(member.guild.members)),
        "{id}": str(member.id),
        "{user_id}": str(member.id),
        "{role}": role_mention,
        "{role_name}": role.name if role else "",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def build_vanity_embed(member):
    cfg = vanity_config[member.guild.id]
    role = member.guild.get_role(cfg.get("role")) if cfg.get("role") else None
    try:
        color = int(str(cfg.get("color", "#000001")).replace("#", ""), 16)
    except ValueError:
        color = COLOR
    e = discord.Embed(
        title=vanity_replace(cfg.get("title", "Vanity Unlocked!"), member, role),
        description=vanity_replace(cfg.get("description", "{user} has `/bleeed` in their status and received {role}!"), member, role),
        color=color,
    )
    image = cfg.get("image")
    thumbnail = cfg.get("thumbnail")
    if image:
        e.set_image(url=vanity_replace(image, member, role))
    if thumbnail:
        thumb_url = member.display_avatar.url if thumbnail == "{user_avatar}" else vanity_replace(thumbnail, member, role)
        if thumb_url:
            e.set_thumbnail(url=thumb_url)
    return e

def vanity_status_active(member):
    """Return True when /bleeed appears in the member's custom status."""
    for activity in getattr(member, "activities", ()):
        if isinstance(activity, discord.CustomActivity):
            text = str(getattr(activity, "state", "") or "")
            if "/bleeed" in text.lower():
                return True
    return False


@bot.event
async def on_presence_update(before, after):
    try:
        await sync_vanity_member(after)
    except Exception as exc:
        print(f"presence handler failed in {after.guild.id}/{after.id}: {exc}")


async def sync_vanity_member(member):
    cfg = vanity_config.get(member.guild.id, {"enabled": False, "role": None})
    if not cfg.get("enabled") or not cfg.get("role"):
        return
    role = member.guild.get_role(int(cfg["role"]))
    me = member.guild.me
    if not role or not me or role >= me.top_role or role.is_default() or role.managed:
        return
    active = vanity_status_active(member)
    has_role = role in member.roles
    try:
        if active and not has_role:
            await member.add_roles(role, reason="bleeed vanity status: /bleeed")
        elif not active and has_role:
            await member.remove_roles(role, reason="bleeed vanity status removed")
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"vanity role sync failed in {member.guild.id}/{member.id}: {exc}")

async def sync_all_vanity():
    for guild in bot.guilds:
        cfg = vanity_config.get(guild.id)
        if not cfg or not cfg.get("enabled") or not cfg.get("role"):
            continue
        for member in list(guild.members):
            try:
                await sync_vanity_member(member)
            except Exception as exc:
                print(f"vanity sync error in {guild.id}/{member.id}: {exc}")

@bot.event
async def on_resumed():
    print("discord session resumed")
    await sync_all_vanity()

@bot.event
async def on_message_delete(message):
    if not message.author.bot and message.guild:
        if not hasattr(bot, "_snipes"):
            bot._snipes = defaultdict(lambda: deque(maxlen=100))
        attachments = [a.url for a in message.attachments]
        bot._snipes[message.channel.id].appendleft({
            "author_id": message.author.id,
            "author_name": message.author.display_name,
            "author_tag": str(message.author),
            "content": message.content or "",
            "attachments": attachments,
            "created_at": message.created_at.timestamp() if message.created_at else time.time(),
            "deleted_at": time.time(),
            "message_id": message.id,
        })


async def audit_actor(guild, action):
    try:
        async for entry in guild.audit_logs(limit=1, action=action):
            if time.time() - entry.created_at.timestamp() < 8:
                return entry.user
    except (discord.Forbidden, discord.HTTPException):
        pass
    return None


async def antinuke_check(guild, action):
    cfg = antinuke_config[guild.id]
    if not cfg["enabled"]: return
    actor = await audit_actor(guild, action)
    if not actor or actor.bot or actor.id == guild.owner_id: return
    me = guild.me
    if actor.top_role >= me.top_role: return
    key = (guild.id, actor.id, str(action))
    if not hasattr(bot, "_nuke_events"): bot._nuke_events = defaultdict(deque)
    q = bot._nuke_events[key]; now = time.time(); q.append(now)
    while q and now - q[0] > cfg["window"]: q.popleft()
    if len(q) < cfg["threshold"]: return
    try:
        if cfg["action"] == "kick": await guild.kick(actor, reason="bleeed antinuke")
        else: await guild.ban(actor, reason="bleeed antinuke", delete_message_seconds=0)
        ch = guild.system_channel
        if ch: await ch.send(embed=make_embed("antinuke", f"blocked destructive activity from **{actor}**."))
    except discord.HTTPException: pass


@bot.event
async def on_guild_channel_delete(channel):
    await antinuke_check(channel.guild, discord.AuditLogAction.channel_delete)

@bot.event
async def on_guild_role_delete(role):
    await antinuke_check(role.guild, discord.AuditLogAction.role_delete)


@bot.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower().strip()
    if message.guild:
        if filter_enabled[message.guild.id] and any(w in content.split() for w in filter_words[message.guild.id]):
            try: await message.delete()
            except discord.HTTPException: pass
            return
        if content in autoreacts[message.guild.id]:
            for reaction in autoreacts[message.guild.id][content][:3]:
                try:
                    await message.add_reaction(reaction)
                except (discord.HTTPException, discord.Forbidden) as exc:
                    print(f"autoreact failed in {message.guild.id}: {exc}")
        if content in autoresponders[message.guild.id]:
            try:
                await message.channel.send(autoresponders[message.guild.id][content])
            except (discord.HTTPException, discord.Forbidden) as exc:
                print(f"autoresponder failed in {message.guild.id}: {exc}")
    if message.author.id in afk_data and not content.startswith(PREFIX):
        afk_data.pop(message.author.id, None)
        await message.channel.send(embed=make_embed("afk removed", f"welcome back {message.author.mention}! your AFK has been removed."), delete_after=5)
    for uid, data in list(afk_data.items()):
        if uid != message.author.id and f"<@{uid}>" in message.content:
            await message.channel.send(embed=make_embed("afk", f"**{data['name']}** is AFK — {data['reason']}"), delete_after=8)
    await bot.process_commands(message)


@bot.command(aliases=["h"])
async def help(ctx, command_name=None):
    if command_name:
        cmd = bot.get_command(command_name.lower())
        if not cmd: return await ctx.send(embed=make_embed("command not found", f"I couldn't find `,{command_name}`. Use `,commands` to see every command."))
        info = COMMAND_INFO.get(cmd.name, (cmd.help or "No description available.", cmd.qualified_name, cmd.qualified_name, cmd.aliases))
        description, syntax, example, aliases = info
        alias_text = ", ".join(aliases) if aliases else "none"
        desc = f"# Command: {cmd.name}\n{description}\n\n**Aliases**\n{alias_text}\n\n**Usage**\n`Syntax: {PREFIX}{syntax}\nExample: {PREFIX}{example}`"
        return await ctx.send(embed=make_embed(None, desc))
    e = make_embed("bleeed", f"to use **bleeed** you must use the prefix `{PREFIX}`.\n\nexample: `{PREFIX}ping`\n\nuse `{PREFIX}commands` to see every command.\nuse `{PREFIX}help <command>` for command usage, aliases, and examples.")
    await ctx.send(embed=e)


@bot.command(name="commands", aliases=["cmd"])
async def command_list(ctx):
    pages = build_pages(); view = CommandsView(pages, ctx.author.id)
    msg = await ctx.send(embed=view.embed(), view=view); view.message = msg


@bot.command()
async def ping(ctx): await ctx.send(embed=make_embed("pong", f"`{round(bot.latency * 1000)}ms`"))

@bot.command()
async def uptime(ctx):
    s=int(time.time()-start_time); await ctx.send(embed=make_embed("uptime", f"<t:{int(start_time)}:R>\n`{s//3600}h {(s%3600)//60}m {s%60}s`"))

@bot.command(aliases=["av"])
async def avatar(ctx, member: discord.Member=None):
    member=member or ctx.author; e=make_embed(f"{member.display_name}'s avatar"); e.set_image(url=member.display_avatar.url); await ctx.send(embed=e)

@bot.command()
async def banner(ctx, member: discord.Member=None):
    member=member or ctx.author
    user=await bot.fetch_user(member.id)
    if not user.banner: return await ctx.send(embed=make_embed("banner", "that user doesn't have a profile banner."))
    e=make_embed(f"{member.display_name}'s banner"); e.set_image(url=user.banner.url); await ctx.send(embed=e)

@bot.command()
async def botinfo(ctx):
    e = info_embed(ctx, "Bot Information", [
        ("Prefix", f"`{PREFIX}`", True),
        ("Library", "`discord.py`", True),
        ("Servers", f"`{len(bot.guilds)}`", True),
        ("Latency", f"`{round(bot.latency * 1000)}ms`", True),
        ("Uptime", f"<t:{int(start_time)}:R>", True),
        ("Commands", f"`{len(bot.commands)}`", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="userinfo", aliases=["ui"], description="View detailed information about a member.")
async def userinfo(ctx, member: discord.Member=None):
    member = member or ctx.author
    try:
        joined = f"<t:{int(member.joined_at.timestamp())}:F>\n<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "unknown"
        roles = [r.mention for r in member.roles if not r.is_default()]
        role_text = " · ".join(roles[-15:]) if roles else "none"
        created = int(member.created_at.timestamp())
        e = discord.Embed(color=COLOR)
        e.description = (
            "# User Information\n\n"
            f"**User**\n{member.mention} · `{member.id}`\n\n"
            f"**Created**\n<t:{created}:F> · <t:{created}:R>\n\n"
            f"**Joined**\n{joined}\n\n"
            f"**Roles**\n{role_text}"
        )
        e.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=e)
    except Exception as exc:
        print(f"userinfo error: {type(exc).__name__}: {exc}")
        await ctx.send(embed=result_embed("User Information", "Error", "I couldn't load that member's information."))

@bot.hybrid_command(name="serverinfo", aliases=["si"], description="View information about the server.")
async def serverinfo(ctx):
    g = ctx.guild
    e = info_embed(ctx, "Server Information", [
        ("Server", f"**{g.name}**\n`{g.id}`", False),
        ("Owner", f"<@{g.owner_id}>", True),
        ("Members", f"`{g.member_count}`", True),
        ("Channels", f"`{len(g.channels)}`", True),
        ("Roles", f"`{len(g.roles)}`", True),
        ("Created", f"<t:{int(g.created_at.timestamp())}:R>", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="channelinfo", description="View information about a channel.")
async def channelinfo(ctx, channel: discord.TextChannel=None):
    c = channel or ctx.channel
    e = info_embed(ctx, "Channel Information", [
        ("Channel", f"{c.mention} · `{c.id}`", False),
        ("Type", f"`{c.type}`", True),
        ("Position", f"`{c.position}`", True),
        ("Created", f"<t:{int(c.created_at.timestamp())}:R>", False),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="roleinfo", description="View information about a role.")
async def roleinfo(ctx, role: discord.Role):
    e = info_embed(ctx, "Role Information", [
        ("Role", f"{role.mention} · `{role.id}`", False),
        ("Members", f"`{len(role.members)}`", True),
        ("Position", f"`{role.position}`", True),
        ("Color", f"`{role.color}`", True),
        ("Created", f"<t:{int(role.created_at.timestamp())}:R>", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="membercount", description="Show server member counts.")
async def membercount(ctx):
    g = ctx.guild
    humans = sum(not m.bot for m in g.members)
    bots = g.member_count - humans
    e = info_embed(ctx, "Member Count", [
        ("Total", f"`{g.member_count}`", True),
        ("Humans", f"`{humans}`", True),
        ("Bots", f"`{bots}`", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="serverstats", description="Show compact server statistics.")
async def serverstats(ctx):
    g = ctx.guild
    humans = sum(not m.bot for m in g.members)
    bots = g.member_count - humans
    text_channels = sum(isinstance(c, discord.TextChannel) for c in g.channels)
    voice_channels = sum(isinstance(c, discord.VoiceChannel) for c in g.channels)
    categories = sum(isinstance(c, discord.CategoryChannel) for c in g.channels)
    e = info_embed(ctx, "Server Statistics", [
        ("Members", f"`{g.member_count}` total · `{humans}` humans · `{bots}` bots", False),
        ("Channels", f"`{text_channels}` text · `{voice_channels}` voice · `{categories}` categories", False),
        ("Roles", f"`{len(g.roles) - 1}` custom", True),
        ("Emojis", f"`{len(g.emojis)}`", True),
        ("Stickers", f"`{len(g.stickers)}`", True),
        ("Boosts", f"`{g.premium_subscription_count or 0}`", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="firstmessage", description="Find the oldest message in the current channel.")
async def firstmessage(ctx):
    try:
        oldest = None
        async for msg in ctx.channel.history(limit=1, oldest_first=True):
            oldest = msg
        if not oldest:
            return await ctx.send(embed=make_embed("first message", "no messages were found."))
        content = discord.utils.escape_markdown(oldest.content[:1000]) or "[no text]"
        value = (
            f"[jump to message]({oldest.jump_url})\n"
            f"by {oldest.author.mention}\n"
            f"<t:{int(oldest.created_at.timestamp())}:F>\n\n"
            f"{content}"
        )
        await ctx.send(embed=result_embed("First Message", "Message", value))
    except (discord.Forbidden, discord.HTTPException):
        await ctx.send(embed=make_embed("first message", "I couldn't read this channel's history."))

@bot.hybrid_command(name="invites", description="List server invites.")
@commands.has_guild_permissions(manage_guild=True)
async def invites(ctx):
    try:
        data = await ctx.guild.invites()
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("invites", "I need **Manage Server** to view invites."))
    if not data:
        return await ctx.send(embed=make_embed("invites", "no active invites were found."))
    lines=[]
    for inv in data[:20]:
        uses = inv.uses if inv.uses is not None else 0
        lines.append(f"`{inv.code}` · **{uses}** uses · {inv.channel.mention if inv.channel else 'unknown channel'}")
    await ctx.send(embed=make_embed("Invites", "\n".join(lines)))

@bot.hybrid_command(name="inviteinfo", description="Look up an invite code.")
async def inviteinfo(ctx, code: str):
    code = code.split("/")[-1].split("?")[0]
    try:
        inv = await bot.fetch_invite(code, with_counts=True)
    except (discord.NotFound, discord.HTTPException):
        return await ctx.send(embed=make_embed("invite info", "that invite is invalid or expired."))
    guild_name = inv.guild.name if inv.guild else "unknown"
    channel_name = inv.channel.name if inv.channel else "unknown"
    e = result_embed("Invite Information", "Code", f"`{inv.code}`", extra=[
        ("Server", f"**{guild_name}**"),
        ("Channel", f"**#{channel_name}**"),
        ("Members", f"`{inv.approximate_member_count or 0}` total · `{inv.approximate_presence_count or 0}` online"),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="voiceinfo", aliases=["vcinfo"], description="Show your current voice-channel information.")
async def voiceinfo(ctx, member: discord.Member=None):
    member = member or ctx.author
    voice = member.voice
    if not voice or not voice.channel:
        return await ctx.send(embed=make_embed("Voice Information", f"{member.mention} is not connected to a voice channel."))
    c = voice.channel
    e = info_embed(ctx, "Voice Information", [
        ("Member", f"{member.mention} · `{member.id}`", False),
        ("Channel", f"{c.mention} · `{c.id}`", False),
        ("Members", f"`{len(c.members)}`", True),
        ("Mute", f"`{member.voice.self_mute or member.voice.mute}`", True),
        ("Deaf", f"`{member.voice.self_deaf or member.voice.deaf}`", True),
    ])
    await ctx.send(embed=e)

@bot.hybrid_command(name="say", description="Send a message as bleeed.")
@commands.has_guild_permissions(manage_messages=True)
async def say(ctx, *, message: str):
    await ctx.send(message)

@bot.hybrid_command(name="topic", description="Set the current channel topic.")
@commands.has_guild_permissions(manage_channels=True)
async def topic(ctx, *, text: str):
    if not isinstance(ctx.channel, discord.TextChannel):
        return await ctx.send(embed=make_embed("topic", "this command can only be used in a text channel."))
    if len(text) > 1024:
        return await ctx.send(embed=make_embed("topic", "the topic must be 1024 characters or less."))
    await ctx.channel.edit(topic=text, reason=f"topic changed by {ctx.author}")
    await ctx.send(embed=result_embed("Channel Updated", "Topic", text, extra=[("Channel", ctx.channel.mention)]))

@bot.hybrid_command(name="unwarn", description="Remove one warning from a member.")
async def unwarn(ctx, member: discord.Member, number: int):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you don't have the required warn role."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    items = warning_data[ctx.guild.id][member.id]
    if number < 1 or number > len(items):
        return await ctx.send(embed=make_embed("warning", f"warning **#{number}** doesn't exist for {member.mention}."))
    removed = items.pop(number - 1)
    await ctx.send(embed=result_embed("Warning Removed", "User", member.mention, extra=[("Warning", f"`#{number}` · {removed}"), ("Moderator", ctx.author.mention)]))

@bot.hybrid_command(name="clearwarnings", description="Clear all warnings for a member.")
async def clearwarnings(ctx, member: discord.Member):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you don't have the required warn role."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    count = len(warning_data[ctx.guild.id][member.id])
    warning_data[ctx.guild.id][member.id].clear()
    await ctx.send(embed=result_embed("Warnings Cleared", "User", member.mention, extra=[("Removed", f"`{count}` warnings"), ("Moderator", ctx.author.mention)]))

@bot.hybrid_command(name="servericon", aliases=["icon"], description="Show the server icon.")
async def servericon(ctx):
    if not ctx.guild.icon:
        return await ctx.send(embed=make_embed("Server Icon", "this server doesn't have an icon."))
    e=make_embed("Server Icon")
    e.set_image(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

class RolesView(discord.ui.View):
    def __init__(self, pages, author_id, guild_name):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        self.guild_name = guild_name
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.pages) - 1
        self.page.label = f"Page {self.index + 1}/{len(self.pages)}"

    def embed(self):
        return make_embed(None, self.pages[self.index], footer=False, timestamp=False)

    async def check_user(self, interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("only the command author or staff can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="‹", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="›", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

@bot.hybrid_command(name="roles", description="List server roles.")
async def roles(ctx):
    # Match the compact Bleed/Greed-style role directory: 10 roles per page.
    role_list = list(reversed(ctx.guild.roles))
    if role_list and role_list[-1].is_default():
        role_list.pop()
    if not role_list:
        return await ctx.send(embed=make_embed(None, f"# Roles in {ctx.guild.name}\nno roles found.", footer=False, timestamp=False))

    pages = []
    total_pages = (len(role_list) + 9) // 10
    for page_index in range(total_pages):
        chunk = role_list[page_index * 10:(page_index + 1) * 10]
        lines = [f"# Roles in {ctx.guild.name}"]
        for offset, role in enumerate(chunk, start=page_index * 10 + 1):
            lines.append(f"`{offset:02d}` **{role.mention}** · `{role.id}`")
        lines.append(f"-# Page {page_index + 1}/{total_pages}")
        pages.append("\n".join(lines))

    view = RolesView(pages, ctx.author.id, ctx.guild.name)
    msg = await ctx.send(embed=view.embed(), view=view)
    view.message = msg

@bot.hybrid_command(name="emojis", description="List custom server emojis.")
async def emojis(ctx): await ctx.send(embed=make_embed("emojis", " ".join(str(e) for e in ctx.guild.emojis) or "no custom emojis."))

@bot.hybrid_command(name="stickers", description="List server stickers.")
async def stickers(ctx): await ctx.send(embed=make_embed("stickers", " ".join(f"`{s.name}`" for s in ctx.guild.stickers) or "no stickers."))

@bot.command()
async def permissions(ctx, member: discord.Member=None):
    member=member or ctx.author; perms=[p.replace("_", " ") for p,v in member.guild_permissions if v]; await ctx.send(embed=make_embed("permissions", f"**{member.mention}**\n" + ", ".join(perms)))

@bot.command()
async def guildicon(ctx):
    e=make_embed("server icon")
    if ctx.guild.icon:
        e.set_image(url=ctx.guild.icon.url)
    await ctx.send(embed=e)

@bot.command()
async def boost(ctx):
    g = ctx.guild
    e = info_embed(ctx, "Server Boosts", [
        ("Boosts", f"`{g.premium_subscription_count or 0}`", True),
        ("Level", f"`{g.premium_tier}`", True),
        ("Boosters", f"`{len(g.premium_subscribers)}`", True),
    ])
    await ctx.send(embed=e)

@bot.command()
async def welcome(ctx, action=None, *, value=""):

    if not has_manage(ctx):
        return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))

    cfg = get_welcome_config(ctx.guild.id)
    action = (action or "status").lower()

    # Keep the original easy setup: ,welcome #welcome
    if action.startswith("<@&") or action.startswith("<#") or action.startswith("#"):
        channel = None
        if ctx.message.channel_mentions:
            channel = ctx.message.channel_mentions[0]
        elif action.startswith("#"):
            try:
                channel = ctx.guild.get_channel(int(action[1:]))
            except ValueError:
                channel = None
        if not channel:
            return await ctx.send(embed=make_embed("welcome", f"usage: `{PREFIX}welcome #channel`"))
        cfg["enabled"] = True
        cfg["channel"] = channel.id
        welcome_channels[ctx.guild.id] = channel.id
        save_welcome_config()
        return await ctx.send(embed=make_embed("Welcome Enabled", f"welcome messages will be sent in {channel.mention}."))

    if action in {"channel", "setchannel"}:
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        if not channel:
            return await ctx.send(embed=make_embed("Welcome", f"usage: `{PREFIX}welcome channel #welcome`"))
        cfg["enabled"] = True
        cfg["channel"] = channel.id
        welcome_channels[ctx.guild.id] = channel.id
        save_welcome_config()
        return await ctx.send(embed=make_embed("Welcome Channel Updated", f"channel: {channel.mention}"))

    if action in {"status", "settings"}:
        channel = ctx.guild.get_channel(cfg.get("channel")) if cfg.get("channel") else None
        body = (
            f"**Enabled**\n`{cfg.get('enabled', False)}`\n\n"
            f"**Channel**\n{channel.mention if channel else 'not configured'}\n\n"
            f"**Title**\n{cfg.get('title', '')}\n\n"
            f"**Description**\n{cfg.get('description', '')}\n\n"
            f"**Color**\n`{cfg.get('color', '#000001')}`\n\n"
            f"**Image**\n{cfg.get('image') or 'none'}\n\n"
            f"**Thumbnail**\n{cfg.get('thumbnail') or 'none'}"
        )
        return await ctx.send(embed=make_embed("Welcome Settings", body))

    if action == "title":
        if not value.strip():
            return await ctx.send(embed=make_embed("Welcome", f"usage: `{PREFIX}welcome title Welcome to {{server}}!`"))
        cfg["title"] = value.strip()[:256]
    elif action in {"description", "desc", "message"}:
        if not value.strip():
            return await ctx.send(embed=make_embed("Welcome", f"usage: `{PREFIX}welcome description Welcome {{user}} to {{server}}!`"))
        cfg["description"] = value.strip()[:4096]
    elif action == "color":
        parsed = parse_color(value)
        if parsed is None:
            return await ctx.send(embed=make_embed("Welcome", "color must be a 6-digit hex value, for example `#efcead`."))
        cfg["color"] = "#" + format(parsed, "06x")
    elif action == "image":
        if value.lower() in {"off", "none", "remove"}:
            cfg["image"] = None
        elif value.startswith(("http://", "https://")):
            cfg["image"] = value.strip()
        else:
            return await ctx.send(embed=make_embed("Welcome", "image must be a direct `http://` or `https://` URL, or `off`."))
    elif action == "thumbnail":
        if value.lower() in {"off", "none", "remove"}:
            cfg["thumbnail"] = None
        elif value.lower() in {"user", "avatar", "default"}:
            cfg["thumbnail"] = "{user_avatar}"
        elif value.startswith(("http://", "https://")):
            cfg["thumbnail"] = value.strip()
        else:
            return await ctx.send(embed=make_embed("Welcome", "thumbnail must be `user`, a direct URL, or `off`."))
    elif action == "preview":
        # Preview uses the command author as a fake new member.
        fake_member = ctx.author
        return await ctx.send(embed=build_welcome_embed(fake_member))
    elif action == "reset":
        welcome_config.pop(ctx.guild.id, None)
        welcome_channels.pop(ctx.guild.id, None)
        save_welcome_config()
        return await ctx.send(embed=make_embed("Welcome Reset", "the welcome embed has been reset to its default settings."))
    elif action in {"help", "commands"}:
        return await ctx.send(embed=make_embed("Welcome Setup",
            f"`{PREFIX}welcome #channel` — enable welcome messages\n"
            f"`{PREFIX}welcome title <text>` — edit the title\n"
            f"`{PREFIX}welcome description <text>` — edit the message\n"
            f"`{PREFIX}welcome color #hex` — edit the embed color\n"
            f"`{PREFIX}welcome image <url|off>` — set/remove the image\n"
            f"`{PREFIX}welcome thumbnail <user|url|off>` — set the thumbnail\n"
            f"`{PREFIX}welcome preview` — preview it\n"
            f"`{PREFIX}welcome settings` — view settings\n"
            f"`{PREFIX}welcome reset` — restore defaults\n\n"
            f"Variables: `{user}` `{username}` `{displayname}` `{server}` `{membercount}` `{id}`"
        ))
    else:
        return await ctx.send(embed=make_embed("Welcome", f"unknown option `{action}`. Use `{PREFIX}welcome help`."))

    cfg["enabled"] = bool(cfg.get("channel"))
    save_welcome_config()
    await ctx.send(embed=make_embed("Welcome Updated", f"**{action}** has been updated. Use `{PREFIX}welcome preview` to see the current embed."))

@bot.command()
async def disablewelcome(ctx):
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    cfg = get_welcome_config(ctx.guild.id)
    cfg["enabled"] = False
    welcome_channels.pop(ctx.guild.id, None)
    save_welcome_config()
    await ctx.send(embed=make_embed("Welcome Disabled", "welcome messages are now disabled. Your custom embed settings were kept."))

@bot.command()
async def booster(ctx, role: discord.Role=None):
    if role is None:
        rid=boost_roles.get(ctx.guild.id); return await ctx.send(embed=make_embed("booster", f"booster role: {ctx.guild.get_role(rid).mention if rid and ctx.guild.get_role(rid) else 'not configured'}"))
    if not ctx.author.guild_permissions.manage_roles: return await ctx.send(embed=make_embed("no permission", "you need Manage Roles."))
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("error", "my role must be above the booster role."))
    boost_roles[ctx.guild.id]=role.id; await ctx.send(embed=make_embed("booster role set", f"boosters will receive {role.mention}."))

@bot.command(name="boosterremove", aliases=["booster-off"])
async def boosterremove(ctx):
    if not ctx.author.guild_permissions.manage_roles: return await ctx.send(embed=make_embed("no permission", "you need Manage Roles."))
    boost_roles.pop(ctx.guild.id,None); await ctx.send(embed=make_embed("booster role removed", "automatic booster roles are disabled."))

@bot.command(name="ar", aliases=["autoresponder"])
async def ar(ctx, action="list", *, data=""):
    if action.lower() in {"add","remove","clear"} and not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    d=autoresponders[ctx.guild.id]; action=action.lower()
    if action=="add":
        if "|" not in data: return await ctx.send(embed=make_embed("autoresponder", f"usage: `{PREFIX}ar add trigger | response`"))
        t,r=[x.strip() for x in data.split("|",1)]; d[t.lower()]=r; return await ctx.send(embed=make_embed("autoresponder added", f"`{t}` → {r}"))
    if action=="remove": d.pop(data.lower().strip(),None); save_autoreact_config(); return await ctx.send(embed=make_embed("autoresponder removed", f"removed `{data}`."))
    if action=="clear": d.clear(); save_autoreact_config(); return await ctx.send(embed=make_embed("autoresponders cleared", "all autoresponders were removed."))
    text="\n".join(f"`{k}` → {v}" for k,v in d.items()) or "no autoresponders are configured."; await ctx.send(embed=make_embed("autoresponders", text))

@bot.command()
async def autorole(ctx, role: discord.Role=None):
    if role is None:
        rid=autoroles.get(ctx.guild.id); return await ctx.send(embed=make_embed("autorole", f"{ctx.guild.get_role(rid).mention if rid and ctx.guild.get_role(rid) else 'not configured'}"))
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("error", "my role must be above that role."))
    autoroles[ctx.guild.id]=role.id; save_autorole_config(); await ctx.send(embed=make_embed("autorole set", f"new members will receive {role.mention}."))

@bot.command()
async def autoreact(ctx, action="list", *, data=""):
    if action in {"add","remove","clear"} and not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    d=autoreacts[ctx.guild.id]
    if action=="add":
        if "|" not in data: return await ctx.send(embed=make_embed("autoreact", f"usage: `{PREFIX}autoreact add trigger | emoji`"))
        t,e=[x.strip() for x in data.split("|",1)]; d.setdefault(t.lower(),[]).append(e); save_autoreact_config(); return await ctx.send(embed=make_embed("autoreact added", f"`{t}` → {e}"))
    if action=="remove": d.pop(data.lower().strip(),None); return await ctx.send(embed=make_embed("autoreact removed", f"removed `{data}`."))
    if action=="clear": d.clear(); return await ctx.send(embed=make_embed("autoreacts cleared", "all automatic reactions were removed."))
    await ctx.send(embed=make_embed("autoreacts", "\n".join(f"`{k}` → {' '.join(v)}" for k,v in d.items()) or "none configured."))

@bot.command(aliases=["b"])
async def ban(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author, {BAN_ROLE}):
        return await ctx.send(embed=make_embed("no permission", "you need the configured ban role or Administrator."))
    if not bot_can(ctx, "ban_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Ban Members** permission to do that."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot ban member", "The target must be below my highest role and below your highest role."))
    try:
        await member.ban(reason=reason, delete_message_seconds=0)
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("ban failed", "Discord denied the ban. Check my **Ban Members** permission and role hierarchy."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("ban failed", "Discord returned an error while banning that member."))
    await ctx.send(embed=result_embed("Member Banned", "User", fmt_user(member), extra=[("Reason", reason), ("Moderator", ctx.author.mention)]))

@bot.command(aliases=["ub"])
async def unban(ctx, user_id:int):
    if not role_ok(ctx.author, {BAN_ROLE}):
        return await ctx.send(embed=make_embed("no permission", "you need the configured ban role or Administrator."))
    if not bot_can(ctx, "ban_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Ban Members** permission to unban users."))
    try:
        await ctx.guild.unban(discord.Object(id=user_id), reason=f"unbanned by {ctx.author}")
    except discord.NotFound:
        return await ctx.send(embed=make_embed("unban failed", "That user is not currently banned, or the ID is invalid."))
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("unban failed", "Discord denied the action. Check my **Ban Members** permission."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("unban failed", "Discord returned an error while unbanning that user."))
    await ctx.send(embed=result_embed("Member Unbanned", "User ID", f"`{user_id}`", extra=[("Moderator", ctx.author.mention)]))

@bot.command(aliases=["k"])
async def kick(ctx, member:discord.Member,*,reason="no reason provided"):
    if not role_ok(ctx.author, KICK_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured kick role or Administrator."))
    if not bot_can(ctx, "kick_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Kick Members** permission to do that."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot kick member", "The target must be below my highest role and below your highest role."))
    try:
        await member.kick(reason=reason)
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("kick failed", "Discord denied the kick. Check my **Kick Members** permission and role hierarchy."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("kick failed", "Discord returned an error while kicking that member."))
    await ctx.send(embed=result_embed("Member Kicked", "User", fmt_user(member), extra=[("Reason", reason), ("Moderator", ctx.author.mention)]))

@bot.command(aliases=["timeout","to"])
async def mute(ctx,member:discord.Member,minutes:int=10,*,reason="no reason provided"):
    if not role_ok(ctx.author, MUTE_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured mute role or Administrator."))
    if not bot_can(ctx, "moderate_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Moderate Members** permission to mute users."))
    if minutes < 1 or minutes > 40320:
        return await ctx.send(embed=make_embed("invalid duration", "Mute duration must be between **1 minute** and **28 days**."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot mute member", "The target must be below my highest role and below your highest role."))
    try:
        await member.timeout(timedelta(minutes=minutes), reason=reason)
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("mute failed", "Discord denied the timeout. Check my **Moderate Members** permission and role hierarchy."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("mute failed", "Discord returned an error while muting that member."))
    await ctx.send(embed=result_embed("Member Muted", "User", fmt_user(member), extra=[("Duration", f"{minutes} minutes"), ("Reason", reason), ("Moderator", ctx.author.mention)]))

@bot.command(aliases=["um","untimeout"])
async def unmute(ctx,member:discord.Member):
    if not role_ok(ctx.author, MUTE_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured mute role or Administrator."))
    if not bot_can(ctx, "moderate_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Moderate Members** permission to remove timeouts."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot unmute member", "The target must be below my highest role and below your highest role."))
    try:
        await member.timeout(None, reason=f"unmuted by {ctx.author}")
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("unmute failed", "Discord denied the action. Check my **Moderate Members** permission and role hierarchy."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("unmute failed", "Discord returned an error while removing the timeout."))
    await ctx.send(embed=result_embed("Member Unmuted", "User", fmt_user(member), extra=[("Moderator", ctx.author.mention)]))

@bot.command(aliases=["w"])
async def warn(ctx,member:discord.Member,*,reason="no reason provided"):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured warn role or Administrator."))
    if not target_ok(ctx,member):
        return await ctx.send(embed=make_embed("cannot warn member", "You can't warn yourself, the server owner, or someone at/above your role."))
    warning_data[ctx.guild.id][member.id].append(reason)
    await ctx.send(embed=result_embed("Member Warned", "User", fmt_user(member), extra=[("Reason", reason), ("Total Warnings", str(len(warning_data[ctx.guild.id][member.id]))), ("Moderator", ctx.author.mention)]))

@bot.command()
async def warnings(ctx,member:discord.Member=None):
    member=member or ctx.author
    items=warning_data[ctx.guild.id][member.id]
    body="\n".join(f"`{i:02}` **{r}**" for i,r in enumerate(items,1)) or "No warnings recorded."
    await ctx.send(embed=result_embed(f"Warnings · {member.display_name}", "User", fmt_user(member), extra=[("Warnings", body)]))

@bot.command(aliases=["p","clear"])
async def purge(ctx,amount:int=10):
    if not role_ok(ctx.author,PURGE_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured purge role or Administrator."))
    if not bot_can(ctx, "manage_messages"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Manage Messages** permission to purge messages."))
    if amount < 1 or amount > 100:
        return await ctx.send(embed=make_embed("invalid amount", "Choose a number between **1** and **100**."))
    try:
        deleted=await ctx.channel.purge(limit=amount + 1)
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("purge failed", "Discord denied the action. Check my **Manage Messages** and **Read Message History** permissions."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("purge failed", "Discord returned an error while deleting messages."))
    msg=await ctx.send(embed=result_embed("Messages Purged", "Deleted", f"**{max(0,len(deleted)-1)}** messages", extra=[("Moderator", ctx.author.mention)]))
    await asyncio.sleep(3)
    try: await msg.delete()
    except discord.HTTPException: pass

@bot.command(aliases=["l"])
async def lock(ctx):
    # Lock/unlock are intentionally silent for users without moderation access.
    if not role_ok(ctx.author, LOCK_ROLES):
        return
    if not bot_can(ctx, "manage_channels"):
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    except (discord.Forbidden, discord.HTTPException):
        return
    try:
        await ctx.message.add_reaction("🔒")
    except discord.HTTPException:
        pass

@bot.command(aliases=["ul"])
async def unlock(ctx):
    # Lock/unlock are intentionally silent for users without moderation access.
    if not role_ok(ctx.author, LOCK_ROLES):
        return
    if not bot_can(ctx, "manage_channels"):
        return
    try:
        await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
    except (discord.Forbidden, discord.HTTPException):
        return
    try:
        await ctx.message.add_reaction("🔓")
    except discord.HTTPException:
        pass

class SnipeView(discord.ui.View):
    def __init__(self, entries, author_id):
        super().__init__(timeout=120)
        self.entries = entries
        self.index = 0
        self.author_id = author_id
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index == len(self.entries) - 1
        self.page.label = f"Page {self.index + 1}/{len(self.entries)}"

    def embed(self):
        item = self.entries[self.index]
        author = item["author_name"]
        content = item["content"] or "[no text]"
        if len(content) > 1500:
            content = content[:1497] + "..."
        lines = [f"# Sniped Message", "", f"**{author}** · `{item['author_tag']}`", "", content, "", f"**Deleted**\n<t:{int(item['deleted_at'])}:F> · <t:{int(item['deleted_at'])}:R>"]
        if item["attachments"]:
            lines.extend(["", "**Attachments**", *[url for url in item["attachments"][:3]]])
        return make_embed(None, "\n".join(lines), footer=False, timestamp=False)

    async def check_user(self, interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("only the command author or staff can use these buttons.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="‹", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Page 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="›", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_user(interaction):
            return
        self.index += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.embed(), view=self)

@bot.command(aliases=["cs"])
async def clearsnipes(ctx):
    # Only the same moderation roles used by warn/mute/kick/ban can clear snipes.
    if not role_ok(ctx.author, WARN_ROLES | MUTE_ROLES | KICK_ROLES | {BAN_ROLE}):
        return
    if not hasattr(bot, "_snipes"):
        bot._snipes = defaultdict(lambda: deque(maxlen=100))
    bot._snipes[ctx.channel.id].clear()
    try:
        await ctx.message.add_reaction("✅")
    except discord.HTTPException:
        pass

@bot.command(aliases=["s"])
async def snipe(ctx):
    snipes = getattr(bot, "_snipes", {}).get(ctx.channel.id, [])
    now = time.time()
    entries = [x for x in snipes if now - x["deleted_at"] <= 3600]
    if not entries:
        return await ctx.send(embed=make_embed("snipe", "nothing to snipe here from the last hour."))
    # Drop expired entries from the in-memory history.
    try:
        bot._snipes[ctx.channel.id] = deque(entries, maxlen=100)
    except Exception:
        pass
    view = SnipeView(entries, ctx.author.id)
    await ctx.send(embed=view.embed(), view=view)

@bot.command()
async def antinuke(ctx, action="status", value=None):
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission","you need Manage Server."))
    cfg=antinuke_config[ctx.guild.id]; action=action.lower()
    if action=="enable": cfg["enabled"]=True
    elif action=="disable": cfg["enabled"]=False
    elif action=="threshold":
        try: cfg["threshold"]=max(1,min(20,int(value)))
        except: return await ctx.send(embed=make_embed("antinuke","threshold must be a number."))
    elif action=="action":
        if value not in {"ban","kick"}: return await ctx.send(embed=make_embed("antinuke","action must be `ban` or `kick`."))
        cfg["action"]=value
    elif action!="status": return await ctx.send(embed=make_embed("antinuke",f"usage: `{PREFIX}antinuke <enable|disable|status|threshold|action>`"))
    await ctx.send(embed=make_embed("antinuke",f"**enabled:** `{cfg['enabled']}`\n**threshold:** `{cfg['threshold']}` actions / `{cfg['window']}s`\n**action:** `{cfg['action']}`"))

@bot.command()
async def antiraid(ctx, action="status", value=None):
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission","you need Manage Server."))
    cfg=antiraid_config[ctx.guild.id]; action=action.lower()
    if action=="enable": cfg["enabled"]=True
    elif action=="disable": cfg["enabled"]=False
    elif action=="threshold":
        try: cfg["threshold"]=max(2,min(50,int(value)))
        except: return await ctx.send(embed=make_embed("antiraid","threshold must be a number."))
    elif action!="status": return await ctx.send(embed=make_embed("antiraid",f"usage: `{PREFIX}antiraid <enable|disable|status|threshold>`"))
    await ctx.send(embed=make_embed("antiraid",f"**enabled:** `{cfg['enabled']}`\n**threshold:** `{cfg['threshold']}` joins / `{cfg['window']}s`"))

@bot.command()
async def filter(ctx,action="list",*,word=""):
    if action in {"add","remove","clear","on","off"} and not has_manage(ctx): return await ctx.send(embed=make_embed("no permission","you need Manage Server."))
    s=filter_words[ctx.guild.id]
    if action=="add": s.add(word.lower().strip())
    elif action=="remove": s.discard(word.lower().strip())
    elif action=="clear": s.clear()
    elif action=="on": filter_enabled[ctx.guild.id]=True
    elif action=="off": filter_enabled[ctx.guild.id]=False
    elif action!="list": return await ctx.send(embed=make_embed("filter",f"usage: `{PREFIX}filter <add|remove|list|on|off|clear> [word]`"))
    await ctx.send(embed=make_embed("filter",f"**enabled:** `{filter_enabled[ctx.guild.id]}`\n**words:** {', '.join(sorted(s)) or 'none'}"))

@bot.command()
async def security(ctx):
    a=antinuke_config[ctx.guild.id]; r=antiraid_config[ctx.guild.id]; await ctx.send(embed=make_embed("security",f"**antinuke:** `{a['enabled']}` • `{a['threshold']}` / `{a['window']}s` • `{a['action']}`\n**antiraid:** `{r['enabled']}` • `{r['threshold']}` / `{r['window']}s`\n**filter:** `{filter_enabled[ctx.guild.id]}`"))

@bot.command(name="8ball", aliases=["8", "ball"])
async def eightball(ctx, *, question):
    answer = random.choice(["yes.", "no.", "probably.", "maybe.", "ask again later.", "definitely.", "the stars say yes.", "not looking good."])
    await ctx.send(embed=result_embed("8ball", "Question", question, extra=[("Answer", f"**{answer}**")]))

@bot.command()
async def coinflip(ctx):
    result = random.choice(["heads", "tails"])
    await ctx.send(embed=result_embed("Coinflip", "Result", f"**{result}**"))

@bot.command()
async def roll(ctx, sides: int = 6):
    sides = max(2, min(sides, 100000))
    result = random.randint(1, sides)
    await ctx.send(embed=result_embed("Roll", "Result", f"**{result}**", extra=[("Sides", f"`{sides}`")]))

@bot.command()
async def choose(ctx, *, choices):
    options = [x.strip() for x in choices.split("|") if x.strip()]
    if len(options) < 2:
        return await ctx.send(embed=result_embed("Choose", "Usage", f"`{PREFIX}choose option 1 | option 2`"))
    result = random.choice(options)
    await ctx.send(embed=result_embed("Choose", "Selected", f"**{result}**", extra=[("Options", " · ".join(f"`{x}`" for x in options[:10]))]))

@bot.command()
async def rps(ctx, choice):
    choice = choice.lower(); options = ["rock", "paper", "scissors"]
    if choice not in options:
        return await ctx.send(embed=result_embed("Rock Paper Scissors", "Usage", f"`{PREFIX}rps rock|paper|scissors`"))
    botc = random.choice(options)
    result = "tie" if choice == botc else "you win" if (choice, botc) in [("rock", "scissors"), ("paper", "rock"), ("scissors", "paper")] else "you lose"
    await ctx.send(embed=result_embed("Rock Paper Scissors", "Result", f"**{result}**", extra=[("You", choice), ("bleeed", botc)]))

@bot.command()
async def joke(ctx):
    joke_text = random.choice(["why did the computer get cold? it left its windows open.", "I told my PC I needed a break. now it won't stop sending me vacation ads.", "what do you call a sleeping bull? a bulldozer.", "why was the server cold? it left its cache open."])
    await ctx.send(embed=result_embed("Joke", "Joke", joke_text))

@bot.command()
async def fact(ctx):
    fact_text = random.choice(["octopuses have three hearts.", "bananas are botanically berries.", "a day on Venus is longer than its year.", "honey can stay edible for a very long time when stored properly."])
    await ctx.send(embed=result_embed("Fact", "Did you know?", fact_text))

@bot.command()
async def rate(ctx, *, thing):
    score = random.randint(0, 100)
    await ctx.send(embed=result_embed("Rate", "Subject", thing, extra=[("Score", f"**{score}/100**")]))

@bot.command()
async def roast(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Roast", "Target", member.mention, extra=[("Roast", "you're running on the free trial of confidence.")]))

@bot.command()
async def compliment(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Compliment", "Target", member.mention, extra=[("Message", "you're genuinely a great person to have around.")]))

@bot.command()
async def wyr(ctx, *, question):
    await ctx.send(embed=result_embed("Would You Rather", "Question", question))

@bot.command()
async def mock(ctx, *, text):
    mocked = "".join(c.upper() if i % 2 else c.lower() for i, c in enumerate(text))
    await ctx.send(embed=result_embed("Mock", "Result", mocked))

@bot.command()
async def reverse(ctx, *, text):
    await ctx.send(embed=result_embed("Reverse", "Result", text[::-1]))

@bot.command()
async def hug(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Hug", "Action", f"{ctx.author.mention} gave {member.mention} a hug ♡"))

@bot.command()
async def pat(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Pat", "Action", f"{ctx.author.mention} gave {member.mention} a pat ♡"))

@bot.command()
async def slap(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Slap", "Action", f"{ctx.author.mention} bonked {member.mention} (cartoon-style)."))

@bot.command()
async def love(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Love", "Action", f"{ctx.author.mention} sent some love to {member.mention} ♡"))

@bot.command()
async def simp(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Simp Rate", "User", member.mention, extra=[("Score", f"**{random.randint(0,100)}%**")]))

@bot.command()
async def gayrate(ctx, member: discord.Member=None):
    member = member or ctx.author
    await ctx.send(embed=result_embed("Rate", "User", member.mention, extra=[("Score", f"**{random.randint(0,100)}%**")]))

@bot.command()
async def howlucky(ctx):
    await ctx.send(embed=result_embed("Luck", "Today's luck", f"**{random.randint(0,100)}%**"))

@bot.command()
async def ship(ctx, a: discord.Member, b: discord.Member):
    score = random.randint(0,100)
    await ctx.send(embed=result_embed("Ship", "Pair", f"{a.mention} × {b.mention}", extra=[("Compatibility", f"**{score}%**")]))

@bot.command()
async def shipname(ctx, a: discord.Member, b: discord.Member):
    n = (a.display_name[:max(1, len(a.display_name)//2)] + b.display_name[max(1, len(b.display_name)//2):]).replace(" ", "")
    await ctx.send(embed=result_embed("Ship Name", "Pair", f"{a.mention} × {b.mention}", extra=[("Name", f"**{n}**")]))

@bot.command()
async def truth(ctx):
    await ctx.send(embed=result_embed("Truth", "Question", random.choice(["what is a hobby you wish you were better at?", "what is the funniest thing you've seen today?", "what game could you play for hours?"])))

@bot.command()
async def dare(ctx):
    await ctx.send(embed=result_embed("Dare", "Challenge", random.choice(["send a funny emoji in chat.", "change your status for 5 minutes.", "say something nice about the next person who messages you."])))

@bot.command()
async def wouldyou(ctx):
    await ctx.send(embed=result_embed("Would You Rather", "Question", random.choice(["would you rather always have perfect Wi-Fi or perfect battery life?", "would you rather have unlimited games or unlimited snacks?", "would you rather teleport or pause time?"])))

@bot.command(aliases=["afkset"])
async def afk(ctx,*,reason="AFK"): afk_data[ctx.author.id]={"name":str(ctx.author),"reason":reason}; await ctx.send(embed=make_embed("afk",f"{ctx.author.mention} is now AFK: {reason}"))

@bot.command()
async def poll(ctx,*,question):
    msg=await ctx.send(embed=make_embed("poll",question+"\n\n👍 yes\n👎 no")); await msg.add_reaction("👍"); await msg.add_reaction("👎")



def parse_duration(value):
    value = value.lower().strip()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    try:
        amount = float(value[:-1]); unit = value[-1]
        return max(1, int(amount * units[unit]))
    except (ValueError, KeyError, IndexError):
        return None


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("you need Manage Channels to close this ticket.", ephemeral=True)
        await interaction.response.send_message("closing ticket...", ephemeral=True)
        await asyncio.sleep(1)
        await interaction.channel.delete(reason=f"ticket closed by {interaction.user}")


@bot.hybrid_command(name="ticket")
async def ticket(ctx, *, reason="no reason provided"):
    """Create a private support ticket."""
    guild = ctx.guild
    if guild is None:
        return await ctx.send(embed=make_embed("error", "this command can only be used in a server."))
    existing = discord.utils.get(guild.text_channels, name=f"ticket-{ctx.author.id}")
    if existing:
        return await ctx.send(embed=make_embed("ticket", f"you already have a ticket: {existing.mention}"))
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        ctx.author: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True),
    }
    channel = await guild.create_text_channel(f"ticket-{ctx.author.id}", overwrites=overwrites, reason="bleeed ticket")
    tickets[channel.id] = ctx.author.id
    e = make_embed("ticket created", f"welcome {ctx.author.mention}!\n\n**reason:** {reason}\n\nA staff member can help you here.")
    await channel.send(content=ctx.author.mention, embed=e, view=TicketCloseView())
    await ctx.send(embed=make_embed("ticket", f"your ticket has been created: {channel.mention}"))


@bot.hybrid_command(name="close")
@commands.has_permissions(manage_channels=True)
async def close(ctx):
    """Close the current ticket channel."""
    if ctx.channel.id not in tickets and not ctx.channel.name.startswith("ticket-"):
        return await ctx.send(embed=make_embed("ticket", "this is not a ticket channel."))
    await ctx.send(embed=make_embed("ticket closed", "this channel will be deleted in a moment."))
    await asyncio.sleep(2)
    tickets.pop(ctx.channel.id, None)
    await ctx.channel.delete(reason=f"ticket closed by {ctx.author}")


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

    @discord.ui.button(label="Enter", style=discord.ButtonStyle.success, emoji="🎉")
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = giveaways.get(self.giveaway_id)
        if not data or data["ended"]:
            return await interaction.response.send_message("this giveaway has ended.", ephemeral=True)
        data["entries"].add(interaction.user.id)
        await interaction.response.send_message("you entered the giveaway! 🎉", ephemeral=True)


async def finish_giveaway(message_id):
    data = giveaways.get(message_id)
    if not data:
        return
    await asyncio.sleep(data["duration"])
    data["ended"] = True
    entries = list(data["entries"])
    winners = min(data["winners"], len(entries))
    chosen = random.sample(entries, winners) if winners else []
    mentions = ", ".join(f"<@{uid}>" for uid in chosen) if chosen else "no valid entries"
    channel = bot.get_channel(data["channel_id"])
    if channel:
        await channel.send(embed=make_embed("giveaway ended", f"**prize:** {data['prize']}\n**winner(s):** {mentions}"))


@bot.hybrid_command(name="giveaway", aliases=["gaw"])
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, duration: str, winners: int, *, prize: str):
    """Start a button-based giveaway."""
    seconds = parse_duration(duration)
    if seconds is None:
        return await ctx.send(embed=make_embed("giveaway", "duration must look like `30s`, `10m`, `2h`, or `1d`."))
    if winners < 1 or winners > 20:
        return await ctx.send(embed=make_embed("giveaway", "winners must be between 1 and 20."))
    e = make_embed("🎉 giveaway", f"**prize:** {prize}\n**winners:** `{winners}`\n**ends:** <t:{int(time.time()+seconds)}:R>\n\nClick **Enter** to participate!")
    view = GiveawayView(0)
    msg = await ctx.send(embed=e, view=view)
    view.giveaway_id = msg.id
    giveaways[msg.id] = {"channel_id": ctx.channel.id, "duration": seconds, "winners": winners, "prize": prize, "entries": set(), "ended": False}
    bot.loop.create_task(finish_giveaway(msg.id))


@bot.hybrid_command(name="announce")
@commands.has_permissions(manage_guild=True)
async def announce(ctx, *, message):
    """Send a server announcement embed."""
    e = make_embed("📢 announcement", message)
    await ctx.send(embed=e)


@bot.hybrid_command(name="slowmode")
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    """Set channel slowmode."""
    if not 0 <= seconds <= 21600:
        return await ctx.send(embed=make_embed("slowmode", "use a value from 0 to 21600 seconds."))
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(embed=make_embed("slowmode", f"slowmode set to **{seconds}s**."))


@bot.hybrid_command(name="nick")
@commands.has_permissions(manage_nicknames=True)
async def nick(ctx, member: discord.Member, *, nickname: str = None):
    """Change a member nickname."""
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("error", "you can't change that member's nickname."))
    await member.edit(nick=nickname, reason=f"nickname changed by {ctx.author}")
    await ctx.send(embed=make_embed("nickname", f"nickname updated for {member.mention}."))


@bot.hybrid_command(name="addrole")
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, role: discord.Role):
    """Give a role to a member."""
    if role >= ctx.guild.me.top_role or role >= ctx.author.top_role:
        return await ctx.send(embed=make_embed("error", "that role is too high for you or the bot."))
    await member.add_roles(role, reason=f"role added by {ctx.author}")
    await ctx.send(embed=make_embed("role added", f"gave {role.mention} to {member.mention}."))


@bot.hybrid_command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    """Remove a role from a member."""
    if role >= ctx.guild.me.top_role or role >= ctx.author.top_role:
        return await ctx.send(embed=make_embed("error", "that role is too high for you or the bot."))
    await member.remove_roles(role, reason=f"role removed by {ctx.author}")
    await ctx.send(embed=make_embed("role removed", f"removed {role.mention} from {member.mention}."))


@bot.hybrid_command(name="deleterole", aliases=["delrole", "roledelete"], description="Delete a server role.")
@commands.has_permissions(manage_roles=True)
async def deleterole(ctx, role: discord.Role):
    """Delete a role the caller and bot can manage."""
    if role.is_default() or role.managed:
        return await ctx.send(embed=make_embed("delete role", "that role cannot be deleted."))
    if role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("delete role", "my highest role must be above that role."))
    if not ctx.author.guild_permissions.administrator and role >= ctx.author.top_role:
        return await ctx.send(embed=make_embed("delete role", "your highest role must be above that role."))
    role_name = role.name
    role_id = role.id
    try:
        await role.delete(reason=f"role deleted by {ctx.author}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("delete role", "Discord denied deleting that role."))
    await ctx.send(embed=make_embed("role deleted", f"**Name**\n`{role_name}`\n\n**ID**\n`{role_id}`\n\n**Deleted By**\n{ctx.author.mention}"))


def parse_role_changes(raw):
    pattern = re.compile(r"(?i)(name|color|colour|icon|hoist|mentionable)\s*=")
    matches = list(pattern.finditer(raw))
    if not matches:
        return {}
    result = {}
    for i, match in enumerate(matches):
        key = match.group(1).lower()
        key = "color" if key == "colour" else key
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        value = raw[match.end():end].strip().strip('"').strip("'")
        if value:
            result[key] = value
    return result


@bot.hybrid_command(name="changerole", aliases=["editrole", "rolechange"], description="Change a role's settings.")
@commands.has_permissions(manage_roles=True)
async def changerole(ctx, role: discord.Role, *, changes: str):
    """Change role name, color, icon, hoist, or mentionable state."""
    if role.is_default() or role.managed:
        return await ctx.send(embed=make_embed("change role", "that role cannot be edited."))
    if role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("change role", "my highest role must be above that role."))
    if not ctx.author.guild_permissions.administrator and role >= ctx.author.top_role:
        return await ctx.send(embed=make_embed("change role", "your highest role must be above that role."))

    changes_map = parse_role_changes(changes)
    if not changes_map:
        return await ctx.send(embed=make_embed("change role", f"use `{PREFIX}changerole @role name=VIP color=#efcead icon=⭐ hoist=true mentionable=true`"))

    kwargs = {}
    changed = []
    if "name" in changes_map:
        name = changes_map["name"][:100]
        if not name:
            return await ctx.send(embed=make_embed("change role", "the role name cannot be empty."))
        kwargs["name"] = name
        changed.append("name")
    if "color" in changes_map:
        color = parse_color(changes_map["color"])
        if color is None:
            return await ctx.send(embed=make_embed("change role", "color must look like `#efcead` or `efcead`."))
        kwargs["color"] = color
        changed.append("color")
    for key in ("hoist", "mentionable"):
        if key in changes_map:
            value = changes_map[key].lower()
            if value not in {"true", "false", "yes", "no", "on", "off"}:
                return await ctx.send(embed=make_embed("change role", f"`{key}` must be `true` or `false`."))
            kwargs[key] = value in {"true", "yes", "on"}
            changed.append(key)
    if "icon" in changes_map:
        icon_value = changes_map["icon"]
        if icon_value.lower() in {"none", "remove", "off"}:
            kwargs["display_icon"] = None
        elif re.match(r"^https?://", icon_value, re.I):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(icon_value, timeout=10) as resp:
                        if resp.status != 200:
                            return await ctx.send(embed=make_embed("change role", "i couldn't download that icon."))
                        icon_bytes = await resp.read()
                if len(icon_bytes) > 256 * 1024:
                    return await ctx.send(embed=make_embed("change role", "that icon file is too large."))
                kwargs["display_icon"] = icon_bytes
            except Exception:
                return await ctx.send(embed=make_embed("change role", "i couldn't download that icon."))
        else:
            kwargs["display_icon"] = icon_value
        changed.append("icon")

    try:
        edited = await role.edit(**kwargs, reason=f"role changed by {ctx.author}")
    except ValueError as exc:
        return await ctx.send(embed=make_embed("change role", f"invalid role setting: `{exc}`"))
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("change role", "Discord denied editing that role. Check role hierarchy and whether this server supports role icons."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("change role", "Discord couldn't edit that role."))

    await ctx.send(embed=make_embed(
        "role changed",
        f"**Role**\n{edited.mention} · `{edited.id}`\n\n**Changed**\n`{', '.join(changed)}`\n\n**Changed By**\n{ctx.author.mention}"
    ))


@bot.hybrid_group(name="vanity", invoke_without_command=True, description="Configure the /bleeed custom-status role and embed.")
@commands.has_permissions(manage_roles=True)
async def vanity(ctx, target: str = None):
    cfg = vanity_config[ctx.guild.id]
    raw = (target or "").strip()
    lowered = raw.lower()

    if lowered in {"off", "disable", "remove"}:
        cfg["enabled"] = False
        cfg["role"] = None
        save_vanity_config()
        return await ctx.send(embed=make_embed("vanity disabled", "the `/bleeed` status role is disabled."))

    if lowered in {"status", "settings"}:
        configured = ctx.guild.get_role(cfg.get("role")) if cfg.get("role") else None
        return await ctx.send(embed=make_embed(
            "vanity settings",
            f"**Trigger**\n`/bleeed`\n\n**Role**\n{configured.mention if configured else 'not configured'}\n\n"
            f"**Enabled**\n`{'yes' if cfg.get('enabled') and configured else 'no'}`\n\n"
            f"**Title**\n{cfg.get('title', 'Vanity Unlocked!')}\n\n"
            f"**Description**\n{cfg.get('description', '')}\n\n"
            f"**Color**\n`{cfg.get('color', '#000001')}`"
        ))

    if not raw:
        return await ctx.send(embed=make_embed(
            "vanity",
            f"`{PREFIX}vanity @role` — set the role\n"
            f"`{PREFIX}vanity title <text>` — edit title\n"
            f"`{PREFIX}vanity description <text>` — edit description\n"
            f"`{PREFIX}vanity color #hex` — edit color\n"
            f"`{PREFIX}vanity image <url>` — edit image\n"
            f"`{PREFIX}vanity thumbnail user` — use the member avatar\n"
            f"`{PREFIX}vanity preview` — preview the embed\n"
            f"`{PREFIX}vanity settings` — view settings\n"
            f"`{PREFIX}vanity reset` — reset embed settings\n"
            f"`{PREFIX}vanity off` — disable vanity"
        ))

    role = None
    message_obj = getattr(ctx, "message", None)
    if message_obj is not None and getattr(message_obj, "role_mentions", None):
        role = message_obj.role_mentions[0]
    if role is None:
        match = re.fullmatch(r"<@&(\d+)>", raw)
        if match:
            role = ctx.guild.get_role(int(match.group(1)))
    if role is None and raw.isdigit():
        role = ctx.guild.get_role(int(raw))
    if role is None:
        role = discord.utils.find(lambda r: r.name.lower() == raw.lower(), ctx.guild.roles)

    if role is None:
        return await ctx.send(embed=make_embed("vanity", "i couldn't find that role. mention it, use its ID, or use its exact name."))
    if role.is_default() or role.managed or role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("vanity", "that role must be a normal role below my highest role."))

    cfg["enabled"] = True
    cfg["role"] = role.id
    save_vanity_config()
    return await ctx.send(embed=make_embed(
        "vanity enabled",
        f"members with `/bleeed` in their custom status will receive {role.mention}.\n\nremove `/bleeed` from their status and bleeed will remove the role."
    ))

@vanity.command(name="title")
async def vanity_title(ctx, *, text: str):
    vanity_config[ctx.guild.id]["title"] = text
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity title updated", f"**Title**\n{text}"))

@vanity.command(name="description")
async def vanity_description(ctx, *, text: str):
    vanity_config[ctx.guild.id]["description"] = text
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity description updated", f"**Description**\n{text}"))

@vanity.command(name="color")
async def vanity_color(ctx, color: str):
    value = color.strip().replace("#", "")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return await ctx.send(embed=make_embed("vanity", "use a 6-digit hex color such as `#efcead`."))
    vanity_config[ctx.guild.id]["color"] = f"#{value.lower()}"
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity color updated", f"**Color**\n`#{value.lower()}`"))

@vanity.command(name="image")
async def vanity_image(ctx, url: str):
    if url.lower() in {"off", "none", "remove"}:
        vanity_config[ctx.guild.id]["image"] = None
        save_vanity_config()
        return await ctx.send(embed=make_embed("vanity image removed", "the vanity embed image has been removed."))
    vanity_config[ctx.guild.id]["image"] = url
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity image updated", url))

@vanity.command(name="thumbnail")
async def vanity_thumbnail(ctx, value: str = "user"):
    if value.lower() in {"off", "none", "remove"}:
        vanity_config[ctx.guild.id]["thumbnail"] = None
    elif value.lower() == "user":
        vanity_config[ctx.guild.id]["thumbnail"] = "{user_avatar}"
    else:
        vanity_config[ctx.guild.id]["thumbnail"] = value
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity thumbnail updated", f"**Thumbnail**\n{value}"))

@vanity.command(name="preview")
async def vanity_preview(ctx):
    member = ctx.author
    role = ctx.guild.get_role(vanity_config[ctx.guild.id].get("role")) if vanity_config[ctx.guild.id].get("role") else None
    if not role:
        return await ctx.send(embed=make_embed("vanity preview", "set a vanity role first with `,vanity @role`."))
    await ctx.send(embed=build_vanity_embed(member))

@vanity.command(name="reset")
async def vanity_reset(ctx):
    cfg = vanity_config[ctx.guild.id]
    cfg.update({
        "title": "Vanity Unlocked!",
        "description": "{user} has `/bleeed` in their status and received {role}!",
        "color": "#000001",
        "image": None,
        "thumbnail": "{user_avatar}",
    })
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity reset", "the vanity embed has been restored to its defaults."))

@bot.hybrid_group(name="create", invoke_without_command=True)
async def create(ctx):
    """Create a server role, text channel, or voice channel."""
    await ctx.send(embed=make_embed(
        "create",
        f"**server setup**\n\n"
        f"`{PREFIX}create role <name>` — create a role\n"
        f"`{PREFIX}create channel <name>` — create a text channel\n"
        f"`{PREFIX}create vc <name>` — create a voice channel\n\n"
        f"Slash commands: `/create role`, `/create channel`, `/create vc`"
    ))


@create.command(name="role")
@commands.has_permissions(manage_roles=True)
async def create_role(ctx, *, name: str):
    """Create a new server role."""
    name = name.strip()
    if not name:
        return await ctx.send(embed=make_embed("create role", "role name cannot be empty."))
    if len(name) > 100:
        return await ctx.send(embed=make_embed("create role", "role names can be up to 100 characters."))
    role = await ctx.guild.create_role(name=name, reason=f"role created by {ctx.author}")
    e = make_embed(
        "role created",
        f"**name:** {role.mention}\n**id:** `{role.id}`\n**created by:** {ctx.author.mention}"
    )
    if ctx.guild.icon:
        e.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=e)


@create.command(name="channel")
@commands.has_permissions(manage_channels=True)
async def create_channel(ctx, *, name: str):
    """Create a new text channel."""
    name = name.strip()
    if not name:
        return await ctx.send(embed=make_embed("create channel", "channel name cannot be empty."))
    if len(name) > 100:
        return await ctx.send(embed=make_embed("create channel", "channel names can be up to 100 characters."))
    channel = await ctx.guild.create_text_channel(name, reason=f"channel created by {ctx.author}")
    e = make_embed(
        "channel created",
        f"**channel:** {channel.mention}\n**id:** `{channel.id}`\n**created by:** {ctx.author.mention}"
    )
    await ctx.send(embed=e)


@create.command(name="vc", aliases=["voice"])
@commands.has_permissions(manage_channels=True)
async def create_vc(ctx, *, name: str):
    """Create a new voice channel."""
    name = name.strip()
    if not name:
        return await ctx.send(embed=make_embed("create voice", "voice channel name cannot be empty."))
    if len(name) > 100:
        return await ctx.send(embed=make_embed("create voice", "channel names can be up to 100 characters."))
    channel = await ctx.guild.create_voice_channel(name, reason=f"voice channel created by {ctx.author}")
    e = make_embed(
        "voice channel created",
        f"**channel:** {channel.mention}\n**id:** `{channel.id}`\n**created by:** {ctx.author.mention}"
    )
    await ctx.send(embed=e)


@bot.hybrid_command(name="remind")
async def remind(ctx, duration: str, *, message: str):
    """Create a personal reminder."""
    seconds = parse_duration(duration)
    if seconds is None:
        return await ctx.send(embed=make_embed("reminder", "duration must look like `30s`, `10m`, `2h`, or `1d`."))
    await ctx.send(embed=make_embed("reminder set", f"I'll remind you <t:{int(time.time()+seconds)}:R>."))
    await asyncio.sleep(seconds)
    try:
        await ctx.author.send(embed=make_embed("⏰ reminder", message))
    except discord.HTTPException:
        await ctx.channel.send(ctx.author.mention, embed=make_embed("⏰ reminder", message))

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(embed=make_embed("missing argument", f"Use `{PREFIX}help {ctx.command.qualified_name}` for the correct syntax."))
    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=make_embed("invalid argument", f"I couldn't find that member, role, channel, or number. Use `{PREFIX}help {ctx.command.qualified_name}`."))
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send(embed=make_embed("no permission", "You don't have the Discord permission required for this command."))
    if isinstance(error, commands.BotMissingPermissions):
        return await ctx.send(embed=make_embed("bot permission missing", "I don't have the Discord permission required for this command."))
    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(embed=make_embed("slow down", f"Try again <t:{int(time.time()+error.retry_after)}:R>."))
    if isinstance(error, commands.CommandInvokeError):
        original=error.original
        print(f"Command error in {ctx.command}: {original!r}")
        if isinstance(original, discord.Forbidden):
            return await ctx.send(embed=make_embed("discord denied the action", "Check my permissions and make sure my bot role is high enough."))
        return await ctx.send(embed=make_embed("command failed", "Something went wrong while running that command. Check the console for details."))
    print(f"Unhandled command error in {ctx.command}: {error!r}")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

bot.run(TOKEN)
