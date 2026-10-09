import os, time, random, asyncio, json, re, io
import aiohttp
from collections import defaultdict, deque
from datetime import timedelta, datetime, timezone
import discord
from discord.ext import commands

PREFIX = ","
COLOR = 0x000001
TOKEN = os.getenv("DISCORD_TOKEN")
BOT_OWNER_ID = 1401864973923389465

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
v53_message_times = defaultdict(lambda: deque(maxlen=20))
warning_data = defaultdict(lambda: defaultdict(list))
modlog_data = defaultdict(lambda: defaultdict(list))
quarantine_data = defaultdict(dict)
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
BOOSTER_CONFIG_FILE = "booster_config.json"
BR_CONFIG_FILE = "br_config.json"
BR_BASE_CONFIG_FILE = "br_base_config.json"
BR_PERMISSION_ROLE = 1555248843493220463
BR_OVERRIDE_FILE = "br_overrides.json"
MODLOG_FILE = "modlogs.json"
QUARANTINE_FILE = "quarantine.json"
vanity_config = defaultdict(lambda: {
    "enabled": False,
    "role": None,
    "channel": None,
    "title": "Vanity Unlocked!",
    "description": "{user} has `/bleeed` in their status and received {role}!",
    "color": "#000001",
    "image": None,
    "thumbnail": "{user_avatar}",
})
AUTOROLE_CONFIG_FILE = "autorole_config.json"
AUTOREACT_CONFIG_FILE = "autoreact_config.json"

def _load_json_config(path, default=None):
    """Load a JSON config file safely, returning default when it is missing/invalid."""
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return default

def _save_json_file(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError as exc:
        print(f"config save failed for {path}: {exc}")

def load_modlogs():
    global modlog_data
    raw = _load_json_config(MODLOG_FILE, {})
    modlog_data = defaultdict(lambda: defaultdict(list))
    for gid, users in (raw or {}).items():
        try:
            modlog_data[int(gid)] = defaultdict(list, {int(uid): list(entries or []) for uid, entries in (users or {}).items()})
        except (TypeError, ValueError):
            continue

def save_modlogs():
    _save_json_file(MODLOG_FILE, {str(gid): {str(uid): list(entries) for uid, entries in users.items()} for gid, users in modlog_data.items() if users})

def load_quarantine():
    global quarantine_data
    raw = _load_json_config(QUARANTINE_FILE, {})
    quarantine_data = defaultdict(dict)
    for gid, users in (raw or {}).items():
        try:
            quarantine_data[int(gid)] = {int(uid): list(role_ids or []) for uid, role_ids in (users or {}).items()}
        except (TypeError, ValueError):
            continue

def save_quarantine():
    _save_json_file(QUARANTINE_FILE, {str(gid): {str(uid): list(role_ids) for uid, role_ids in users.items()} for gid, users in quarantine_data.items() if users})

def record_modlog(guild, member_or_id, action, moderator, reason="No reason provided", **extra):
    uid = member_or_id.id if hasattr(member_or_id, "id") else int(member_or_id)
    entry = {
        "case_id": f"{int(time.time())}-{len(modlog_data[guild.id][uid]) + 1}",
        "action": action,
        "moderator_id": moderator.id if hasattr(moderator, "id") else int(moderator),
        "reason": reason or "No reason provided",
        "timestamp": int(time.time()),
    }
    entry.update(extra)
    modlog_data[guild.id][uid].append(entry)
    modlog_data[guild.id][uid] = modlog_data[guild.id][uid][-100:]
    save_modlogs()

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
booster_config = defaultdict(lambda: {
    "enabled": True,
    "channel": None,
    "title": "Thank you for boosting!",
    "description": "{user} just boosted **{server}**! Thank you for supporting the server.",
    "color": "#000001",
    "image": None,
    "thumbnail": "{user_avatar}",
})
br_config = defaultdict(dict)
br_base_config = defaultdict(lambda: None)
br_color_pairs = defaultdict(dict)
br_overrides = defaultdict(set)
BR_COLOR_PAIRS_FILE = "br_color_pairs.json"

def load_br_color_pairs():
    global br_color_pairs
    data = _load_json_config(BR_COLOR_PAIRS_FILE, {})
    br_color_pairs = defaultdict(dict)
    for gid, users in data.items():
        br_color_pairs[str(gid)] = {str(uid): colors for uid, colors in (users or {}).items()}

def save_br_color_pairs():
    _save_json_file(BR_COLOR_PAIRS_FILE, {str(gid): dict(users) for gid, users in br_color_pairs.items()})

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

def load_booster_config():
    try:
        with open(BOOSTER_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, cfg in raw.items():
            base = dict(booster_config[int(gid)])
            base.update(cfg or {})
            booster_config[int(gid)] = base
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        pass

def save_booster_config():
    _save_json_file(BOOSTER_CONFIG_FILE, {str(k): dict(v) for k, v in booster_config.items()})

def load_br_config():
    try:
        with open(BR_CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for gid, users in raw.items():
            br_config[int(gid)] = {int(uid): int(rid) for uid, rid in (users or {}).items()}
    except (FileNotFoundError, json.JSONDecodeError, ValueError, TypeError):
        pass

def save_br_config():
    _save_json_file(BR_CONFIG_FILE, {str(gid): {str(uid): rid for uid, rid in users.items()} for gid, users in br_config.items()})


def load_br_overrides():
    global br_overrides
    data = _load_json_config(BR_OVERRIDE_FILE, {})
    br_overrides = defaultdict(set)
    for gid, users in (data or {}).items():
        try:
            br_overrides[int(gid)] = {int(uid) for uid in (users or [])}
        except (TypeError, ValueError):
            continue

def save_br_overrides():
    _save_json_file(BR_OVERRIDE_FILE, {str(gid): sorted(users) for gid, users in br_overrides.items() if users})

def has_br_access(member):
    return (member.guild_permissions.administrator
            or any(r.id == BR_PERMISSION_ROLE for r in member.roles)
            or member.id in br_overrides.get(member.guild.id, set()))

def _is_custom_emoji(value):
    try:
        emoji = discord.PartialEmoji.from_str(value.strip())
        return emoji if emoji.id else None
    except Exception:
        return None

async def br_icon_bytes_from_custom_emoji(emoji):
    """Download a Discord custom emoji and turn animated GIFs into a static PNG."""
    url = str(emoji.url)
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                return None
            raw = await resp.read()
    if len(raw) > 10 * 1024 * 1024:
        return None
    try:
        from PIL import Image
        image = Image.open(io.BytesIO(raw))
        image.seek(0)
        image = image.convert("RGBA")
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None

def load_br_base_config():
    global br_base_config
    data = _load_json_config(BR_BASE_CONFIG_FILE, {})
    br_base_config = defaultdict(lambda: None)
    for gid, rid in (data or {}).items():
        try:
            br_base_config[int(gid)] = int(rid)
        except (TypeError, ValueError):
            continue

def save_br_base_config():
    _save_json_file(BR_BASE_CONFIG_FILE, {str(gid): rid for gid, rid in br_base_config.items() if rid})

def booster_replace(text, member, role=None):
    if text is None:
        return None
    replacements = {
        "{user}": member.mention, "{mention}": member.mention,
        "{username}": member.name, "{displayname}": member.display_name,
        "{server}": member.guild.name, "{membercount}": str(member.guild.member_count or len(member.guild.members)),
        "{id}": str(member.id), "{user_id}": str(member.id),
        "{role}": role.mention if role else "", "{role_name}": role.name if role else "",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

def build_booster_embed(member):
    cfg = booster_config[member.guild.id]
    color = parse_color(cfg.get("color", "#000001")) or COLOR
    e = discord.Embed(title=booster_replace(cfg.get("title"), member), description=booster_replace(cfg.get("description"), member), color=color)
    if cfg.get("image"):
        e.set_image(url=booster_replace(cfg["image"], member))
    if cfg.get("thumbnail"):
        thumb = member.display_avatar.url if cfg["thumbnail"] == "{user_avatar}" else booster_replace(cfg["thumbnail"], member)
        e.set_thumbnail(url=thumb)
    return e

load_booster_config()
load_br_config()
load_br_base_config()
load_br_color_pairs()
load_br_overrides()
load_modlogs()
load_quarantine()



def make_embed(title=None, description=None, *, footer=False, timestamp=False, ctx=None, icon=False):
    """Consistent compact directory-style embed system inspired by modern Discord bot UIs."""
    e = discord.Embed(color=COLOR)
    if title:
        heading = f"# {title}"
        e.description = heading if not description else f"{heading}\n{description}"
    elif description:
        e.description = description
    return e


def directory_embed(title, subtitle=None, *, ctx=None):
    e = discord.Embed(color=COLOR)
    lines = [f"# {title}"]
    if subtitle:
        lines.append(subtitle)
    e.description = "\n".join(lines)
    if ctx and getattr(ctx.guild, "icon", None):
        e.set_thumbnail(url=ctx.guild.icon.url)
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



def action_embed(message, *, added=False, removed=False):
    """Compact Discord-style action response used for successful add/remove actions."""
    if added:
        icon = "<:add:1557785192712642634>"
    elif removed:
        icon = "<:remove:1557785190183600258>"
    else:
        icon = ""
    return discord.Embed(description=f"{icon} {message}".strip(), color=COLOR)


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
    "servers": ("Show every server bleeed is in and let the bot owner make it leave a server.", "servers", "servers", ["guilds"]),
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
    "br": ("Create, customize, share, and manage Booster Roles.", "br <create|name|color|colour|icon|share|delete|list|base|override> [value]", "br create VIP", []),
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
    "modlogs": ("View a member's moderation history.", "modlogs <member>", "modlogs @user", ["modlog"]),
    "quarantine": ("Quarantine a member and temporarily restrict their roles.", "quarantine <member> [reason]", "quarantine @user raiding", ["q"]) ,
    "unquarantine": ("Remove quarantine and restore saved roles.", "unquarantine <member>", "unquarantine @user", ["unq"]),
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
    "compliment": ("Give a friendly compliment.", "compliment [member]", "compliment @user", []),
    "wyr": ("Ask a would-you-rather question.", "wyr <question>", "wyr cats or dogs?", []),
    "mock": ("Convert text into alternating-case mock text.", "mock <text>", "mock skill issue", []),
    "reverse": ("Reverse text.", "reverse <text>", "reverse hello", []),
    "hug": ("Give someone a virtual hug.", "hug [member]", "hug @user", []),
    "pat": ("Give someone a virtual pat.", "pat [member]", "pat @user", []),
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
    "role": ("Give a role to a member.", "role <member> <role>", "role @user @VIP", ["r"]),
    "removerole": ("Remove a role from a member.", "removerole <member> <role>", "removerole @user @VIP", []),
    "vanity": ("Configure the /bleeed status role and its customizable embed.", "vanity [role|channel|title|description|color|image|thumbnail|preview|settings|reset|off]", "vanity channel #vanity", []),
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
    "id": ("Show a user's Discord ID.", "id [member]", "id @user", ["uid"]),
    "joined": ("Show when a member joined the server.", "joined [member]", "joined @user", ["joinedat"]),
    "created": ("Show when a Discord account was created.", "created [member]", "created @user", ["createdat"]),
    "randomnumber": ("Pick a random integer in a range.", "randomnumber [minimum] [maximum]", "randomnumber 1 100", ["rand"]),
})

COMMAND_INFO.update({
    "settings": ("View and manage the server's main bleeed configuration.", "settings [view|set|reset] ...", "settings", ["cfg"]),
    "joinlog": ("Log new members into a dedicated channel.", "joinlog [channel]", "joinlog #logs", ["joinlogs"]),
    "leavelog": ("Log members leaving the server.", "leavelog [channel]", "leavelog #logs", ["leavelogs"]),
    "auditlog": ("Set the channel for automated event and security logs.", "auditlog [channel]", "auditlog #logs", ["auditlogs"]),
    "logconfig": ("View or configure join, leave, and audit logging.", "logconfig <join|leave|audit> #channel", "logconfig audit #logs", ["modconfig"]),
    "goodbye": ("Configure a customizable member-leave message.", "goodbye <on|off|channel|message|status>", "goodbye message goodbye {username}", ["leave"]),
    "gallery": ("Make channels accept image/attachment posts only.", "gallery <add|remove|list> [channel]", "gallery add #media", []),
    "protection": ("Toggle lightweight link, caps, spam, and mention protection.", "protection <on|off> <links|caps|spam|mentions>", "protection on links", ["automod"]),
    "alias": ("Create guild-local shortcuts for existing commands.", "alias <add|remove|list|reset> ...", "alias add si serverinfo", ["aliasadd"]),
    "commandtoggle": ("Disable or enable a command in the current channel.", "commandtoggle <on|off|list> <command>", "commandtoggle off giveaway", ["disabled"]),
    "count": ("Count members or members holding a role.", "count [role]", "count @Members", []),
    "rolelist": ("Show a compact role/member-count overview.", "rolelist", "rolelist", ["toproles"]),
    "channelstatsall": ("Show counts of the server's channel types.", "channelstatsall", "channelstatsall", ["channels"]),
    "memberstats": ("Show human, bot, and presence statistics.", "memberstats", "memberstats", ["memberstats"]),
    "usersearch": ("Look up a user by Discord ID.", "usersearch <user_id>", "usersearch 123456789", ["userinfoid"]),
    "settopic": ("Set or view the current channel topic.", "settopic [topic]", "settopic weekly discussion", ["topicset"]),
    "clone": ("Clone the current or selected channel.", "clone [channel] [name]", "clone #general general-copy", []),
    "massrole": ("Add or remove a role from non-bot members.", "massrole <add|remove> @role", "massrole add @Member", ["rmrole"]),
    "timer": ("Set a reminder and receive it by DM.", "timer <duration> [message]", "timer 30m check the event", ["remindme"]),
    "embed": ("Send a clean bleeed-styled embed from text.", "embed <text>", "embed server rules are here", ["sayembed"]),
    "cleanbots": ("Remove recent bot messages from the current channel.", "cleanbots [amount]", "cleanbots 50", ["purgebots"]),
    "invitecheck": ("List server invites and their usage.", "invitecheck", "invitecheck", ["invites"]),
})


COMMAND_INFO.update({
    "memberinfo": ("Show detailed member information.", "memberinfo [member]", "memberinfo @user", []),
    "categorylist": ("List server categories and channel counts.", "categorylist", "categorylist", []),
    "threadlist": ("List active server threads.", "threadlist", "threadlist", []),
    "forumchannels": ("List server forum channels.", "forumchannels", "forumchannels", []),
    "serverfeatures": ("Show enabled Discord server features.", "serverfeatures", "serverfeatures", []),
    "boosters": ("List current server boosters.", "boosters", "boosters", []),
    "serverroles": ("List server roles with member counts.", "serverroles", "serverroles", []),
    "memberpermissions": ("Show a member's permissions.", "memberpermissions [member]", "memberpermissions @user", []),
    "rename": ("Rename the server.", "rename <name>", "rename My Server", []),
    "slowmodeall": ("Set slowmode across all manageable text channels.", "slowmodeall [seconds]", "slowmodeall 5", []),
    "lockall": ("Lock all manageable text channels.", "lockall", "lockall", []),
    "unlockall": ("Unlock all manageable text channels.", "unlockall", "unlockall", []),
    "modstats": ("Show a member's moderation statistics.", "modstats [member]", "modstats @user", []),
    "modrecent": ("Show the latest moderation cases in the server.", "modrecent [amount]", "modrecent 10", []),
    "deafen": ("Server-deafen a member in voice.", "deafen <member> [reason]", "deafen @user disruptive", []),
    "undeafen": ("Remove a server deafen.", "undeafen <member>", "undeafen @user", []),
    "voicekick": ("Disconnect a member from voice.", "voicekick <member> [reason]", "voicekick @user disruptive", []),
    "warnlist": ("Show members with the most warnings.", "warnlist [amount]", "warnlist 10", []),
    "raidmode": ("Quickly enable or disable raid protection.", "raidmode <on|off|status>", "raidmode on", []),
    "antinukewindow": ("Set the antinuke detection window.", "antinukewindow [seconds]", "antinukewindow 15", []),
    "antiraidwindow": ("Set the antiraid join window.", "antiraidwindow [seconds]", "antiraidwindow 15", []),
    "antinukestatus": ("Show detailed antinuke settings.", "antinukestatus", "antinukestatus", []),
    "antiraidstatus": ("Show detailed antiraid settings.", "antiraidstatus", "antiraidstatus", []),
    "securityreset": ("Reset antinuke, antiraid, and word-filter settings.", "securityreset", "securityreset", []),
})

CATEGORIES = [
    ("Information", ["help", "commands", "servers", "ping", "uptime", "avatar", "banner", "botinfo", "userinfo", "serverinfo", "channelinfo", "roleinfo", "membercount", "roles", "emojis", "stickers", "permissions", "guildicon", "servericon", "boost", "serverstats", "firstmessage", "invites", "inviteinfo", "voiceinfo", "id", "joined", "created"]),
    ("Server", ["welcome", "disablewelcome", "booster", "boosterremove", "ar", "autorole", "autoreact", "poll", "ticket", "close", "giveaway", "gaw", "announce", "remind", "vanity"]),
    ("Roles", ["role", "removerole", "deleterole", "changerole", "create", "create role", "create channel", "create vc", "br"]),
    ("Security", ["antinuke", "antiraid", "filter", "security"]),
    ("Moderation", ["ban", "unban", "kick", "mute", "unmute", "warn", "warnings", "unwarn", "clearwarnings", "purge", "lock", "unlock", "snipe", "slowmode", "nick", "topic", "say"]),
    ("Fun", ["8ball", "coinflip", "roll", "choose", "rps", "joke", "fact", "rate", "wyr", "mock", "reverse", "truth", "dare", "wouldyou"]),
    ("Social", ["hug", "pat", "love", "simp", "gayrate", "howlucky", "ship", "shipname", "compliment"]),
    ("Utility", ["afk", "randomnumber"]),
]

# V53 command-browser categories.
CATEGORIES.extend([
    ("Management", ["settings", "joinlog", "leavelog", "auditlog", "logconfig", "goodbye", "gallery", "protection", "alias", "commandtoggle", "count", "rolelist", "channelstatsall", "memberstats", "usersearch", "settopic", "clone", "massrole"]),
    ("Utility Plus", ["timer", "embed", "cleanbots", "invitecheck"]),
])


def command_text(name):
    return f"`{name}`"


def build_pages():
    """Build dense, predictable command-directory pages similar in structure to modern bot browsers."""
    lookup = dict(CATEGORIES)
    page_groups = [
        ["Information"],
        ["Server", "Management"],
        ["Roles", "Role Management", "Role Subcommands", "Security"],
        ["Moderation", "Moderation Tools", "Additional Moderation", "Moderation Subcommands", "Purge Subcommands", "Nuke Subcommands", "Threads", "Channel Management", "Server Tools", "Case and Note Tools", "Remaining Supplied Commands", "More Purge Commands", "More Server Commands"],
        ["Fun", "Social", "Utility", "Utility Plus"],
        ["Owner"],
    ]
    used = set()
    pages = []
    for group in page_groups:
        blocks = []
        for title in group:
            names = [name for name in lookup.get(title, []) if name in COMMAND_INFO and name not in used]
            used.update(names)
            if names:
                blocks.append(f"# {title}\n" + "  ·  ".join(f"`{name}`" for name in names))
        if blocks:
            pages.append("\n\n".join(blocks))

    leftovers = [name for name in COMMAND_INFO if name not in used]
    if leftovers:
        pages.append("# More\n" + "  ·  ".join(f"`{name}`" for name in leftovers))
    return pages


class ServerLeaveConfirmView(discord.ui.View):
    def __init__(self, owner_id, guild):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        self.guild_id = guild.id
        self.guild_name = guild.name

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("only the bot owner can use this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Leave server", style=discord.ButtonStyle.danger)
    async def leave(self, interaction, button):
        guild = bot.get_guild(self.guild_id)
        if guild is None:
            return await interaction.response.edit_message(content="that server is no longer available.", embed=None, view=None)
        try:
            await guild.leave()
        except discord.HTTPException as exc:
            return await interaction.response.send_message(f"i couldn't leave **{self.guild_name}**: `{exc}`", ephemeral=True)
        await interaction.response.edit_message(
            content=f"left **{self.guild_name}** (`{self.guild_id}`).",
            embed=None,
            view=None,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="cancelled.", embed=None, view=None)


class ServerListView(discord.ui.View):
    def __init__(self, owner_id, guilds):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.guilds = list(guilds)
        self.index = 0
        self.message = None
        self.per_page = 10
        self.refresh()

    @property
    def pages(self):
        return max(1, (len(self.guilds) + self.per_page - 1) // self.per_page)

    def refresh(self):
        self.previous.disabled = self.index <= 0
        self.next.disabled = self.index >= self.pages - 1
        self.page.label = f"{self.index + 1}/{self.pages}"
        self.server_select.options = [
            discord.SelectOption(
                label=guild.name[:100],
                value=str(guild.id),
                description=f"ID: {guild.id}"[:100],
            )
            for guild in self.guilds[self.index * self.per_page:(self.index + 1) * self.per_page]
        ]

    def embed(self):
        current = self.guilds[self.index * self.per_page:(self.index + 1) * self.per_page]
        lines = [
            f"`{i:02}` **{guild.name}** · `{guild.id}` · `{guild.member_count or 0}` members"
            for i, guild in enumerate(current, start=self.index * self.per_page + 1)
        ]
        description = "\n".join(lines) if lines else "bleeed isn't in any servers."
        return make_embed("Bot Servers", f"**Servers:** `{len(self.guilds)}`\n\n{description}\n\n-# Select a server below to leave it.")

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("only the bot owner can use this.", ephemeral=True)
            return False
        return True

    @discord.ui.select(placeholder="Choose a server to leave", min_values=1, max_values=1, options=[discord.SelectOption(label="Loading...")])
    async def server_select(self, interaction, select):
        guild_id = int(select.values[0])
        guild = bot.get_guild(guild_id)
        if guild is None:
            return await interaction.response.send_message("that server is no longer available.", ephemeral=True)
        embed = make_embed(
            "Leave Server?",
            f"**{guild.name}**\n`{guild.id}`\n\nAre you sure you want Bleed to leave this server?",
        )
        await interaction.response.edit_message(embed=embed, view=ServerLeaveConfirmView(self.owner_id, guild))

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction, button):
        self.index -= 1
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True, row=1)
    async def page(self, interaction, button):
        pass

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction, button):
        self.index += 1
        self.refresh()
        await interaction.response.edit_message(embed=self.embed(), view=self)

class CommandsView(discord.ui.View):
    """Compact command directory with buttons that expire after one minute."""
    def __init__(self, pages, author_id):
        super().__init__(timeout=60)
        self.pages = pages
        self.index = 0
        self.author_id = author_id
        self.message = None
        self.update_buttons()

    def update_buttons(self):
        self.previous.disabled = self.index <= 0
        self.next.disabled = self.index >= len(self.pages) - 1
        self.page.label = f"{self.index + 1}/{len(self.pages)}"

    def embed(self):
        page = self.pages[self.index]
        e = directory_embed("commands")
        # Render each category as a compact field, matching the directory/card
        # hierarchy of the reference site while staying native to Discord.
        blocks = page.split("\n\n")
        total = 0
        for block in blocks:
            lines = block.splitlines()
            if not lines:
                continue
            category = lines[0].lstrip("# ").strip()
            command_line = " ".join(lines[1:]).strip()
            names = [x.strip() for x in command_line.split("·") if x.strip()]
            total += len(names)
            if names:
                e.add_field(name=f"**{category}** · `{len(names)}`", value=" · ".join(names), inline=False)
        e.description += (
            f"\n\n**prefix** `{PREFIX}`  **search** `{PREFIX}help <command>`"
            f"\n-# page {self.index + 1}/{len(self.pages)} · {total} commands"
        )
        return e

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this command menu belongs to the person who opened it.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.HTTPException, discord.NotFound):
                pass

    @discord.ui.button(label="‹", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index > 0:
            self.index -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

    @discord.ui.button(label="›", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.index < len(self.pages) - 1:
            self.index += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embed(), view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="×", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        try:
            await interaction.message.delete()
        except discord.HTTPException:
            await interaction.response.edit_message(view=None)


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
    vcfg = v53cfg(member.guild.id) if "v53cfg" in globals() else {}
    join_cid = vcfg.get("logs", {}).get("join") if vcfg else None
    join_channel = member.guild.get_channel(int(join_cid)) if join_cid else None
    if join_channel:
        try:
            await join_channel.send(embed=make_embed("member joined", f"{member.mention} · `{member.id}`\n\naccount created <t:{int(member.created_at.timestamp())}:R>"))
        except discord.HTTPException:
            pass
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
        cfg = booster_config[after.guild.id]
        channel = after.guild.get_channel(int(cfg.get("channel"))) if cfg.get("channel") else after.guild.system_channel
        if channel:
            try:
                await channel.send(embed=build_booster_embed(after))
            except discord.HTTPException as exc:
                print(f"booster embed send failed: {exc}")


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
            channel_id = cfg.get("channel")
            channel = member.guild.get_channel(int(channel_id)) if channel_id else None
            if channel:
                try:
                    await channel.send(embed=build_vanity_embed(member))
                except (discord.Forbidden, discord.HTTPException) as exc:
                    print(f"vanity embed send failed in {member.guild.id}/{member.id}: {exc}")
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
        # Legacy word filter.
        if filter_enabled[message.guild.id] and any(w in content.split() for w in filter_words[message.guild.id]):
            try: await message.delete()
            except discord.HTTPException: pass
            return

        # Persistent v53 protection switches.
        cfg = v53cfg(message.guild.id) if "v53cfg" in globals() else {}
        auto = cfg.get("automod", {}) if cfg else {}
        exempt = {int(x) for x in cfg.get("automod_exempt_roles", [])} if cfg else set()
        exempted = any(r.id in exempt for r in message.author.roles) or message.author.guild_permissions.administrator
        if not exempted:
            reason = None
            if auto.get("links") and re.search(r"https?://|discord\.gg/|discord\.com/invite/", content, re.I):
                reason = "link filter"
            elif auto.get("caps") and len(re.sub(r"[^A-Za-z]", "", message.content)) >= 12:
                letters = re.sub(r"[^A-Za-z]", "", message.content)
                if letters and sum(c.isupper() for c in letters) / len(letters) >= 0.75:
                    reason = "caps filter"
            elif auto.get("mentions") and len(message.mentions) + len(message.role_mentions) >= 6:
                reason = "mention spam"
            if auto.get("spam"):
                q = v53_message_times[(message.guild.id, message.author.id)]
                now = time.time(); q.append(now)
                while q and now - q[0] > 7: q.popleft()
                if len(q) >= 6: reason = "spam filter"
            if reason:
                try: await message.delete()
                except discord.HTTPException: pass
                cid = cfg.get("logs", {}).get("audit")
                ch = message.guild.get_channel(int(cid)) if cid else None
                if ch:
                    try: await ch.send(embed=make_embed("automod action", f"deleted {message.author.mention}'s message in {message.channel.mention}\n\n**Reason**\n`{reason}`"))
                    except discord.HTTPException: pass
                return

        # Gallery mode: only messages with attachments/images are allowed.
        if message.channel.id in {int(x) for x in cfg.get("gallery_channels", [])} and not message.attachments:
            try: await message.delete()
            except discord.HTTPException: pass
            return

        # Guild-local command aliases.
        if content.startswith(PREFIX):
            parts = message.content[len(PREFIX):].strip().split(maxsplit=1)
            if parts:
                custom = cfg.get("aliases", {}).get(parts[0].lower())
                if custom:
                    rest = f" {parts[1]}" if len(parts) > 1 else ""
                    message.content = PREFIX + custom + rest

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


class GroupHelpView(discord.ui.View):
    """Bleed-style command group browser. Controls are removed after 60 seconds."""
    def __init__(self, ctx, group, entries, display_name):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.group = group
        self.entries = list(entries)
        self.display_name = display_name
        self.author_id = ctx.author.id
        self.index = 0
        self.sort_mode = 0
        self.message = None
        self.refresh_buttons()

    def ordered_entries(self):
        entries = list(self.entries)
        if self.sort_mode == 1:
            entries.sort(key=lambda c: c.name.lower())
        elif self.sort_mode == 2:
            entries.sort(key=lambda c: c.name.lower(), reverse=True)
        return entries

    def refresh_buttons(self):
        total = max(1, len(self.ordered_entries()))
        self.previous.disabled = self.index <= 0
        self.next.disabled = self.index >= total - 1
        self.page.label = f"{self.index + 1}/{total}"
        self.sort.label = ("Sort: Default", "Sort: A–Z", "Sort: Z–A")[self.sort_mode]

    def make_embed(self):
        entries = self.ordered_entries()
        total = len(entries)
        if not entries:
            return make_embed(f"Group Command: {self.display_name}", "No subcommands are available.")
        cmd = entries[self.index]
        info = COMMAND_INFO.get(cmd.qualified_name, COMMAND_INFO.get(cmd.name, (cmd.help or "No description available.", cmd.signature or "n/a", "n/a", cmd.aliases)))
        description, syntax, example, aliases = info
        alias_text = ", ".join(aliases) if aliases else "n/a"
        parameters = cmd.signature.strip() or "n/a"
        permissions = "Manage Channels" if cmd.name in {"exclusive", "add", "remove", "clear"} and self.group.name in {"ar", "autoresponder"} else "n/a"
        if cmd.name in {"servers", "guilds", "maintenance", "status", "stream"}:
            permissions = "Server Owner"
        module = getattr(cmd, "cog_name", None) or "servers"
        e = discord.Embed(title=f"Group Command: {self.display_name} {cmd.name}", description=description, color=COLOR)
        e.add_field(name="Aliases", value=alias_text or "n/a", inline=True)
        e.add_field(name="Parameters", value=parameters or "n/a", inline=True)
        e.add_field(name="Information", value=f"⚠️ {permissions}", inline=True)
        e.add_field(name="Usage", value=f"```text\nSyntax: {PREFIX}{self.display_name} {syntax}\nExample: {PREFIX}{self.display_name} {example}\n```", inline=False)
        e.description = (e.description or "") + f"\n\n-# Page {self.index + 1}/{total} ({total} entries) ∙ Module: {module}"
        return e

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("this help menu belongs to the person who opened it.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except (discord.HTTPException, discord.NotFound):
                pass

    @discord.ui.button(label="❮", style=discord.ButtonStyle.primary)
    async def previous(self, interaction, button):
        self.index = max(0, self.index - 1)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="❯", style=discord.ButtonStyle.primary)
    async def next(self, interaction, button):
        self.index = min(len(self.ordered_entries()) - 1, self.index + 1)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page(self, interaction, button):
        await interaction.response.defer()

    @discord.ui.button(label="Sort: Default", style=discord.ButtonStyle.secondary)
    async def sort(self, interaction, button):
        self.sort_mode = (self.sort_mode + 1) % 3
        self.index = min(self.index, len(self.ordered_entries()) - 1)
        self.refresh_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    @discord.ui.button(label="✕", style=discord.ButtonStyle.danger)
    async def close(self, interaction, button):
        self.stop()
        await interaction.response.edit_message(view=None)


@bot.command(aliases=["h"])
async def help(ctx, *, command_name=None):
    if command_name:
        cmd = bot.get_command(command_name.lower().strip())
        if not cmd:
            return await ctx.send(embed=make_embed("command not found", f"I couldn't find `{PREFIX}{command_name}`.\n\nuse `{PREFIX}commands` to browse every command."))
        display_name = command_name.strip().split()[0]
        if isinstance(cmd, commands.Group):
            entries = list(cmd.commands)
            if entries:
                view = GroupHelpView(ctx, cmd, entries, display_name)
                msg = await ctx.send(embed=view.make_embed(), view=view)
                view.message = msg
                return
        info = COMMAND_INFO.get(cmd.qualified_name, COMMAND_INFO.get(cmd.name, (cmd.help or "No description available.", cmd.signature or cmd.qualified_name, "n/a", cmd.aliases)))
        description, syntax, example, aliases = info
        alias_text = ", ".join(aliases) if aliases else "n/a"
        parameters = cmd.signature.strip() or "n/a"
        if cmd.name in {"servers", "guilds", "maintenance", "status", "stream"}:
            permission = "⚠️ Server Owner"
        elif cmd.name in {"ar", "autoreact", "autorole"}:
            permission = "⚠️ Manage Channels"
        elif getattr(cmd, "checks", None):
            permission = "Configured server permission"
        else:
            permission = "n/a"
        module = getattr(cmd, "cog_name", None) or "servers"
        e = discord.Embed(title=f"Command: {cmd.qualified_name}", description=description, color=COLOR)
        e.add_field(name="Aliases", value=alias_text or "n/a", inline=True)
        e.add_field(name="Parameters", value=parameters or "n/a", inline=True)
        e.add_field(name="Information", value=permission, inline=True)
        e.add_field(name="Usage", value=f"```text\nSyntax: {PREFIX}{syntax}\nExample: {PREFIX}{example}\n```", inline=False)
        e.description = (e.description or "") + f"\n\n-# Page 1/1 (1 entry) ∙ Module: {module}"
        return await ctx.send(embed=e)
    e = directory_embed("bleeed", "premium-style moderation, security, server management and utility tools", ctx=ctx)
    e.add_field(name="**Prefix**", value=f"`{PREFIX}`", inline=True)
    e.add_field(name="**Commands**", value=f"`{len(COMMAND_INFO)}`", inline=True)
    e.add_field(name="**Help**", value=f"`{PREFIX}help <command>**", inline=True)
    e.description += f"\n\nuse `{PREFIX}commands` to browse the command directory."
    await ctx.send(embed=e)


@bot.command(name="servers", aliases=["guilds"])
async def servers(ctx):
    if ctx.author.id != BOT_OWNER_ID:
        return
    guilds = sorted(bot.guilds, key=lambda g: g.name.lower())
    view = ServerListView(BOT_OWNER_ID, guilds)
    msg = await ctx.send(embed=view.embed(), view=view)
    view.message = msg


@bot.command(name="commands", aliases=["cmd"])
async def command_list(ctx):
    pages = build_pages()
    view = CommandsView(pages, ctx.author.id)
    msg = await ctx.send(embed=view.embed(), view=view)
    view.message = msg


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
    record_modlog(ctx.guild, member, "Unwarn", ctx.author, removed, warning_number=number)
    await ctx.send(embed=result_embed("Warning Removed", "User", member.mention, extra=[("Warning", f"`#{number}` · {removed}"), ("Moderator", ctx.author.mention)]))

@bot.hybrid_command(name="clearwarnings", description="Clear all warnings for a member.")
async def clearwarnings(ctx, member: discord.Member):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you don't have the required warn role."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    count = len(warning_data[ctx.guild.id][member.id])
    warning_data[ctx.guild.id][member.id].clear()
    record_modlog(ctx.guild, member, "Clear Warnings", ctx.author, f"Cleared {count} warnings")
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

@bot.command(name="guildpermissions")
async def guildpermissions(ctx, member: discord.Member=None):
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
async def booster(ctx, action=None, *, value=""):
    if not has_manage(ctx):
        return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    cfg = booster_config[ctx.guild.id]
    action = (action or "settings").lower()
    if action in {"help", "settings"}:
        role = ctx.guild.get_role(boost_roles.get(ctx.guild.id)) if boost_roles.get(ctx.guild.id) else None
        channel = ctx.guild.get_channel(int(cfg.get("channel"))) if cfg.get("channel") else None
        return await ctx.send(embed=make_embed("booster settings", f"**Role**\n{role.mention if role else 'not configured'}\n\n**Channel**\n{channel.mention if channel else 'server system channel'}\n\n**Title**\n{cfg.get('title')}\n\n**Description**\n{cfg.get('description')}\n\n**Color**\n`{cfg.get('color')}`\n\nUse `{PREFIX}booster channel #channel`, `{PREFIX}booster title <text>`, `{PREFIX}booster description <text>`, `{PREFIX}booster color #hex`, `{PREFIX}booster image <url|off>`, `{PREFIX}booster thumbnail <user|url|off>`, `{PREFIX}booster preview` or `{PREFIX}booster reset` to customize it."))
    if action == "channel":
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        if not channel:
            m = re.search(r"(?:<#)?(\d{15,20})>?", value); channel = ctx.guild.get_channel(int(m.group(1))) if m else None
        if not isinstance(channel, discord.TextChannel):
            return await ctx.send(embed=make_embed("booster", "mention a text channel."))
        cfg["channel"] = channel.id; save_booster_config()
        return await ctx.send(embed=make_embed("booster channel updated", f"booster embeds will now be sent in {channel.mention}."))
    if action == "title": cfg["title"] = value
    elif action == "description": cfg["description"] = value
    elif action == "color":
        if parse_color(value) is None: return await ctx.send(embed=make_embed("booster", "use a 6-digit hex color such as `#efcead`."))
        cfg["color"] = value if value.startswith("#") else "#" + value
    elif action == "image": cfg["image"] = None if value.lower() == "off" else value
    elif action == "thumbnail": cfg["thumbnail"] = None if value.lower() == "off" else ("{user_avatar}" if value.lower() == "user" else value)
    elif action == "preview": return await ctx.send(embed=build_booster_embed(ctx.author))
    elif action == "reset":
        cfg.update({"title":"Thank you for boosting!","description":"{user} just boosted **{server}**! Thank you for supporting the server.","color":"#000001","image":None,"thumbnail":"{user_avatar}"})
    elif action == "role":
        role = ctx.message.role_mentions[0] if ctx.message.role_mentions else None
        if not role or role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("booster", "mention a role below my highest role."))
        boost_roles[ctx.guild.id] = role.id
        return await ctx.send(embed=make_embed("booster role set", f"boosters will receive {role.mention}."))
    else:
        return await ctx.send(embed=make_embed("booster", "unknown option. use `,booster settings` for the available options."))
    save_booster_config()
    await ctx.send(embed=make_embed("booster updated", f"**{action}** has been updated. use `{PREFIX}booster preview` to preview it."))

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

@bot.command(aliases=["modlog"])
async def modlogs(ctx, member: discord.Member):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need a configured moderation role or Administrator."))
    entries = list(modlog_data[ctx.guild.id][member.id])[-20:]
    if not entries:
        return await ctx.send(embed=make_embed("Modlogs", f"No moderation logs found for {member.mention}."))
    lines = []
    for entry in reversed(entries):
        moderator = ctx.guild.get_member(entry.get("moderator_id"))
        mod_text = moderator.mention if moderator else f"`{entry.get('moderator_id')}`"
        ts = int(entry.get("timestamp", time.time()))
        reason = str(entry.get("reason", "No reason provided"))
        if len(reason) > 120: reason = reason[:117] + "..."
        lines.append(f"**{entry.get('action','Action')}** · <t:{ts}:R>\nModerator: {mod_text}\nReason: {reason}")
    body = "\n\n".join(lines)
    if len(body) > 5800: body = body[:5797] + "..."
    await ctx.send(embed=make_embed(f"Modlogs · {member.display_name}", body))

async def get_or_create_quarantine_role(guild):
    role = discord.utils.find(lambda r: r.name.lower() == "quarantine", guild.roles)
    if role:
        return role
    me = guild.me
    if not me or not me.guild_permissions.manage_roles:
        return None
    role = await guild.create_role(name="Quarantine", reason="BLEEED quarantine role setup")
    if role >= me.top_role:
        try: await role.delete(reason="Quarantine role could not be placed below the bot")
        except discord.HTTPException: pass
        return None
    return role

async def apply_quarantine_overwrites(guild, role):
    for channel in guild.channels:
        try:
            overwrite = channel.overwrites_for(role)
            overwrite.view_channel = False
            overwrite.send_messages = False
            overwrite.add_reactions = False
            overwrite.connect = False
            overwrite.speak = False
            await channel.set_permissions(role, overwrite=overwrite, reason="BLEEED quarantine")
        except (discord.Forbidden, discord.HTTPException):
            continue

@bot.command(aliases=["q"])
async def quarantine(ctx, member: discord.Member, *, reason="No reason provided"):
    if not role_ok(ctx.author, MUTE_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need a configured moderation role or Administrator."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot quarantine", "The target must be below my highest role and below your highest role."))
    if member.id in quarantine_data[ctx.guild.id]:
        return await ctx.send(embed=make_embed("already quarantined", f"{member.mention} is already quarantined."))
    if not bot_can(ctx, "manage_roles"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Manage Roles** permission to quarantine members."))
    role = await get_or_create_quarantine_role(ctx.guild)
    if not role or role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("quarantine failed", "I couldn't create or manage the Quarantine role. Make sure my bot role is high enough."))
    saved = [r.id for r in member.roles if r != ctx.guild.default_role and r < ctx.guild.me.top_role]
    try:
        if saved:
            await member.remove_roles(*[r for r in member.roles if r != ctx.guild.default_role and r < ctx.guild.me.top_role], reason=f"Quarantine by {ctx.author}: {reason}")
        await member.add_roles(role, reason=f"Quarantine by {ctx.author}: {reason}")
        await apply_quarantine_overwrites(ctx.guild, role)
    except (discord.Forbidden, discord.HTTPException):
        return await ctx.send(embed=make_embed("quarantine failed", "Discord denied the role change. Check my **Manage Roles** permission and hierarchy."))
    quarantine_data[ctx.guild.id][member.id] = saved
    save_quarantine()
    record_modlog(ctx.guild, member, "Quarantine", ctx.author, reason)
    await ctx.send(embed=result_embed("Member Quarantined", "User", fmt_user(member), extra=[("Reason", reason), ("Moderator", ctx.author.mention)]))

@bot.command(aliases=["unq"])
async def unquarantine(ctx, member: discord.Member):
    if not role_ok(ctx.author, MUTE_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need a configured moderation role or Administrator."))
    saved = quarantine_data[ctx.guild.id].get(member.id)
    if saved is None:
        return await ctx.send(embed=make_embed("not quarantined", f"{member.mention} is not quarantined."))
    if not bot_can(ctx, "manage_roles"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Manage Roles** permission to restore roles."))
    role = discord.utils.find(lambda r: r.name.lower() == "quarantine", ctx.guild.roles)
    try:
        if role and role in member.roles:
            await member.remove_roles(role, reason=f"Unquarantine by {ctx.author}")
        roles = [ctx.guild.get_role(rid) for rid in saved]
        roles = [r for r in roles if r and r < ctx.guild.me.top_role]
        if roles:
            await member.add_roles(*roles, reason=f"Unquarantine by {ctx.author}")
    except (discord.Forbidden, discord.HTTPException):
        return await ctx.send(embed=make_embed("unquarantine failed", "Discord denied the role change. Check my **Manage Roles** permission and hierarchy."))
    quarantine_data[ctx.guild.id].pop(member.id, None)
    save_quarantine()
    record_modlog(ctx.guild, member, "Unquarantine", ctx.author, "Removed quarantine")
    await ctx.send(embed=result_embed("Member Unquarantined", "User", fmt_user(member), extra=[("Moderator", ctx.author.mention)]))

@bot.group(name="ban", aliases=["b"], invoke_without_command=True)
async def ban(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author, {BAN_ROLE}):
        return await ctx.send(embed=make_embed("no permission", "you need the configured ban role or Administrator."))
    if not bot_can(ctx, "ban_members"):
        return await ctx.send(embed=make_embed("bot permission missing", "I need **Ban Members** permission to do that."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot ban member", "The target must be below my highest role and below your highest role."))
    explicit = re.match(r"^(\d{1,6})(?:\s+(.*))?$", reason.strip())
    if explicit:
        delete_seconds = max(0, min(int(explicit.group(1)), 604800))
        reason = explicit.group(2) or "no reason provided"
    else:
        delete_seconds = int(guild_cfg(ctx.guild.id).get("ban_delete_seconds", 604800))
        delete_seconds = max(0, min(delete_seconds, 604800))
    try:
        await member.ban(reason=reason, delete_message_seconds=delete_seconds)
    except discord.Forbidden:
        return await ctx.send(embed=make_embed("ban failed", "Discord denied the ban. Check my **Ban Members** permission and role hierarchy."))
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("ban failed", "Discord returned an error while banning that member."))
    record_modlog(ctx.guild, member, "Ban", ctx.author, reason, details=f"Message deletion window: {delete_seconds} seconds")
    await ctx.send(embed=result_embed("Member Banned", "User", fmt_user(member), extra=[("Reason", reason), ("Messages", f"deleted from the last {delete_seconds} seconds"), ("Moderator", ctx.author.mention)]))

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
    record_modlog(ctx.guild, user_id, "Unban", ctx.author, "Unbanned by moderator")
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
    record_modlog(ctx.guild, member, "Kick", ctx.author, reason)
    await ctx.send(embed=result_embed("Member Kicked", "User", fmt_user(member), extra=[("Reason", reason), ("Moderator", ctx.author.mention)]))

@bot.group(name="mute", aliases=["timeout","to"], invoke_without_command=True)
async def mute(ctx,member:discord.Member=None,minutes:int=10,*,reason="no reason provided"):
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
    record_modlog(ctx.guild, member, "Mute", ctx.author, reason, duration=f"{minutes} minutes")
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
    record_modlog(ctx.guild, member, "Unmute", ctx.author, "Removed timeout")
    await ctx.send(embed=result_embed("Member Unmuted", "User", fmt_user(member), extra=[("Moderator", ctx.author.mention)]))

@bot.command(aliases=["w"])
async def warn(ctx,member:discord.Member,*,reason="no reason provided"):
    if not role_ok(ctx.author, WARN_ROLES):
        return await ctx.send(embed=make_embed("no permission", "you need the configured warn role or Administrator."))
    if not target_ok(ctx,member):
        return await ctx.send(embed=make_embed("cannot warn member", "You can't warn yourself, the server owner, or someone at/above your role."))
    warning_data[ctx.guild.id][member.id].append(reason)
    record_modlog(ctx.guild, member, "Warn", ctx.author, reason)
    await ctx.send(embed=result_embed("Member Warned", "User", fmt_user(member), extra=[("Reason", reason), ("Total Warnings", str(len(warning_data[ctx.guild.id][member.id]))), ("Moderator", ctx.author.mention)]))

@bot.command()
async def warnings(ctx,member:discord.Member=None):
    member=member or ctx.author
    items=warning_data[ctx.guild.id][member.id]
    body="\n".join(f"`{i:02}` **{r}**" for i,r in enumerate(items,1)) or "No warnings recorded."
    await ctx.send(embed=result_embed(f"Warnings · {member.display_name}", "User", fmt_user(member), extra=[("Warnings", body)]))

@bot.group(name="purge", aliases=["p","clear"], invoke_without_command=True)
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

@bot.group(name="unlock", aliases=["ul"], invoke_without_command=True)
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



@bot.command(aliases=["uid"])
async def id(ctx, member: discord.Member=None):
    """Show a user's Discord ID."""
    member = member or ctx.author
    await ctx.send(embed=make_embed("user id", f"**User**\n{member.mention}\n\n**ID**\n`{member.id}`"))

@bot.command(aliases=["joinedat"])
async def joined(ctx, member: discord.Member=None):
    """Show when a member joined the server."""
    member = member or ctx.author
    value = f"<t:{int(member.joined_at.timestamp())}:F>" if member.joined_at else "unknown"
    await ctx.send(embed=make_embed("member joined", f"**Member**\n{member.mention}\n\n**Joined**\n{value}"))

@bot.command(aliases=["createdat"])
async def created(ctx, member: discord.Member=None):
    """Show when a Discord account was created."""
    member = member or ctx.author
    await ctx.send(embed=make_embed("account created", f"**User**\n{member.mention}\n\n**Created**\n<t:{int(member.created_at.timestamp())}:F>\n<t:{int(member.created_at.timestamp())}:R>"))

@bot.command(aliases=["rand"])
async def randomnumber(ctx, minimum: int=1, maximum: int=100):
    """Pick a random integer in a range."""
    if minimum > maximum:
        minimum, maximum = maximum, minimum
    if maximum - minimum > 1000000000:
        return await ctx.send(embed=make_embed("random number", "that range is too large."))
    await ctx.send(embed=make_embed("random number", f"`{random.randint(minimum, maximum)}`\n\nRange: `{minimum}`–`{maximum}`"))


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


@bot.group(name="slowmode", invoke_without_command=True)
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int = None):
    """Set channel slowmode."""
    if seconds is None:
        return await ctx.send(embed=make_embed("slowmode", f"usage: `{PREFIX}slowmode <seconds>` or `{PREFIX}slowmode on/off [channel]`."))
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


@bot.group(name="role", aliases=["r"], invoke_without_command=True)
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member = None, role: discord.Role = None):
    """Toggle a role on a member: add it once, remove it if used again."""
    if member is None or role is None:
        return await ctx.send(embed=make_embed("role", f"usage: `{PREFIX}role <member> <role>` or `{PREFIX}role <subcommand>`."))
    if role >= ctx.guild.me.top_role or (not ctx.author.guild_permissions.administrator and role >= ctx.author.top_role):
        return await ctx.send(embed=make_embed("error", "that role is too high for you or the bot."))
    if role in member.roles:
        await member.remove_roles(role, reason=f"role toggled off by {ctx.author}")
        icon = "<:remove:1557785190183600258>"
        message = f"Removed {role.mention} from {member.mention}"
    else:
        await member.add_roles(role, reason=f"role toggled on by {ctx.author}")
        icon = "<:add:1557785192712642634>"
        message = f"Added {role.mention} to {member.mention}"
    # Use the matching custom emoji for each action and include the command invoker.
    await ctx.send(embed=discord.Embed(
        description=f"{icon} {ctx.author.mention}: {message}",
        color=COLOR,
    ))


@bot.hybrid_command(name="removerole")
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, role: discord.Role):
    """Remove a role from a member."""
    if role >= ctx.guild.me.top_role or role >= ctx.author.top_role:
        return await ctx.send(embed=make_embed("error", "that role is too high for you or the bot."))
    await member.remove_roles(role, reason=f"role removed by {ctx.author}")
    await ctx.send(embed=action_embed(f"Removed {role.mention} from {member.mention}", removed=True))


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


class BRShareView(discord.ui.View):
    def __init__(self, owner_id, target_id, role_id, timeout=120):
        super().__init__(timeout=timeout); self.owner_id=owner_id; self.target_id=target_id; self.role_id=role_id; self.done=False
    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id: return await interaction.response.send_message("this confirmation is only for the mentioned user.", ephemeral=True)
        role=interaction.guild.get_role(self.role_id)
        if not role or role >= interaction.guild.me.top_role: return await interaction.response.edit_message(content="that role can no longer be shared.", view=None)
        try: await interaction.user.add_roles(role, reason="BR role share accepted")
        except discord.HTTPException: return await interaction.response.edit_message(content="i couldn't give you that role.", view=None)
        self.done=True; await interaction.response.edit_message(content=f"{interaction.user.mention} accepted **{role.name}**.", view=None)
    @discord.ui.button(label="No", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target_id: return await interaction.response.send_message("this confirmation is only for the mentioned user.", ephemeral=True)
        self.done=True; await interaction.response.edit_message(content=f"{interaction.user.mention} declined **{interaction.guild.get_role(self.role_id).name if interaction.guild.get_role(self.role_id) else 'the role'}**.", view=None)

@bot.command(name="br")
async def br(ctx, action=None, *, value=""):
    action=(action or "help").lower()

    # Override management is deliberately admin-only.
    if action == "override":
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=make_embed("Booster Role", "only server administrators can manage BR overrides."))
        target = ctx.message.mentions[0] if ctx.message.mentions else None
        lowered = value.lower().strip()
        remove = lowered.startswith("remove ") or lowered.startswith("off ") or lowered.startswith("revoke ")
        if not target and remove:
            parts = value.split()
            if len(parts) > 1:
                try:
                    target = ctx.guild.get_member(int(re.sub(r"\D", "", parts[1])))
                except (ValueError, TypeError):
                    target = None
        if not target:
            return await ctx.send(embed=make_embed("Booster Role", f"use `{PREFIX}br override @user` to allow a user to create a BR without boosting, or `{PREFIX}br override remove @user` to revoke it."))
        if target.bot:
            return await ctx.send(embed=make_embed("Booster Role", "you can't give a BR override to a bot."))
        users = br_overrides[ctx.guild.id]
        if remove:
            if target.id not in users:
                return await ctx.send(embed=make_embed("Booster Role", f"{target.mention} doesn't have a BR override."))
            users.discard(target.id)
            save_br_overrides()
            return await ctx.send(embed=make_embed("Booster Role", f"BR override removed from {target.mention}."))
        users.add(target.id)
        save_br_overrides()
        return await ctx.send(embed=make_embed("Booster Role", f"{target.mention} can now create a BR without boosting."))

    if not has_br_access(ctx.author):
        return
    if action == "create":
        if not value.strip(): return await ctx.send(embed=make_embed("Booster Role", f"usage: `{PREFIX}br create rolename`"))
        existing=ctx.guild.get_role(br_config[ctx.guild.id].get(ctx.author.id)) if br_config[ctx.guild.id].get(ctx.author.id) else None
        if existing: return await ctx.send(embed=make_embed("Booster Role", f"you already have {existing.mention}. edit it with `{PREFIX}br color`, `{PREFIX}br icon`, or create a new one after deleting it."))
        base_id = br_base_config.get(ctx.guild.id)
        base_role = ctx.guild.get_role(base_id) if base_id else None
        me = ctx.guild.me
        if base_role and (not me or base_role >= me.top_role):
            return await ctx.send(embed=make_embed("Booster Role", "the BR base role must be below my highest role."))
        role=await ctx.guild.create_role(name=value.strip(), reason=f"BR role created by {ctx.author}")
        if base_role:
            try:
                await role.edit(position=base_role.position + 1, reason=f"BR role placed above base role by {ctx.author}")
            except discord.HTTPException:
                await role.delete(reason="BR role placement failed")
                return await ctx.send(embed=make_embed("Booster Role", "i couldn't place the BR role above the configured base role."))
        br_config[ctx.guild.id][ctx.author.id]=role.id; save_br_config()
        try:
            await ctx.author.add_roles(role, reason="BR role automatically assigned on creation")
        except discord.Forbidden:
            br_config[ctx.guild.id].pop(ctx.author.id, None)
            save_br_config()
            try:
                await role.delete(reason="BR role assignment failed")
            except discord.HTTPException:
                pass
            return await ctx.send(embed=make_embed("Booster Role", "the role was created, but i couldn't give it to you. Check my role hierarchy and Manage Roles permission."))
        except discord.HTTPException:
            return await ctx.send(embed=make_embed("Booster Role", "the role was created, but Discord wouldn't assign it to you. Try again."))
        return await ctx.send(embed=make_embed("Booster Role", f"**Role**\n{role.mention} · `{role.id}`\n\n**Assigned To**\n{ctx.author.mention}"))
    if action == "base":
        if not ctx.author.guild_permissions.administrator:
            return await ctx.send(embed=make_embed("Booster Role", "only server administrators can set the BR base role."))
        target = ctx.message.role_mentions[0] if ctx.message.role_mentions else None
        if not target or target.is_default():
            return await ctx.send(embed=make_embed("Booster Role", f"use `{PREFIX}br base @role`."))
        me = ctx.guild.me
        if not me or target >= me.top_role:
            return await ctx.send(embed=make_embed("Booster Role", "the BR base role must be below my highest role."))

        # Keep every tracked BR role above the configured base role.
        tracked = []
        for creator_id, rid in br_config[ctx.guild.id].items():
            r = ctx.guild.get_role(rid)
            if r and not r.is_default() and r < me.top_role:
                tracked.append((r, creator_id))
        if target.position + len(tracked) >= me.top_role.position:
            return await ctx.send(embed=make_embed("Booster Role", "there isn't enough space above that base role for all existing BR roles. Choose a lower base role."))

        # Move all existing BR roles as one hierarchy update so the base role
        # remains underneath every BR role without position-shift surprises.
        ordered = [r for r, _ in sorted(tracked, key=lambda item: item[0].position)]
        positions = {r: target.position + 1 + offset for offset, r in enumerate(ordered)}
        try:
            await ctx.guild.edit_role_positions(positions=positions, reason=f"BR base role set by {ctx.author}")
        except (discord.Forbidden, discord.HTTPException):
            return await ctx.send(embed=make_embed("Booster Role", "i couldn't move the existing BR roles above the base role. Check my Manage Roles permission."))

        br_base_config[ctx.guild.id] = target.id
        save_br_base_config()
        return await ctx.send(embed=make_embed("Booster Role", f"**Base Role**\n{target.mention} · `{target.id}`\n\nAll existing and new BR roles are kept above this role."))

    if action == "list":
        entries = []
        for creator_id, rid in br_config[ctx.guild.id].items():
            r = ctx.guild.get_role(rid)
            creator = ctx.guild.get_member(int(creator_id))
            if r:
                creator_text = creator.mention if creator else f"<@{creator_id}>"
                entries.append((r.position, r, creator_text))
        entries.sort(key=lambda x: x[0], reverse=True)
        base_id = br_base_config.get(ctx.guild.id)
        base_role = ctx.guild.get_role(base_id) if base_id else None
        if not entries:
            body = "no BR roles have been created in this server."
        else:
            body = "\n".join(f"`{i:02}` **{r.mention}** · created by {creator}" for i, (_, r, creator) in enumerate(entries, 1))
        if base_role:
            body += f"\n\n**Base Role**\n{base_role.mention} · `{base_role.id}`"
        return await ctx.send(embed=make_embed("Booster Role", body))

    role_id=br_config[ctx.guild.id].get(ctx.author.id); role=ctx.guild.get_role(role_id) if role_id else None
    if action == "delete":
        if not role:
            # Clean stale ownership data if the role was deleted manually.
            br_config[ctx.guild.id].pop(ctx.author.id, None)
            br_color_pairs.get(str(ctx.guild.id), {}).pop(str(ctx.author.id), None)
            save_br_config(); save_br_color_pairs()
            return await ctx.send(embed=make_embed("Booster Role", f"you don't have a BR role. Create one with `{PREFIX}br create <rolename>`."))
        if role >= ctx.guild.me.top_role:
            return await ctx.send(embed=make_embed("Booster Role", "my highest role must be above your BR role."))
        try:
            await role.delete(reason=f"BR role deleted by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=make_embed("Booster Role", "i couldn't delete your BR role. Check my Manage Roles permission."))
        except discord.HTTPException:
            return await ctx.send(embed=make_embed("Booster Role", "Discord couldn't delete your BR role. Try again."))
        br_config[ctx.guild.id].pop(ctx.author.id, None)
        br_color_pairs.get(str(ctx.guild.id), {}).pop(str(ctx.author.id), None)
        save_br_config(); save_br_color_pairs()
        return await ctx.send(embed=make_embed("Booster Role", "your BR role has been deleted."))
    if action in {"help","settings"}: return await ctx.send(embed=make_embed("Booster Role", f"`{PREFIX}br create <rolename>` — create your role\n`{PREFIX}br color <#hexcode> [#hexcode]` — solid color or real Discord gradient\n`{PREFIX}br colour <#hexcode> [#hexcode]` — solid color or real Discord gradient\n`{PREFIX}br icon <emoji>` — use any Unicode/custom emoji (animated custom emojis become still)\n`{PREFIX}br delete` — delete your BR role\n`{PREFIX}br list` — list BR roles and their creators\n`{PREFIX}br share @user` — ask a user to accept your role\n`{PREFIX}br override @user` — admin: let a user create without boosting\n`{PREFIX}br override remove @user` — admin: revoke an override" + (f"\n\n**Current Role**\n{role.mention}" if role else "\n\n**Current Role**\nnot created")))
    if not role: return await ctx.send(embed=make_embed("Booster Role", f"create your role first with `{PREFIX}br create <rolename>`."))
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("Booster Role", "my highest role must be above your BR role."))
    if action in {"name", "rename"}:
        new_name = value.strip()
        if not new_name:
            return await ctx.send(embed=make_embed("Booster Role", f"use `{PREFIX}br name <rolename>`."))
        if len(new_name) > 100:
            return await ctx.send(embed=make_embed("Booster Role", "role names can be up to 100 characters."))
        try:
            edited = await role.edit(name=new_name, reason=f"BR role renamed by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(embed=make_embed("Booster Role", "i couldn't rename that role. Check my role hierarchy."))
        except discord.HTTPException:
            return await ctx.send(embed=make_embed("Booster Role", "Discord couldn't rename that role."))
        return await ctx.send(embed=make_embed("BR role renamed", f"**Role**\n{edited.mention} · `{edited.id}`\n\n**New Name**\n`{edited.name}`"))
    if action in {"color","colour"}:
        parts = value.strip().split()
        if len(parts) not in {1, 2}:
            return await ctx.send(embed=make_embed("Booster Role", "use `,br color #hexcode` or `,br color #hexcode #hexcode`."))
        parsed = [parse_color(part) for part in parts]
        if any(color is None for color in parsed):
            return await ctx.send(embed=make_embed("Booster Role", "use valid 6-digit hex colors such as `#efcead #c49a6c`."))

        def fmt_hex(value):
            return value if value.startswith("#") else f"#{value}"

        first = parsed[0]
        if len(parsed) == 2:
            # discord.py 2.6+ exposes Discord's native enhanced role styles.
            # Supplying a primary + secondary colour makes this an actual
            # Discord gradient role instead of blending the two colors into one.
            second = parsed[1]
            try:
                await role.edit(
                    color=discord.Color(first),
                    secondary_color=discord.Color(second),
                    reason=f"BR gradient changed by {ctx.author}",
                )
            except TypeError:
                # Compatibility with builds exposing the British spelling.
                await role.edit(
                    colour=discord.Color(first),
                    secondary_colour=discord.Color(second),
                    reason=f"BR gradient changed by {ctx.author}",
                )
            br_color_pairs.setdefault(str(ctx.guild.id), {})[str(ctx.author.id)] = [fmt_hex(parts[0]), fmt_hex(parts[1])]
            save_br_color_pairs()
            return await ctx.send(embed=make_embed("BR gradient updated", f"**Gradient**\n`{fmt_hex(parts[0])}` → `{fmt_hex(parts[1])}`\n\nThe role now uses Discord's native gradient style."))

        try:
            await role.edit(color=discord.Color(first), secondary_color=None, reason=f"BR role color changed by {ctx.author}")
        except TypeError:
            await role.edit(colour=discord.Color(first), secondary_colour=None, reason=f"BR role color changed by {ctx.author}")
        br_color_pairs.setdefault(str(ctx.guild.id), {})[str(ctx.author.id)] = [fmt_hex(parts[0])]
        save_br_color_pairs()
        return await ctx.send(embed=make_embed("br role updated", f"**Color**\n`{fmt_hex(parts[0])}`"))
    if action == "icon":
        icon_value = value.strip()
        if not icon_value:
            return await ctx.send(embed=make_embed("Booster Role", "use `,br icon <emoji>` — Unicode emojis, custom emojis, and animated custom emojis are supported."))

        # Custom Discord emoji: download it and send the image bytes to Discord.
        # Animated custom emojis are converted to the first frame so the role icon
        # is always a still image.
        custom_emoji = _is_custom_emoji(icon_value)
        try:
            if custom_emoji:
                icon_bytes = await br_icon_bytes_from_custom_emoji(custom_emoji)
                if not icon_bytes:
                    return await ctx.send(embed=make_embed("Booster Role", "i couldn't download or convert that custom emoji."))
                await role.edit(display_icon=icon_bytes, reason=f"BR role icon changed by {ctx.author}")
            else:
                # Pass the Unicode emoji directly. This covers normal Apple/Android
                # emoji, skin tones, flags, ZWJ emoji, and other Unicode sequences.
                await role.edit(display_icon=icon_value, reason=f"BR role icon changed by {ctx.author}")
        except (discord.Forbidden, discord.HTTPException, ValueError, TypeError):
            return await ctx.send(embed=make_embed("Booster Role", "Discord couldn't use that emoji as a role icon. Make sure the role is below my highest role and the server supports role icons."))
        return await ctx.send(embed=make_embed("Booster Role", f"**Icon**\n{icon_value}"))
    if action == "share":
        target=ctx.message.mentions[0] if ctx.message.mentions else None
        if not target: return await ctx.send(embed=make_embed("Booster Role", "mention the user you want to share the role with."))
        if target.bot: return await ctx.send(embed=make_embed("Booster Role", "you can't share a BR role with a bot."))
        view=BRShareView(ctx.author.id,target.id,role.id)
        return await ctx.send(f"{target.mention}, **{ctx.author.display_name}** wants to share **{role.name}** with you. Do you want it?", view=view)
    return await ctx.send(embed=make_embed("Booster Role", f"use `{PREFIX}br help` to see the available commands."))

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
            f"`{PREFIX}vanity channel #channel` — set the message channel\n"
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

@vanity.command(name="channel")
async def vanity_channel(ctx, channel: discord.TextChannel):
    cfg = vanity_config[ctx.guild.id]
    if channel.guild.id != ctx.guild.id:
        return await ctx.send(embed=make_embed("vanity", "that channel must be in this server."))
    perms = channel.permissions_for(ctx.guild.me)
    if not perms.send_messages or not perms.embed_links:
        return await ctx.send(embed=make_embed("vanity", f"i need Send Messages and Embed Links in {channel.mention}."))
    cfg["channel"] = channel.id
    save_vanity_config()
    await ctx.send(embed=make_embed("vanity channel updated", f"vanity embeds will now be sent in {channel.mention}."))


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
        "channel": None,
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


@bot.group(name="remind", invoke_without_command=True)
async def remind(ctx, duration: str = None, *, message: str = None):
    """Create a personal reminder."""
    if not duration or not message:
        return await ctx.send(embed=make_embed("reminder", f"usage: `{PREFIX}remind <duration> <message>`; examples: `10m homework`, `2h call mom`."))
    seconds = parse_duration(duration)
    if seconds is None or seconds < 1:
        return await ctx.send(embed=make_embed("reminder", "duration must look like `30s`, `10m`, `2h`, or `1d`."))
    data = _load_json_config("reminders.json", {})
    key = str(ctx.author.id)
    items = data.setdefault(key, [])
    rid = max([int(x.get("id", 0)) for x in items] + [0]) + 1
    due = int(time.time() + seconds)
    items.append({"id": rid, "guild_id": ctx.guild.id if ctx.guild else None, "channel_id": ctx.channel.id, "message": message[:500], "due": due})
    _save_json_file("reminders.json", data)
    await ctx.send(embed=make_embed("reminder set", f"**ID:** `{rid}`\n**Reminder:** {message}\n**Due:** <t:{due}:R>"))
    async def deliver_reminder():
        await asyncio.sleep(seconds)
        latest = _load_json_config("reminders.json", {})
        latest_items = latest.get(key, [])
        found = next((x for x in latest_items if int(x.get("id", 0)) == rid), None)
        if not found:
            return
        latest[key] = [x for x in latest_items if int(x.get("id", 0)) != rid]
        _save_json_file("reminders.json", latest)
        try:
            await ctx.author.send(embed=make_embed("reminder", message))
        except discord.HTTPException:
            try: await ctx.channel.send(ctx.author.mention, embed=make_embed("reminder", message))
            except discord.HTTPException: pass
    bot.loop.create_task(deliver_reminder())


# =========================
# ULTIMATE EXPANSION PACK
# =========================
ULTIMATE_CONFIG_FILE = "ultimate_config.json"
ultimate_config = _load_json_config(ULTIMATE_CONFIG_FILE, {})

def save_ultimate_config():
    _save_json_file(ULTIMATE_CONFIG_FILE, ultimate_config)

def guild_cfg(gid):
    cfg = ultimate_config.setdefault(str(gid), {})
    return cfg

def has_manage_server(ctx):
    return bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild))

def has_manage_roles(ctx):
    return bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_roles))

@bot.command(aliases=["memberslist"])
async def memberlist(ctx, role: discord.Role = None):
    members = [m for m in ctx.guild.members if role is None or role in m.roles]
    members.sort(key=lambda m: m.display_name.lower())
    if not members:
        return await ctx.send(embed=make_embed("member list", "no members matched that filter."))
    chunks = [members[i:i+25] for i in range(0, len(members), 25)]
    page = chunks[0]
    body = "\n".join(f"`{i:02}` {m.mention} · `{m.id}`" for i, m in enumerate(page, 1))
    body += f"\n\n-# {len(page)} shown · {len(members)} total"
    return await ctx.send(embed=make_embed("member list", body))

@bot.command(aliases=["rolecount"])
async def countrole(ctx, role: discord.Role):
    count = sum(role in m.roles for m in ctx.guild.members)
    await ctx.send(embed=make_embed("role count", f"**Role**\n{role.mention}\n\n**Members**\n`{count}`"))

@bot.command()
async def channelstats(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    try:
        recent = [m async for m in channel.history(limit=100)]
    except discord.HTTPException:
        recent = []
    bots = sum(m.author.bot for m in recent)
    await ctx.send(embed=make_embed("channel stats", f"**Channel**\n{channel.mention}\n\n**Recent Messages**\n`{len(recent)}`\n\n**Bot Messages**\n`{bots}`\n\n**Created**\n<t:{int(channel.created_at.timestamp())}:R>"))

@bot.command(aliases=["clonechannel"])
@commands.has_permissions(manage_channels=True)
async def channelclone(ctx, channel: discord.TextChannel = None, *, name: str = None):
    channel = channel or ctx.channel
    if not hasattr(channel, "clone"):
        return await ctx.send(embed=make_embed("channel clone", "that channel type cannot be cloned."))
    clone = await channel.clone(name=name or channel.name, reason=f"channel cloned by {ctx.author}")
    await ctx.send(embed=make_embed("channel cloned", f"**New Channel**\n{clone.mention} · `{clone.id}`"))

@bot.command(aliases=["clonerole"])
@commands.has_permissions(manage_roles=True)
async def roleclone(ctx, role: discord.Role):
    if role.is_default() or role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("role clone", "that role cannot be cloned by me."))
    clone = await ctx.guild.create_role(name=role.name, colour=role.colour, hoist=role.hoist, mentionable=role.mentionable, reason=f"role cloned by {ctx.author}")
    await ctx.send(embed=make_embed("role cloned", f"**New Role**\n{clone.mention} · `{clone.id}`"))

@bot.command()
@commands.has_permissions(manage_roles=True)
async def roleall(ctx, role: discord.Role):
    if role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("role all", "my highest role must be above that role."))
    added = 0
    for member in ctx.guild.members:
        if role not in member.roles and member != ctx.guild.me:
            try:
                await member.add_roles(role, reason=f"roleall by {ctx.author}")
                added += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
    await ctx.send(embed=make_embed("role all", f"added {role.mention} to `{added}` members."))

@bot.command()
@commands.has_permissions(manage_roles=True)
async def unroleall(ctx, role: discord.Role):
    if role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("unrole all", "my highest role must be above that role."))
    removed = 0
    for member in ctx.guild.members:
        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"unroleall by {ctx.author}")
                removed += 1
            except (discord.Forbidden, discord.HTTPException):
                pass
    await ctx.send(embed=action_embed(f"Removed {role.mention} from `{removed}` members", removed=True))

@bot.group(name="lockdown", invoke_without_command=True)
@commands.has_permissions(manage_channels=True)
async def lockdown(ctx, channel: discord.TextChannel = None, *, reason: str = "Server lockdown"):
    targets = [channel] if channel else [c for c in ctx.guild.text_channels if c != ctx.channel]
    changed = 0
    for target in targets:
        try:
            overwrite = target.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = False
            await target.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{reason} by {ctx.author}")
            changed += 1
        except (discord.Forbidden, discord.HTTPException):
            pass
    await ctx.send(embed=make_embed("lockdown", f"locked `{changed}` text channel(s).\n\n**Reason**\n{reason}"))

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlockdown(ctx):
    changed = 0
    for channel in ctx.guild.text_channels:
        try:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            overwrite.send_messages = None
            await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Server unlockdown by {ctx.author}")
            changed += 1
        except (discord.Forbidden, discord.HTTPException):
            pass
    await ctx.send(embed=make_embed("unlockdown", f"unlocked `{changed}` text channels."))

@bot.command(aliases=["clean"])
@commands.has_permissions(manage_messages=True)
async def cleanup(ctx, amount: int = 50):
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(embed=make_embed("cleanup", f"deleted `{max(0, len(deleted)-1)}` messages."))
    await asyncio.sleep(3)
    try: await msg.delete()
    except discord.HTTPException: pass

@bot.group(name="notes", aliases=["modnote"], invoke_without_command=True)
async def modnote(ctx, action="list", member: discord.Member = None, *, note: str = None):
    if not (ctx.author.guild_permissions.administrator or any(r.id in WARN_ROLES for r in ctx.author.roles)):
        return
    if not member:
        return await ctx.send(embed=make_embed("mod notes", f"usage: `{PREFIX}modnote <add|list|clear> @user [note]`"))
    cfg = guild_cfg(ctx.guild.id); notes = cfg.setdefault("notes", {}).setdefault(str(member.id), [])
    if action.lower() == "add":
        if not note: return await ctx.send(embed=make_embed("mod notes", "provide a note."))
        notes.append({"note": note[:500], "moderator": ctx.author.id, "time": int(time.time())})
        notes[:] = notes[-50:]; save_ultimate_config()
        record_modlog(ctx.guild, member, "NOTE", ctx.author, note)
        return await ctx.send(embed=make_embed("mod notes", f"added a note for {member.mention}."))
    if action.lower() == "clear":
        cfg.setdefault("notes", {}).pop(str(member.id), None); save_ultimate_config()
        return await ctx.send(embed=make_embed("mod notes", f"cleared notes for {member.mention}."))
    lines = [f"`{i+1}` {x['note']} · <t:{x['time']}:R>" for i,x in enumerate(notes[-10:])]
    await ctx.send(embed=make_embed("mod notes", "\n".join(lines) if lines else "no notes."))

@bot.group(name="history", aliases=["cases"], invoke_without_command=True)
async def cases(ctx, member: discord.Member = None):
    if not (ctx.author.guild_permissions.administrator or any(r.id in WARN_ROLES for r in ctx.author.roles)):
        return
    if member is None:
        return await ctx.send(embed=make_embed("mod history", f"usage: `{PREFIX}history @member` or `{PREFIX}history view <case id>`."))
    entries = modlog_data[ctx.guild.id].get(member.id, [])[-25:]
    if not entries:
        return await ctx.send(embed=make_embed("mod cases", f"no cases found for {member.mention}."))
    lines=[]
    for i,e in enumerate(entries, 1):
        mod = ctx.guild.get_member(int(e.get("moderator_id", 0)))
        lines.append(f"`{e.get('case_id', i)}` **{e.get('action','UNKNOWN')}** · {e.get('reason','No reason')} · {mod.mention if mod else 'Unknown'} · <t:{int(e.get('timestamp',time.time()))}:R>")
    await ctx.send(embed=make_embed("mod cases", "\n".join(lines)))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def suggestchannel(ctx, channel: discord.TextChannel = None):
    if not channel:
        return await ctx.send(embed=make_embed("suggestions", f"use `{PREFIX}suggestchannel #channel`."))
    guild_cfg(ctx.guild.id)["suggestion_channel"] = channel.id; save_ultimate_config()
    await ctx.send(embed=make_embed("suggestions", f"suggestions will now go to {channel.mention}."))

@bot.command(aliases=["suggestion"])
async def suggest(ctx, *, text: str):
    channel_id = guild_cfg(ctx.guild.id).get("suggestion_channel")
    channel = ctx.guild.get_channel(channel_id) if channel_id else ctx.channel
    e = make_embed("Suggestion", f"{text}\n\n-# Suggested by {ctx.author.mention}")
    msg = await channel.send(embed=e)
    for emoji in ("👍", "👎"):
        try: await msg.add_reaction(emoji)
        except discord.HTTPException: pass
    if channel != ctx.channel:
        try: await ctx.message.delete()
        except discord.HTTPException: pass

@bot.command()
@commands.has_permissions(manage_guild=True)
async def starboard(ctx, channel: discord.TextChannel = None, threshold: int = 3):
    if not channel:
        return await ctx.send(embed=make_embed("starboard", f"use `{PREFIX}starboard #channel [threshold]`."))
    threshold=max(1,min(threshold,20)); guild_cfg(ctx.guild.id)["starboard_channel"]=channel.id; guild_cfg(ctx.guild.id)["starboard_threshold"]=threshold; save_ultimate_config()
    await ctx.send(embed=make_embed("starboard", f"starboard set to {channel.mention} at `{threshold}` reactions."))

@bot.command()
async def countdown(ctx, seconds: int = 10):
    seconds=max(1,min(seconds,60))
    msg=await ctx.send(embed=make_embed("countdown", f"starting in **{seconds}** seconds."))
    for left in range(seconds-1, -1, -1):
        await asyncio.sleep(1)
        if left == 0:
            await msg.edit(embed=make_embed("countdown", "**done.**"))
        else:
            await msg.edit(embed=make_embed("countdown", f"**{left}** seconds remaining."))

@bot.command()
async def dice(ctx, count: int = 1, sides: int = 6):
    count=max(1,min(count,20)); sides=max(2,min(sides,1000))
    rolls=[random.randint(1,sides) for _ in range(count)]
    await ctx.send(embed=make_embed("dice", f"**Rolls**\n" + " · ".join(f"`{x}`" for x in rolls) + f"\n\n**Total**\n`{sum(rolls)}`"))

@bot.command()
async def randomuser(ctx, role: discord.Role = None):
    pool=[m for m in ctx.guild.members if not m.bot and (role is None or role in m.roles)]
    if not pool: return await ctx.send(embed=make_embed("random user", "no matching members."))
    member=random.choice(pool)
    await ctx.send(embed=make_embed("random user", f"selected {member.mention}."))

@bot.command()
async def serverage(ctx):
    age=int(time.time()-ctx.guild.created_at.timestamp())
    await ctx.send(embed=make_embed("server age", f"created <t:{int(ctx.guild.created_at.timestamp())}:F>\n\nthat was <t:{int(ctx.guild.created_at.timestamp())}:R>.\n\n**Age**\n`{age//86400}` days"))

@bot.command(aliases=["botstatus"])
@commands.is_owner()
async def status(ctx, *, text: str = "online"):
    await bot.change_presence(activity=discord.Game(name=text[:128]))
    await ctx.send(embed=make_embed("bot status", f"activity changed to `{text[:128]}`."))

@bot.command()
@commands.is_owner()
async def stream(ctx, *, text: str):
    await bot.change_presence(activity=discord.Streaming(name=text[:128], url="https://twitch.tv/"))
    await ctx.send(embed=make_embed("bot status", f"streaming activity changed to `{text[:128]}`."))

@bot.command()
@commands.is_owner()
async def maintenance(ctx, action="status"):
    action=action.lower(); ultimate_config["maintenance"]= action == "on" if action in {"on","off"} else ultimate_config.get("maintenance",False)
    if action in {"on","off"}: save_ultimate_config()
    await ctx.send(embed=make_embed("maintenance", f"**Enabled:** `{ultimate_config.get('maintenance',False)}`"))

@bot.command()
async def uptimeinfo(ctx):
    seconds=int(time.time()-start_time); d,seconds=divmod(seconds,86400); h,seconds=divmod(seconds,3600); m,s=divmod(seconds,60)
    await ctx.send(embed=make_embed("uptime", f"`{d}d {h}h {m}m {s}s`\n\n**Latency**\n`{round(bot.latency*1000)}ms`"))

@bot.command()
async def permissionscheck(ctx, member: discord.Member = None):
    member=member or ctx.author; p=member.guild_permissions
    names=[name.replace('_',' ') for name in ("administrator","manage guild","manage channels","manage roles","manage messages","moderate members","kick members","ban members","mention everyone") if getattr(p,name.replace(' ','_'),False)]
    await ctx.send(embed=make_embed("permissions", "\n".join(f"• `{x}`" for x in names) if names else "no major management permissions."))

@bot.command()
async def timestamp(ctx, unix: int = None):
    unix = unix or int(time.time())
    await ctx.send(embed=make_embed("timestamp", f"`{unix}`\n\n<t:{unix}:F>\n<t:{unix}:R>\n<t:{unix}:D>"))


# =========================
# V53 COMMUNITY / MANAGEMENT PACK
# =========================
# Persistent configuration lives inside the existing ultimate_config.json so this
# expansion does not create a pile of extra files.

def v53cfg(gid):
    cfg = guild_cfg(gid)
    cfg.setdefault("logs", {})
    cfg.setdefault("aliases", {})
    cfg.setdefault("disabled_commands", {})
    cfg.setdefault("gallery_channels", [])
    cfg.setdefault("command_cooldowns", {})
    cfg.setdefault("joinlog", None)
    cfg.setdefault("leavelog", None)
    cfg.setdefault("auditlog", None)
    cfg.setdefault("automod", {"links": False, "caps": False, "spam": False, "mentions": False})
    cfg.setdefault("automod_exempt_roles", [])
    return cfg


def v53_save(gid):
    v53cfg(gid)
    save_ultimate_config()


def is_staffish(ctx):
    return bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild or role_ok(ctx.author, WARN_ROLES)))


def v53_can_manage(ctx):
    return bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild))


def v53_channel(value, ctx):
    if value is None:
        return None
    if ctx.message.channel_mentions:
        return ctx.message.channel_mentions[0]
    value = str(value).strip().replace("<#", "").replace(">", "")
    try:
        return ctx.guild.get_channel(int(value))
    except ValueError:
        return None


@bot.command(aliases=["cfg"])
async def settings(ctx, action="view", key=None, *, value=None):
    if not v53_can_manage(ctx):
        return
    cfg = v53cfg(ctx.guild.id)
    action = action.lower()
    if action in {"view", "show"}:
        logs = cfg.get("logs", {})
        automod = cfg.get("automod", {})
        join_log = f"<#{logs.get('join')}>" if logs.get("join") else "`off`"
        leave_log = f"<#{logs.get('leave')}>" if logs.get("leave") else "`off`"
        audit_log = f"<#{logs.get('audit')}>" if logs.get("audit") else "`off`"
        body = (
            f"**Prefix**\n`{PREFIX}`\n\n"
            f"**Join log**\n{join_log}\n\n"
            f"**Leave log**\n{leave_log}\n\n"
            f"**Audit log**\n{audit_log}\n\n"
            f"**Automod**\nlinks=`{automod.get('links', False)}` · caps=`{automod.get('caps', False)}` · spam=`{automod.get('spam', False)}` · mentions=`{automod.get('mentions', False)}`\n\n"
            f"**Gallery channels**\n`{len(cfg.get('gallery_channels', []))}`"
        )
        return await ctx.send(embed=make_embed("server settings", body))
    if action in {"reset"}:
        if not ctx.author.guild_permissions.administrator:
            return
        ultimate_config[str(ctx.guild.id)] = {}
        save_ultimate_config()
        return await ctx.send(embed=make_embed("settings reset", "server-specific v53 settings were reset."))
    if action in {"set", "config"} and key:
        allowed = {"joinlog": "join", "leavelog": "leave", "auditlog": "audit"}
        if key.lower() in allowed:
            channel = v53_channel(value, ctx)
            if not channel or not isinstance(channel, discord.TextChannel):
                return await ctx.send(embed=make_embed("settings", f"usage: `{PREFIX}settings set {key} #channel`"))
            cfg["logs"][allowed[key.lower()]] = channel.id
            v53_save(ctx.guild.id)
            return await ctx.send(embed=make_embed("settings updated", f"{key.lower()} → {channel.mention}"))
    return await ctx.send(embed=make_embed("settings", f"use `{PREFIX}settings` to view configuration."))


@bot.command(aliases=["joinlogs"])
async def joinlog(ctx, channel: discord.TextChannel = None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id)
    if channel is None:
        cid = cfg["logs"].get("join")
        return await ctx.send(embed=make_embed("join log", f"channel: {f'<#{cid}>' if cid else '`off`'}"))
    cfg["logs"]["join"] = channel.id; v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("join log", f"join events will be logged in {channel.mention}."))


@bot.command(aliases=["leavelogs"])
async def leavelog(ctx, channel: discord.TextChannel = None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id)
    if channel is None:
        cid = cfg["logs"].get("leave")
        return await ctx.send(embed=make_embed("leave log", f"channel: {f'<#{cid}>' if cid else '`off`'}"))
    cfg["logs"]["leave"] = channel.id; v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("leave log", f"leave events will be logged in {channel.mention}."))


@bot.command(aliases=["auditlogs"])
async def auditlog(ctx, channel: discord.TextChannel = None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id)
    if channel is None:
        cid = cfg["logs"].get("audit")
        return await ctx.send(embed=make_embed("audit log", f"channel: {f'<#{cid}>' if cid else '`off`'}"))
    cfg["logs"]["audit"] = channel.id; v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("audit log", f"moderation and security events will be logged in {channel.mention}."))


@bot.command(aliases=["leave"])
async def goodbye(ctx, action="status", *, text=None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id)
    good = cfg.setdefault("goodbye", {"enabled": False, "channel": None, "message": "goodbye {username} — we'll miss you."})
    action = action.lower()
    if action in {"on", "enable"}:
        good["enabled"] = True
    elif action in {"off", "disable"}:
        good["enabled"] = False
    elif action in {"channel", "setchannel"}:
        channel = v53_channel(text, ctx)
        if not channel: return await ctx.send(embed=make_embed("goodbye", f"usage: `{PREFIX}goodbye channel #channel`"))
        good["channel"] = channel.id; good["enabled"] = True
    elif action in {"message", "text"}:
        if not text: return await ctx.send(embed=make_embed("goodbye", f"usage: `{PREFIX}goodbye message goodbye {{username}}`"))
        good["message"] = text[:1800]; good["enabled"] = True
    elif action == "reset":
        cfg.pop("goodbye", None); v53_save(ctx.guild.id)
        return await ctx.send(embed=make_embed("goodbye", "configuration reset."))
    elif action == "status":
        channel = ctx.guild.get_channel(good.get("channel")) if good.get("channel") else None
        return await ctx.send(embed=make_embed("goodbye", f"**Enabled**\n`{good.get('enabled', False)}`\n\n**Channel**\n{channel.mention if channel else '`server system channel`'}\n\n**Message**\n{good.get('message')}"))
    v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("goodbye updated", "the goodbye configuration was updated."))


@bot.command()
async def gallery(ctx, action="status", channel: discord.TextChannel = None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id)
    chans = set(int(x) for x in cfg.get("gallery_channels", []))
    action = action.lower()
    if action in {"add", "on", "enable"}:
        channel = channel or ctx.channel
        chans.add(channel.id)
    elif action in {"remove", "off", "disable"}:
        channel = channel or ctx.channel
        chans.discard(channel.id)
    elif action == "list":
        return await ctx.send(embed=make_embed("gallery channels", "\n".join(f"• <#{x}>" for x in sorted(chans)) or "none configured."))
    else:
        return await ctx.send(embed=make_embed("gallery", f"use `{PREFIX}gallery add #channel`, `{PREFIX}gallery remove #channel`, or `{PREFIX}gallery list`."))
    cfg["gallery_channels"] = sorted(chans); v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("gallery", f"{channel.mention} is now {'a gallery channel' if channel.id in chans else 'not a gallery channel'}."))


@bot.command(aliases=["automod"])
async def protection(ctx, action="status", feature=None, value=None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id); auto = cfg["automod"]
    action = action.lower()
    if action in {"status", "show"}:
        return await ctx.send(embed=make_embed("protection", "\n".join(f"**{k.title()}** · `{v}`" for k,v in auto.items())))
    if action in {"on", "enable", "off", "disable"} and feature:
        key = feature.lower()
        aliases = {"link":"links", "links":"links", "caps":"caps", "spam":"spam", "mention":"mentions", "mentions":"mentions"}
        key = aliases.get(key)
        if key is None: return await ctx.send(embed=make_embed("protection", "features: `links`, `caps`, `spam`, `mentions`."))
        auto[key] = action in {"on", "enable"}
        v53_save(ctx.guild.id)
        return await ctx.send(embed=make_embed("protection updated", f"`{key}` → `{auto[key]}`"))
    return await ctx.send(embed=make_embed("protection", f"usage: `{PREFIX}protection <on|off> <links|caps|spam|mentions>`"))


@bot.command(aliases=["aliasadd"])
async def alias(ctx, action="list", shortcut=None, *, command=None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id); aliases = cfg["aliases"]
    action = action.lower()
    if action == "list":
        return await ctx.send(embed=make_embed("aliases", "\n".join(f"`{k}` → `{v}`" for k,v in sorted(aliases.items())) or "no custom aliases."))
    if action in {"add", "set"}:
        if not shortcut or not command: return await ctx.send(embed=make_embed("alias", f"usage: `{PREFIX}alias add shortcut command`"))
        target = bot.get_command(command.split()[0].lower())
        if not target: return await ctx.send(embed=make_embed("alias", "that command does not exist."))
        shortcut = shortcut.lower().strip().lstrip(PREFIX)
        if bot.get_command(shortcut): return await ctx.send(embed=make_embed("alias", "that name is already a bot command."))
        aliases[shortcut] = target.qualified_name; v53_save(ctx.guild.id)
        return await ctx.send(embed=make_embed("alias added", f"`{PREFIX}{shortcut}` → `{PREFIX}{target.qualified_name}`"))
    if action in {"remove", "delete"}:
        if not shortcut: return await ctx.send(embed=make_embed("alias", f"usage: `{PREFIX}alias remove shortcut`"))
        aliases.pop(shortcut.lower().lstrip(PREFIX), None); v53_save(ctx.guild.id)
        return await ctx.send(embed=make_embed("alias removed", f"removed `{PREFIX}{shortcut}`."))
    if action == "reset":
        aliases.clear(); v53_save(ctx.guild.id)
        return await ctx.send(embed=make_embed("aliases reset", "all custom aliases were removed."))
    return await ctx.send(embed=make_embed("alias", f"usage: `{PREFIX}alias <add|remove|list|reset> ...`"))


@bot.command(aliases=["disabled"])
async def commandtoggle(ctx, action="list", command_name=None):
    if not v53_can_manage(ctx): return
    cfg = v53cfg(ctx.guild.id); disabled = cfg["disabled_commands"]
    action = action.lower()
    if action == "list":
        lines = [f"`{k}` · {', '.join(f'<#{x}>' for x in v) if v else '`all channels`'}" for k,v in sorted(disabled.items())]
        return await ctx.send(embed=make_embed("disabled commands", "\n".join(lines) or "nothing disabled."))
    if not command_name: return await ctx.send(embed=make_embed("command toggle", f"usage: `{PREFIX}commandtoggle <on|off|list> command`"))
    name = command_name.lower().lstrip(PREFIX)
    if not bot.get_command(name): return await ctx.send(embed=make_embed("command toggle", "that command does not exist."))
    channels = set(int(x) for x in disabled.get(name, []))
    if action in {"off", "disable"}:
        channels.add(ctx.channel.id); disabled[name] = sorted(channels)
        message = f"`{PREFIX}{name}` is disabled in {ctx.channel.mention}."
    elif action in {"on", "enable"}:
        channels.discard(ctx.channel.id)
        if channels: disabled[name] = sorted(channels)
        else: disabled.pop(name, None)
        message = f"`{PREFIX}{name}` is enabled in {ctx.channel.mention}."
    else:
        return await ctx.send(embed=make_embed("command toggle", f"usage: `{PREFIX}commandtoggle <on|off|list> command`"))
    v53_save(ctx.guild.id); await ctx.send(embed=make_embed("command toggle", message))


@bot.command()
async def count(ctx, role: discord.Role = None):
    if role is None:
        return await ctx.send(embed=make_embed("count", f"members: `{ctx.guild.member_count or len(ctx.guild.members)}`"))
    await ctx.send(embed=make_embed("role count", f"{role.mention}\n\n`{sum(1 for m in ctx.guild.members if role in m.roles)}` members"))


@bot.command(aliases=["toproles"])
async def rolelist(ctx):
    roles = [r for r in ctx.guild.roles if not r.is_default()]
    roles.sort(key=lambda r: (r.position, r.id), reverse=True)
    lines = [f"`{i:02}` {r.mention} · `{sum(1 for m in ctx.guild.members if r in m.roles)}`" for i,r in enumerate(roles[:25], 1)]
    await ctx.send(embed=make_embed("role overview", "\n".join(lines) or "no roles."))


@bot.command(aliases=["channels"])
async def channelstatsall(ctx):
    counts = {"text": sum(isinstance(c, discord.TextChannel) for c in ctx.guild.channels), "voice": sum(isinstance(c, discord.VoiceChannel) for c in ctx.guild.channels), "category": sum(isinstance(c, discord.CategoryChannel) for c in ctx.guild.channels), "forum": sum(isinstance(c, discord.ForumChannel) for c in ctx.guild.channels)}
    await ctx.send(embed=make_embed("channel overview", "\n".join(f"**{k.title()}** · `{v}`" for k,v in counts.items())))


@bot.command()
async def memberstats(ctx):
    humans = sum(not m.bot for m in ctx.guild.members); bots = sum(m.bot for m in ctx.guild.members); online = sum(bool(m.status != discord.Status.offline) for m in ctx.guild.members)
    await ctx.send(embed=make_embed("member statistics", f"**Total** · `{len(ctx.guild.members)}`\n**Humans** · `{humans}`\n**Bots** · `{bots}`\n**Online / idle / dnd** · `{online}`"))


@bot.command(aliases=["userinfoid"])
async def usersearch(ctx, user_id: int):
    member = ctx.guild.get_member(user_id)
    if not member:
        try: member = await bot.fetch_user(user_id)
        except discord.HTTPException: return await ctx.send(embed=make_embed("user search", "that user could not be found."))
    await ctx.send(embed=make_embed("user search", f"**User**\n{member.mention if hasattr(member, 'mention') else member}\n\n**ID**\n`{member.id}`"))


@bot.command(aliases=["topicset"])
async def settopic(ctx, *, topic=None):
    if not ctx.author.guild_permissions.manage_channels: return
    if topic is None: return await ctx.send(embed=make_embed("topic", f"current topic: {ctx.channel.topic or '`none`'}"))
    await ctx.channel.edit(topic=topic[:1024], reason=f"Topic changed by {ctx.author}")
    await ctx.send(embed=make_embed("topic updated", "channel topic updated."))


@bot.command()
async def clone(ctx, channel: discord.TextChannel = None, *, name=None):
    if not has_manage_server(ctx): return
    channel = channel or ctx.channel
    try:
        new = await channel.clone(name=name or channel.name, reason=f"Cloned by {ctx.author}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("clone", "Discord rejected the channel clone."))
    await ctx.send(embed=make_embed("channel cloned", f"created {new.mention}."))


@bot.command(aliases=["rmrole"])
async def massrole(ctx, action="add", role: discord.Role = None):
    if not has_manage_roles(ctx) or role is None: return
    if role >= ctx.guild.me.top_role or role.is_default() or role.managed:
        return await ctx.send(embed=make_embed("mass role", "I cannot manage that role."))
    members = [m for m in ctx.guild.members if not m.bot]
    changed = 0
    for member in members:
        try:
            if action.lower() in {"add", "give"} and role not in member.roles:
                await member.add_roles(role, reason=f"Mass role by {ctx.author}"); changed += 1
            elif action.lower() in {"remove", "take"} and role in member.roles:
                await member.remove_roles(role, reason=f"Mass role by {ctx.author}"); changed += 1
        except discord.HTTPException:
            pass
        if changed and changed % 10 == 0: await asyncio.sleep(0.5)
    await ctx.send(embed=make_embed("mass role", f"changed `{changed}` members."))


@bot.command(aliases=["remindme"])
async def timer(ctx, duration: str, *, text="timer finished"):
    seconds = parse_duration(duration)
    if not seconds or seconds < 1 or seconds > 604800:
        return await ctx.send(embed=make_embed("timer", "duration must be between 1 second and 7 days."))
    await ctx.send(embed=make_embed("timer set", f"I'll remind you <t:{int(time.time()+seconds)}:R>."))
    await asyncio.sleep(seconds)
    try: await ctx.author.send(embed=make_embed("timer", text[:1800]))
    except discord.HTTPException: pass


@bot.command(aliases=["sayembed"])
async def embed(ctx, *, text):
    if not v53_can_manage(ctx): return
    e = make_embed(None, text[:4000])
    try: await ctx.message.delete()
    except discord.HTTPException: pass
    await ctx.send(embed=e)


@bot.command()
async def cleanbots(ctx, amount: int = 100):
    if not ctx.author.guild_permissions.manage_messages: return
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1, check=lambda m: m.author.bot)
    await ctx.send(embed=make_embed("bot cleanup", f"deleted `{max(0, len(deleted)-1)}` bot messages."), delete_after=4)


@bot.command()
async def invitecheck(ctx):
    if not ctx.author.guild_permissions.manage_guild: return
    try:
        invites = await ctx.guild.invites()
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("invites", "I need Manage Server to inspect invites."))
    invites.sort(key=lambda x: x.uses or 0, reverse=True)
    lines = [f"`{i.uses or 0}` uses · `{i.code}` · {i.inviter.mention if i.inviter else 'unknown'}" for i in invites[:20]]
    await ctx.send(embed=make_embed("server invites", "\n".join(lines) or "no invites found."))


@bot.command(aliases=["modconfig"])
async def logconfig(ctx, action="status", channel: discord.TextChannel = None):
    if not v53_can_manage(ctx): return
    cfg=v53cfg(ctx.guild.id); logs=cfg["logs"]; action=action.lower()
    if action in {"status", "view"}:
        join_log = f"<#{logs.get('join')}>" if logs.get("join") else "`off`"
    leave_log = f"<#{logs.get('leave')}>" if logs.get("leave") else "`off`"
    audit_log = f"<#{logs.get('audit')}>" if logs.get("audit") else "`off`"
    return await ctx.send(embed=make_embed("log configuration", f"join: {join_log}\nleave: {leave_log}\naudit: {audit_log}"))
    if action not in {"join", "leave", "audit"} or not channel:
        return await ctx.send(embed=make_embed("log configuration", f"usage: `{PREFIX}logconfig <join|leave|audit> #channel`"))
    logs[action]=channel.id; v53_save(ctx.guild.id)
    await ctx.send(embed=make_embed("log configuration", f"{action} logs → {channel.mention}"))


# Custom aliases are dispatched before normal command parsing. This keeps aliases
# guild-local and supports arguments, while leaving the normal prefix untouched.

# BLEEED expansion: extra lightweight information, utility and moderation tools.
@bot.command()
async def bots(ctx):
    n=sum(m.bot for m in ctx.guild.members)
    await ctx.send(embed=result_embed("Bots", "Count", f"**{n}**", extra=[("Share", f"{n/max(ctx.guild.member_count or 1,1)*100:.1f}%")]))

@bot.command()
async def humans(ctx):
    n=sum(not m.bot for m in ctx.guild.members)
    await ctx.send(embed=result_embed("Humans", "Count", f"**{n}**", extra=[("Share", f"{n/max(ctx.guild.member_count or 1,1)*100:.1f}%")]))

@bot.command(aliases=["memberroles"])
async def userroles(ctx, member:discord.Member=None):
    member=member or ctx.author; roles=[r for r in reversed(member.roles) if r != ctx.guild.default_role]
    await ctx.send(embed=make_embed("member roles", f"**User**\n{member.mention}\n\n**Roles**\n"+(" ".join(r.mention for r in roles) or "`none`")))

@bot.command()
async def rolemembers(ctx, role:discord.Role):
    ms=list(role.members); lines=[f"`{i:02}` {m.mention}" for i,m in enumerate(ms[:50],1)]
    await ctx.send(embed=make_embed("role members", f"**Role** {role.mention}\n\n"+("\n".join(lines) or "`none`")+(f"\n\n-# Showing {min(50,len(ms))}/{len(ms)}" if len(ms)>50 else "")))

@bot.command()
async def channelcount(ctx):
    t=len(ctx.guild.text_channels); v=len(ctx.guild.voice_channels); c=len(ctx.guild.categories)
    await ctx.send(embed=make_embed("channel count", f"**Text** `{t}`\n**Voice** `{v}`\n**Categories** `{c}`\n**Total** `{t+v+c}`"))

@bot.command()
async def categorycount(ctx):
    await ctx.send(embed=result_embed("Category Count","Categories",f"**{len(ctx.guild.categories)}**"))

@bot.command()
async def textchannels(ctx):
    await ctx.send(embed=make_embed("text channels", "\n".join(f"`{i:02}` {c.mention}" for i,c in enumerate(ctx.guild.text_channels[:75],1)) or "`none`"))

@bot.command()
async def voicechannels(ctx):
    await ctx.send(embed=make_embed("voice channels", "\n".join(f"`{i:02}` **{c.name}** · `{len(c.members)}`" for i,c in enumerate(ctx.guild.voice_channels[:75],1)) or "`none`"))

@bot.command()
async def servercreated(ctx):
    d=ctx.guild.created_at; await ctx.send(embed=result_embed("Server Created","Date",f"<t:{int(d.timestamp())}:F>",extra=[("Relative",f"<t:{int(d.timestamp())}:R>")]))

@bot.command()
async def memberjoined(ctx, member:discord.Member=None):
    member=member or ctx.author; d=member.joined_at
    await ctx.send(embed=result_embed("Member Joined","User",member.mention,extra=[("Date",f"<t:{int(d.timestamp())}:F>"),("Relative",f"<t:{int(d.timestamp())}:R>")]) if d else make_embed("member joined","No join date is available."))

@bot.command()
async def accountage(ctx, member:discord.Member=None):
    member=member or ctx.author; d=member.created_at
    await ctx.send(embed=result_embed("Account Age","User",member.mention,extra=[("Created",f"<t:{int(d.timestamp())}:F>"),("Relative",f"<t:{int(d.timestamp())}:R>")]))

@bot.command()
async def serverbanner(ctx):
    if not ctx.guild.banner: return await ctx.send(embed=make_embed("server banner","This server does not have a banner."))
    e=make_embed("server banner",f"[Open banner]({ctx.guild.banner.url})"); e.set_image(url=ctx.guild.banner.url); await ctx.send(embed=e)

@bot.command()
async def emojiinfo(ctx, emoji:discord.Emoji):
    await ctx.send(embed=make_embed("emoji info",f"**Name** `{emoji.name}`\n**ID** `{emoji.id}`\n**Animated** `{emoji.animated}`\n**Mention** `{emoji}`"))

@bot.command()
async def stickerinfo(ctx, sticker:discord.GuildSticker):
    await ctx.send(embed=make_embed("sticker info",f"**Name** `{sticker.name}`\n**ID** `{sticker.id}`\n**Format** `{sticker.format}`\n**Description** {sticker.description or '`none`'}"))

@bot.command()
async def snowflake(ctx, value:int):
    try: d=discord.utils.snowflake_time(value)
    except (OverflowError,ValueError): return await ctx.send(embed=make_embed("snowflake","Invalid Discord snowflake."))
    await ctx.send(embed=result_embed("Snowflake","ID",f"`{value}`",extra=[("Created",f"<t:{int(d.timestamp())}:F>"),("Relative",f"<t:{int(d.timestamp())}:R>")]))

@bot.command()
async def hex(ctx, value:str=None):
    value=(value or "").lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}',value): return await ctx.send(embed=make_embed("hex",f"Use `{PREFIX}hex #5865F2`"))
    rgb=tuple(int(value[i:i+2],16) for i in (0,2,4)); await ctx.send(embed=result_embed("Hex","Color",f"`#{value.upper()}`",extra=[("RGB",f"`{rgb[0]}, {rgb[1]}, {rgb[2]}`"),("Integer",f"`{int(value,16)}`")]))

@bot.command()
async def randomchoice(ctx, *, choices):
    opts=[x.strip() for x in choices.split('|') if x.strip()]
    if len(opts)<2: return await ctx.send(embed=make_embed("random choice",f"Use `{PREFIX}randomchoice one | two | three`"))
    await ctx.send(embed=result_embed("Random Choice","Selected",f"**{random.choice(opts)}**"))

@bot.command()
async def randommember(ctx, role:discord.Role=None):
    pool=list(role.members) if role else [m for m in ctx.guild.members if not m.bot]
    if not pool: return await ctx.send(embed=make_embed("random member","No eligible members."))
    await ctx.send(embed=result_embed("Random Member","Selected",random.choice(pool).mention))

@bot.command()
async def rolepermissions(ctx, role:discord.Role):
    p=[n.replace('_',' ') for n,v in role.permissions if v]
    await ctx.send(embed=make_embed("role permissions",f"**Role** {role.mention}\n\n"+(' · '.join(f'`{x}`' for x in p) or '`none`')))

@bot.command()
async def channelpermissions(ctx, channel:discord.TextChannel=None, member:discord.Member=None):
    channel=channel or ctx.channel; member=member or ctx.author; p=channel.permissions_for(member)
    enabled=[n.replace('_',' ') for n,v in p if v]
    await ctx.send(embed=make_embed("channel permissions",f"**Channel** {channel.mention}\n**User** {member.mention}\n\n"+(' · '.join(f'`{x}`' for x in enabled) or '`none`')))

@bot.command()
async def afklist(ctx):
    ids={m.id for m in ctx.guild.members}; lines=[]
    for uid,data in afk_data.items():
        if uid in ids and ctx.guild.get_member(uid): lines.append(f"{ctx.guild.get_member(uid).mention} · {data.get('reason','AFK')}")
    await ctx.send(embed=make_embed("afk list","\n".join(lines[:50]) or "`no members are currently AFK`"))

@bot.command()
async def pollresults(ctx, message_id:int):
    try: msg=await ctx.channel.fetch_message(message_id)
    except (discord.NotFound,discord.Forbidden,discord.HTTPException): return await ctx.send(embed=make_embed("poll results","I couldn't fetch that message."))
    lines=[f"{r.emoji} `{r.count}`" for r in msg.reactions]
    await ctx.send(embed=make_embed("poll results","\n".join(lines) or "`no reactions`"))

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purgebots(ctx, amount:int=50):
    amount=max(1,min(amount,100))
    if not bot_can(ctx,'manage_messages'): return await ctx.send(embed=make_embed("bot permission missing","I need **Manage Messages**."))
    deleted=await ctx.channel.purge(limit=amount,check=lambda m:m.author.bot)
    await ctx.send(embed=action_embed(f"Removed {len(deleted)} bot messages.",removed=True),delete_after=3)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purgeuser(ctx, member:discord.Member, amount:int=50):
    amount=max(1,min(amount,100))
    if not bot_can(ctx,'manage_messages'): return await ctx.send(embed=make_embed("bot permission missing","I need **Manage Messages**."))
    deleted=await ctx.channel.purge(limit=amount,check=lambda m:m.author.id==member.id)
    await ctx.send(embed=action_embed(f"Removed {len(deleted)} messages from {member.mention}.",removed=True),delete_after=3)

@bot.command()
async def calc(ctx, *, expression):
    import ast as _ast
    allowed=(_ast.Expression,_ast.BinOp,_ast.UnaryOp,_ast.Add,_ast.Sub,_ast.Mult,_ast.Div,_ast.Mod,_ast.Pow,_ast.USub,_ast.UAdd,_ast.FloorDiv,_ast.Constant)
    try:
        tree=_ast.parse(expression,mode='eval')
        if any(not isinstance(n,allowed) for n in _ast.walk(tree)): raise ValueError
        if any(isinstance(n,_ast.Constant) and (not isinstance(n.value,(int,float)) or isinstance(n.value,bool)) for n in _ast.walk(tree)): raise ValueError
        result=eval(compile(tree,'<calc>','eval'),{'__builtins__':{}},{})
        if isinstance(result,float) and (result!=result or abs(result)==float('inf')): raise ValueError
    except Exception: return await ctx.send(embed=make_embed("calculator",f"Invalid expression. Example: `{PREFIX}calc (12 + 8) * 3`"))
    await ctx.send(embed=result_embed("Calculator","Expression",f"`{expression}`",extra=[("Result",f"**{result}**")]))

@bot.command()
async def unix(ctx, timestamp:int=None):
    timestamp=timestamp or int(time.time())
    try: d=datetime.fromtimestamp(timestamp,tz=timezone.utc)
    except (OverflowError,OSError,ValueError): return await ctx.send(embed=make_embed("unix","Invalid timestamp."))
    await ctx.send(embed=make_embed("unix",f"**Unix** `{timestamp}`\n\n**Discord** `<t:{timestamp}:F>`\n\n**Relative** `<t:{timestamp}:R>`\n\n**UTC** `{d:%Y-%m-%d %H:%M:%S}`"))

@bot.command()
async def channelage(ctx, channel:discord.TextChannel=None):
    channel=channel or ctx.channel; d=channel.created_at
    await ctx.send(embed=result_embed("Channel Age","Channel",channel.mention,extra=[("Created",f"<t:{int(d.timestamp())}:F>"),("Relative",f"<t:{int(d.timestamp())}:R>")]))

@bot.command()
async def roleage(ctx, role:discord.Role):
    d=role.created_at; await ctx.send(embed=result_embed("Role Age","Role",role.mention,extra=[("Created",f"<t:{int(d.timestamp())}:F>"),("Relative",f"<t:{int(d.timestamp())}:R>")]))

@bot.command()
async def serverowner(ctx):
    owner=ctx.guild.owner
    await ctx.send(embed=result_embed("Server Owner","Owner",owner.mention,extra=[("ID",f"`{owner.id}`")]) if owner else make_embed("server owner","Owner unavailable."))


# =========================
# BLEEED SERVER / MODERATION / SECURITY EXPANSION
# =========================

@bot.command()
async def memberinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in reversed(member.roles) if r != ctx.guild.default_role]
    await ctx.send(embed=make_embed("member information", f"**User**\n{member.mention} · `{member.id}`\n\n**Account**\nCreated <t:{int(member.created_at.timestamp())}:R>\nJoined <t:{int(member.joined_at.timestamp())}:R>\nBot `{member.bot}`\n\n**Roles**\n{' '.join(roles) or '`none`'}"))

@bot.command()
async def categorylist(ctx):
    lines = [f"`{i:02}` {c.mention} · `{len(c.channels)}` channels" for i,c in enumerate(ctx.guild.categories, 1)]
    await ctx.send(embed=make_embed("categories", "\n".join(lines) or "`none`"))

@bot.command()
async def threadlist(ctx):
    threads = list(ctx.guild.threads)
    lines = [f"`{i:02}` {t.mention} · {t.parent.mention if t.parent else '`no parent`'}" for i,t in enumerate(threads[:50],1)]
    await ctx.send(embed=make_embed("active threads", "\n".join(lines) or "`none`"))

@bot.command()
async def forumchannels(ctx):
    forums = [c for c in ctx.guild.channels if isinstance(c, discord.ForumChannel)]
    await ctx.send(embed=make_embed("forum channels", "\n".join(f"`{i:02}` {c.mention}" for i,c in enumerate(forums,1)) or "`none`"))

@bot.command()
async def serverfeatures(ctx):
    features = sorted(str(x).replace('_',' ').lower() for x in ctx.guild.features)
    await ctx.send(embed=make_embed("server features", " · ".join(f"`{x}`" for x in features) or "`none`"))

@bot.command()
async def boosters(ctx):
    members = [m for m in ctx.guild.members if m.premium_since]
    lines = [f"`{i:02}` {m.mention} · <t:{int(m.premium_since.timestamp())}:R>" for i,m in enumerate(sorted(members,key=lambda x:x.premium_since or datetime.min, reverse=True)[:50],1)]
    await ctx.send(embed=make_embed("boosters", "\n".join(lines) or "`no boosters`"))

@bot.command()
async def serverroles(ctx):
    roles = [r for r in reversed(ctx.guild.roles) if not r.is_default()]
    lines = [f"`{i:02}` {r.mention} · `{len(r.members)}`" for i,r in enumerate(roles[:50],1)]
    await ctx.send(embed=make_embed("server roles", "\n".join(lines) or "`none`"))

@bot.command()
async def memberpermissions(ctx, member: discord.Member = None):
    member = member or ctx.author
    p = member.guild_permissions
    enabled = [name.replace('_',' ') for name,value in p if value]
    await ctx.send(embed=make_embed("member permissions", f"**User** {member.mention}\n\n" + (' · '.join(f'`{x}`' for x in enabled) or '`none`')))

@bot.command(name="renameserver")
@commands.has_permissions(manage_guild=True)
async def renameserver(ctx, *, name):
    name = name[:100].strip()
    if not name: return await ctx.send(embed=make_embed("rename", "enter a server name."))
    try:
        await ctx.guild.edit(name=name, reason=f"Server renamed by {ctx.author}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("rename", "Discord rejected the server rename."))
    await ctx.send(embed=action_embed(f"Renamed the server to **{discord.utils.escape_markdown(name)}**", added=True))

@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmodeall(ctx, seconds: int = 0):
    if seconds < 0 or seconds > 21600:
        return await ctx.send(embed=make_embed("slowmode all", "seconds must be between 0 and 21600."))
    changed = 0
    for channel in ctx.guild.text_channels:
        if not channel.permissions_for(ctx.guild.me).manage_channels:
            continue
        try:
            await channel.edit(slowmode_delay=seconds, reason=f"Slowmode all by {ctx.author}"); changed += 1
        except discord.HTTPException: pass
    await ctx.send(embed=make_embed("slowmode all", f"updated `{changed}` text channels to `{seconds}s`."))

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlockall(ctx):
    changed=0
    overwrite=ctx.guild.default_role
    for channel in ctx.guild.text_channels:
        if not channel.permissions_for(ctx.guild.me).manage_channels: continue
        try:
            await channel.set_permissions(overwrite, send_messages=True, reason=f"Unlock all by {ctx.author}"); changed+=1
        except discord.HTTPException: pass
    await ctx.send(embed=action_embed(f"Unlocked `{changed}` text channels.", added=True))

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lockall(ctx):
    changed=0
    overwrite=ctx.guild.default_role
    for channel in ctx.guild.text_channels:
        if not channel.permissions_for(ctx.guild.me).manage_channels: continue
        try:
            await channel.set_permissions(overwrite, send_messages=False, reason=f"Lock all by {ctx.author}"); changed+=1
        except discord.HTTPException: pass
    await ctx.send(embed=action_embed(f"Locked `{changed}` text channels.", removed=True))

@bot.command()
async def modstats(ctx, member: discord.Member = None):
    member = member or ctx.author
    entries = modlog_data[ctx.guild.id][member.id]
    counts = defaultdict(int)
    for e in entries: counts[e.get('action','Unknown')] += 1
    body = '\n'.join(f"**{k}** · `{v}`" for k,v in sorted(counts.items())) or '`no recorded cases`'
    await ctx.send(embed=make_embed("moderation statistics", f"**User** {member.mention}\n\n{body}"))

@bot.command()
async def modrecent(ctx, amount: int = 10):
    amount=max(1,min(amount,25)); rows=[]
    users=modlog_data[ctx.guild.id]
    for uid, entries in users.items():
        for e in entries: rows.append((e.get('timestamp',0),uid,e))
    rows.sort(reverse=True,key=lambda x:x[0])
    lines=[]
    for ts,uid,e in rows[:amount]:
        member=ctx.guild.get_member(uid); target=member.mention if member else f'`{uid}`'
        lines.append(f"`{e.get('action','?')}` · {target} · <t:{int(ts)}:R>")
    await ctx.send(embed=make_embed("recent moderation", '\n'.join(lines) or '`no cases recorded`'))

@bot.command()
@commands.has_permissions(moderate_members=True)
async def deafen(ctx, member: discord.Member, *, reason="no reason provided"):
    if not target_ok(ctx, member): return await ctx.send(embed=make_embed("cannot deafen member", "the target is above your or my highest role."))
    if not member.voice: return await ctx.send(embed=make_embed("deafen", "that member is not in a voice channel."))
    try: await member.edit(deafen=True, reason=reason)
    except discord.HTTPException: return await ctx.send(embed=make_embed("deafen failed", "Discord rejected the action."))
    record_modlog(ctx.guild, member, "Deafen", ctx.author, reason)
    await ctx.send(embed=action_embed(f"Deafened {member.mention}.", added=True))

@bot.command()
@commands.has_permissions(moderate_members=True)
async def undeafen(ctx, member: discord.Member):
    if not target_ok(ctx, member): return await ctx.send(embed=make_embed("cannot undeafen member", "the target is above your or my highest role."))
    try: await member.edit(deafen=False, reason=f"Undeafened by {ctx.author}")
    except discord.HTTPException: return await ctx.send(embed=make_embed("undeafen failed", "Discord rejected the action."))
    record_modlog(ctx.guild, member, "Undeafen", ctx.author, "Removed server deafen")
    await ctx.send(embed=action_embed(f"Undeafened {member.mention}.", added=True))

@bot.command()
@commands.has_permissions(move_members=True)
async def voicekick(ctx, member: discord.Member, *, reason="no reason provided"):
    if not target_ok(ctx, member): return await ctx.send(embed=make_embed("cannot voice kick", "the target is above your or my highest role."))
    if not member.voice: return await ctx.send(embed=make_embed("voice kick", "that member is not in a voice channel."))
    try: await member.move_to(None, reason=reason)
    except discord.HTTPException: return await ctx.send(embed=make_embed("voice kick failed", "Discord rejected the action."))
    record_modlog(ctx.guild, member, "Voice Kick", ctx.author, reason)
    await ctx.send(embed=action_embed(f"Disconnected {member.mention} from voice.", removed=True))

@bot.command()
async def warnlist(ctx, amount: int = 20):
    rows=[]
    for uid, entries in warning_data[ctx.guild.id].items():
        if entries: rows.append((len(entries),uid))
    rows.sort(reverse=True)
    lines=[]
    for count,uid in rows[:max(1,min(amount,50))]:
        m=ctx.guild.get_member(uid); lines.append(f"`{count}` · {m.mention if m else f'`{uid}`'}")
    await ctx.send(embed=make_embed("warning leaderboard", '\n'.join(lines) or '`no warnings recorded`'))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def raidmode(ctx, mode: str = "status"):
    mode=mode.lower()
    cfg=antiraid_config[ctx.guild.id]
    if mode in {"on","enable","strict"}: cfg["enabled"]=True
    elif mode in {"off","disable","normal"}: cfg["enabled"]=False
    elif mode not in {"status","show"}: return await ctx.send(embed=make_embed("raid mode", f"usage: `{PREFIX}raidmode <on|off|status>`"))
    await ctx.send(embed=make_embed("raid mode", f"**Enabled** `{cfg['enabled']}`\n**Threshold** `{cfg['threshold']}` joins / `{cfg['window']}s`"))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def antinukewindow(ctx, seconds: int = None):
    cfg=antinuke_config[ctx.guild.id]
    if seconds is None: return await ctx.send(embed=make_embed("antinuke window", f"current window: `{cfg['window']}s`"))
    cfg['window']=max(3,min(seconds,120))
    await ctx.send(embed=make_embed("antinuke window", f"window set to `{cfg['window']}s`."))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def antiraidwindow(ctx, seconds: int = None):
    cfg=antiraid_config[ctx.guild.id]
    if seconds is None: return await ctx.send(embed=make_embed("antiraid window", f"current window: `{cfg['window']}s`"))
    cfg['window']=max(3,min(seconds,120))
    await ctx.send(embed=make_embed("antiraid window", f"window set to `{cfg['window']}s`."))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def antinukestatus(ctx):
    a=antinuke_config[ctx.guild.id]
    await ctx.send(embed=make_embed("antinuke status", f"**Enabled** `{a['enabled']}`\n**Threshold** `{a['threshold']}`\n**Window** `{a['window']}s`\n**Action** `{a['action']}`"))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def antiraidstatus(ctx):
    a=antiraid_config[ctx.guild.id]
    await ctx.send(embed=make_embed("antiraid status", f"**Enabled** `{a['enabled']}`\n**Threshold** `{a['threshold']}`\n**Window** `{a['window']}s`"))

@bot.command()
@commands.has_permissions(manage_guild=True)
async def securityreset(ctx):
    antinuke_config[ctx.guild.id] = {"enabled":False,"threshold":3,"window":10,"action":"ban"}
    antiraid_config[ctx.guild.id] = {"enabled":False,"threshold":8,"window":10}
    filter_enabled[ctx.guild.id]=False
    filter_words[ctx.guild.id].clear()
    await ctx.send(embed=make_embed("security reset", "antinuke, antiraid, and the word filter were reset."))

CATEGORIES.extend([
    ("Server Plus", ["rename", "slowmodeall", "lockall", "unlockall", "categorylist", "threadlist", "forumchannels", "serverfeatures", "boosters", "serverroles"]),
    ("Information Plus", ["memberinfo", "countrole", "memberpermissions"]),
    ("Moderation Plus", ["modstats", "modrecent", "deafen", "undeafen", "voicekick", "warnlist"]),
    ("Antinuke", ["antinukestatus", "antinukewindow"]),
    ("Antiraid", ["raidmode", "antiraidstatus", "antiraidwindow", "securityreset"]),
])

@bot.before_invoke
async def _v53_command_gate(ctx):
    if not ctx.guild:
        return
    cfg = v53cfg(ctx.guild.id)
    disabled = cfg.get("disabled_commands", {})
    name = getattr(ctx.command, "qualified_name", "").lower()
    if name and ctx.channel.id in [int(x) for x in disabled.get(name, [])] and not ctx.author.guild_permissions.administrator:
        raise commands.CheckFailure("command disabled in this channel")


@bot.event
async def on_member_remove(member):
    cfg = v53cfg(member.guild.id)
    good = cfg.get("goodbye", {})
    if good.get("enabled"):
        channel = member.guild.get_channel(int(good.get("channel"))) if good.get("channel") else member.guild.system_channel
        if channel:
            text = str(good.get("message", "goodbye {username} — we'll miss you."))
            replacements = {"{user}": member.mention, "{mention}": member.mention, "{username}": member.name, "{displayname}": member.display_name, "{server}": member.guild.name, "{membercount}": str(member.guild.member_count or 0), "{id}": str(member.id)}
            for k,v in replacements.items(): text=text.replace(k,v)
            try: await channel.send(embed=make_embed("goodbye", text))
            except discord.HTTPException: pass
    cid = cfg.get("logs", {}).get("leave")
    channel = member.guild.get_channel(int(cid)) if cid else None
    if channel:
        try: await channel.send(embed=make_embed("member left", f"{member.mention} · `{member.id}`\n\ncreated <t:{int(member.created_at.timestamp())}:R>"))
        except discord.HTTPException: pass


@bot.event
async def on_message_edit(before, after):
    if before.guild and not before.author.bot and before.content != after.content:
        cfg=v53cfg(before.guild.id); cid=cfg.get("logs", {}).get("audit"); channel=before.guild.get_channel(int(cid)) if cid else None
        if channel:
            try: await channel.send(embed=make_embed("message edited", f"**Author** {before.author.mention}\n**Channel** {before.channel.mention}\n\n**Before**\n{before.content[:900] or '`empty`'}\n\n**After**\n{after.content[:900] or '`empty`'}\n\n[Jump to message](https://discord.com/channels/{before.guild.id}/{before.channel.id}/{after.id})"))
            except discord.HTTPException: pass

# Expanded BLEEED-style categories.
CATEGORIES.extend([
    ("Members", ["bots","humans","userroles","rolemembers","randommember","memberjoined","accountage","afklist"]),
    ("Channels", ["channelcount","categorycount","textchannels","voicechannels","channelpermissions","channelage"]),
    ("Server Tools", ["servercreated","serverbanner","serverowner","snowflake","unix"]),
    ("Role Tools", ["rolepermissions","roleage"]),
    ("Developer", ["hex","calc","randomchoice","emojiinfo","stickerinfo","pollresults"]),
    ("Moderation Plus", ["purgebots","purgeuser"]),
])

# Extra category documentation for the command browser.
CATEGORIES.extend([
    ("Management", ["memberlist", "countrole", "channelstats", "channelclone", "roleclone", "roleall", "unroleall", "lockdown", "unlockdown", "cleanup", "suggestchannel", "suggest", "starboard"]),
    ("Moderation Tools", ["modnote", "cases"]),
    ("Utility Plus", ["countdown", "dice", "randomuser", "serverage", "uptimeinfo", "permissionscheck", "timestamp"]),
    ("Owner", ["status", "stream", "maintenance"]),
])
COMMAND_INFO.update({
    "memberlist": ("List server members, optionally filtered by role.", "memberlist [role]", "memberlist @Members", []),
    "countrole": ("Count members holding a role.", "countrole @role", "countrole @Staff", ["rolecount"]),
    "channelstats": ("Show recent activity statistics for a channel.", "channelstats [channel]", "channelstats #general", []),
    "channelclone": ("Clone a server channel.", "channelclone [channel] [name]", "channelclone #general general-copy", ["clonechannel"]),
    "roleclone": ("Clone a manageable role.", "roleclone @role", "roleclone @Member", ["clonerole"]),
    "roleall": ("Give a role to matching server members.", "roleall @role", "roleall @Member", []),
    "unroleall": ("Remove a role from server members.", "unroleall @role", "unroleall @Member", []),
    "lockdown": ("Lock text channels for @everyone.", "lockdown [reason]", "lockdown raid protection", []),
    "unlockdown": ("Restore @everyone sending access in text channels.", "unlockdown", "unlockdown", []),
    "cleanup": ("Bulk-delete recent messages.", "cleanup [amount]", "cleanup 50", ["clean"]),
    "modnote": ("Store private moderation notes for a member.", "modnote <add|list|clear> @user [note]", "modnote add @user repeated spam", ["notes"]),
    "cases": ("Show a member's moderation case history.", "cases @user", "cases @user", ["history"]),
    "suggestchannel": ("Set the server suggestion channel.", "suggestchannel #channel", "suggestchannel #suggestions", ["setstarboard"]),
    "suggest": ("Send a suggestion and add voting reactions.", "suggest text", "suggest add a movie night", ["suggestion"]),
    "starboard": ("Configure the server starboard.", "starboard #channel [threshold]", "starboard #starboard 3", ["setstarboard"]),
    "countdown": ("Run a short live countdown.", "countdown [seconds]", "countdown 10", []),
    "dice": ("Roll multiple dice.", "dice [count] [sides]", "dice 2 20", []),
    "randomuser": ("Pick a random non-bot server member.", "randomuser [role]", "randomuser @Players", []),
    "serverage": ("Show how old the server is.", "serverage", "serverage", []),
    "status": ("Change bleeed's game activity. Owner only.", "status [text]", "status moderating", ["botstatus"]),
    "stream": ("Set bleeed's streaming activity. Owner only.", "stream text", "stream live now", []),
    "maintenance": ("Toggle the bot's maintenance flag. Owner only.", "maintenance <on|off|status>", "maintenance on", []),
    "uptimeinfo": ("Show uptime and latency.", "uptimeinfo", "uptimeinfo", []),
    "permissionscheck": ("Show major permissions for a member.", "permissionscheck [member]", "permissionscheck @user", []),
    "timestamp": ("Convert a Unix timestamp into Discord timestamp formats.", "timestamp [unix]", "timestamp 1760000000", []),
    "bots": ("Count bot accounts in the server.", "bots", "bots", []),
    "humans": ("Count human accounts in the server.", "humans", "humans", []),
    "userroles": ("List every role held by a member.", "userroles [member]", "userroles @user", ["memberroles"]),
    "rolemembers": ("List members who have a role.", "rolemembers <role>", "rolemembers @Staff", []),
    "channelcount": ("Show server channel totals.", "channelcount", "channelcount", []),
    "categorycount": ("Count server categories.", "categorycount", "categorycount", []),
    "textchannels": ("List text channels.", "textchannels", "textchannels", []),
    "voicechannels": ("List voice channels.", "voicechannels", "voicechannels", []),
    "servercreated": ("Show when the server was created.", "servercreated", "servercreated", []),
    "memberjoined": ("Show when a member joined.", "memberjoined [member]", "memberjoined @user", []),
    "accountage": ("Show a Discord account's age.", "accountage [member]", "accountage @user", []),
    "serverbanner": ("Show the server banner.", "serverbanner", "serverbanner", []),
    "emojiinfo": ("Show custom emoji information.", "emojiinfo <emoji>", "emojiinfo :wave:", []),
    "stickerinfo": ("Show server sticker information.", "stickerinfo <sticker>", "stickerinfo sticker", []),
    "snowflake": ("Convert a Discord snowflake to a date.", "snowflake <id>", "snowflake 123456789", []),
    "hex": ("Inspect a hexadecimal color.", "hex <hex>", "hex #5865F2", []),
    "randomchoice": ("Choose one item from a list.", "randomchoice <a | b | ...>", "randomchoice red | blue", []),
    "randommember": ("Pick a random member.", "randommember [role]", "randommember @Players", []),
    "rolepermissions": ("Show permissions enabled on a role.", "rolepermissions <role>", "rolepermissions @Staff", []),
    "channelpermissions": ("Show a member's permissions in a channel.", "channelpermissions [channel] [member]", "channelpermissions #general @user", []),
    "afklist": ("List members currently marked AFK.", "afklist", "afklist", []),
    "pollresults": ("Read reaction counts from a message.", "pollresults <message_id>", "pollresults 123456789", []),
    "purgebots": ("Delete recent bot messages.", "purgebots [amount]", "purgebots 50", []),
    "purgeuser": ("Delete recent messages from one member.", "purgeuser <member> [amount]", "purgeuser @user 25", []),
    "calc": ("Safely evaluate basic arithmetic.", "calc <expression>", "calc (12 + 8) * 3", []),
    "unix": ("Convert a Unix timestamp to Discord formats.", "unix [timestamp]", "unix 1760000000", []),
    "channelage": ("Show when a channel was created.", "channelage [channel]", "channelage #general", []),
    "roleage": ("Show when a role was created.", "roleage <role>", "roleage @Members", []),
    "serverowner": ("Show the server owner.", "serverowner", "serverowner", []),
})


@bot.event
async def on_raw_reaction_add(payload):
    if payload.guild_id is None or str(payload.emoji) != "⭐":
        return
    cfg = guild_cfg(payload.guild_id)
    channel_id = cfg.get("starboard_channel")
    threshold = int(cfg.get("starboard_threshold", 3))
    if not channel_id or payload.channel_id == channel_id:
        return
    channel = bot.get_channel(payload.channel_id)
    star_channel = bot.get_channel(channel_id)
    if not channel or not star_channel or not isinstance(channel, discord.TextChannel):
        return
    try:
        message = await channel.fetch_message(payload.message_id)
        count = sum(1 for reaction in message.reactions if str(reaction.emoji) == "⭐")
        if count < threshold:
            return
        posted = cfg.setdefault("starboard_posts", {})
        if str(message.id) in posted:
            try:
                old = await star_channel.fetch_message(int(posted[str(message.id)]))
                await old.edit(content=f"⭐ **{count}** · {message.channel.mention}", embed=old.embeds[0] if old.embeds else None)
                return
            except (discord.NotFound, discord.HTTPException):
                posted.pop(str(message.id), None)
        e = make_embed("Starboard", f"{message.content[:1900] or '*No text content*'}\n\n-# {message.author.mention} · {message.channel.mention} · [Jump](https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id})")
        if message.attachments:
            e.set_image(url=message.attachments[0].url)
        sent = await star_channel.send(content=f"⭐ **{count}** · {message.channel.mention}", embed=e)
        posted[str(message.id)] = sent.id
        posted = dict(list(posted.items())[-500:])
        cfg["starboard_posts"] = posted
        save_ultimate_config()
    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
        return

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
    if isinstance(error, commands.CheckFailure) and str(error) == "command disabled in this channel":
        return await ctx.send(embed=make_embed("command disabled", f"`{PREFIX}{ctx.command.qualified_name}` is disabled in this channel."), delete_after=5)
    if isinstance(error, commands.CommandInvokeError):
        original=error.original
        print(f"Command error in {ctx.command}: {original!r}")
        if isinstance(original, discord.Forbidden):
            return await ctx.send(embed=make_embed("discord denied the action", "Check my permissions and make sure my bot role is high enough."))
        return await ctx.send(embed=make_embed("command failed", "Something went wrong while running that command. Check the console for details."))
    print(f"Unhandled command error in {ctx.command}: {error!r}")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")



# ---------------------------------------------------------------------------
# Expanded Bleed-inspired compatibility command suite (original implementation)
# ---------------------------------------------------------------------------
COMPAT_PATH = "compat_config.json"
try:
    with open(COMPAT_PATH, "r", encoding="utf-8") as _f:
        COMPAT = json.load(_f)
except (OSError, json.JSONDecodeError):
    COMPAT = {}

def compat_save():
    with open(COMPAT_PATH, "w", encoding="utf-8") as _f:
        json.dump(COMPAT, _f, indent=2)

def compat_guild(ctx):
    return COMPAT.setdefault(str(ctx.guild.id), {})

def compat_need_manage(ctx):
    if not (ctx.author.guild_permissions.manage_guild or ctx.author.guild_permissions.administrator):
        return False
    return True

async def compat_reply(ctx, title, body):
    await ctx.send(embed=make_embed(title, body))

@bot.group(name="prefix", invoke_without_command=True)
async def prefix_group(ctx):
    await compat_reply(ctx, "prefix", f"Server prefix: `{PREFIX}`\nUse `{PREFIX}prefix set <prefix>` to configure a per-server prefix.")

@prefix_group.command(name="view")
async def prefix_view(ctx):
    await compat_reply(ctx, "prefix", f"Server prefix: `{compat_guild(ctx).get('prefix', PREFIX)}`")

@prefix_group.command(name="set")
async def prefix_set(ctx, *, prefix: str):
    if not compat_need_manage(ctx):
        return await compat_reply(ctx, "prefix", "You need Manage Server.")
    prefix = prefix.strip()
    if not prefix or len(prefix) > 5 or any(c.isspace() for c in prefix):
        return await compat_reply(ctx, "prefix", "Choose a prefix between 1 and 5 characters, without spaces.")
    compat_guild(ctx)["prefix"] = prefix
    compat_save()
    await compat_reply(ctx, "prefix", f"Saved server prefix `{prefix}`. It will be used for future messages in this server.")

@prefix_group.command(name="remove")
async def prefix_remove(ctx):
    if not compat_need_manage(ctx):
        return await compat_reply(ctx, "prefix", "You need Manage Server.")
    compat_guild(ctx).pop("prefix", None); compat_save()
    await compat_reply(ctx, "prefix", "Removed the saved server-prefix setting.")

@prefix_group.command(name="self")
async def prefix_self(ctx, *, prefix: str):
    await compat_reply(ctx, "prefix self", "Personal prefixes across servers are not available in this self-hosted bot.")

@bot.command(name="boosterrole", aliases=["brrole"])
async def boosterrole_compat(ctx, action="help", *, value=""):
    action=action.lower()
    # Route established BR actions through the existing BR command.
    cmd=bot.get_command("br")
    if action in {"create","color","colour","icon","share","name","rename","delete","remove","list","base","override"}:
        return await ctx.invoke(cmd, action, value=value)
    if action in {"random","dominant","cleanup","limit","award","link","filter"}:
        if not compat_need_manage(ctx) and action not in {"random","dominant"}:
            return await compat_reply(ctx,"Booster Role","You need Manage Server.")
        cfg=compat_guild(ctx).setdefault("boosterrole", {})
        if action in {"random","dominant"}:
            role_id=br_config.get(ctx.guild.id,{}).get(ctx.author.id)
            role=ctx.guild.get_role(role_id) if role_id else None
            if not role: return await compat_reply(ctx,"Booster Role",f"Create your role first with `{PREFIX}br create <name>`.")
            color=(random.randint(0,0xFFFFFF) if action=="random" else int(ctx.author.display_avatar.url[-6:],16) if False else random.randint(0,0xFFFFFF))
            await role.edit(color=discord.Color(color))
            return await compat_reply(ctx,"Booster Role",f"Updated {role.mention}.")
        if action=="cleanup":
            removed=0
            for owner_id, role_id in list(br_config.get(ctx.guild.id,{}).items()):
                role=ctx.guild.get_role(role_id)
                if role and not role.members:
                    try: await role.delete(reason="Booster role cleanup")
                    except discord.HTTPException: continue
                    br_config[ctx.guild.id].pop(owner_id,None); removed+=1
            save_br_config()
            return await compat_reply(ctx,"Booster Role",f"Removed `{removed}` unused booster roles.")
        if action=="limit":
            try: cfg["limit"]=max(1,min(100,int(value)))
            except ValueError: return await compat_reply(ctx,"Booster Role","Usage: `,boosterrole limit <1-100>`")
        elif action=="award":
            role=ctx.message.role_mentions[0] if ctx.message.role_mentions else None
            cfg["award_role"]=role.id if role else None
        elif action=="link":
            parts=value.split()
            if len(parts)<2: return await compat_reply(ctx,"Booster Role","Usage: `,boosterrole link @member @role`")
            member=ctx.message.mentions[0] if ctx.message.mentions else None
            role=ctx.message.role_mentions[0] if ctx.message.role_mentions else None
            if not member or not role: return await compat_reply(ctx,"Booster Role","Mention a member and role.")
            br_config.setdefault(ctx.guild.id,{})[member.id]=role.id; save_br_config()
            return await compat_reply(ctx,"Booster Role",f"Linked {role.mention} to {member.mention}.")
        elif action=="filter":
            words=cfg.setdefault("blocked_words",[])
            if not value.strip(): return await compat_reply(ctx,"Booster Role","Usage: `,boosterrole filter <word>`")
            if value.lower() not in words: words.append(value.lower())
        compat_save()
        return await compat_reply(ctx,"Booster Role",f"Saved `{action}` configuration.")
    await compat_reply(ctx,"Booster Role",f"Use `{PREFIX}br create`, `{PREFIX}br color`, `{PREFIX}br icon`, `{PREFIX}br share`, `{PREFIX}br rename`, `{PREFIX}br delete`, or `{PREFIX}boosterrole {action}`.")

@bot.command(name="boosts")
async def boosts_compat(ctx, action="list", channel: discord.TextChannel=None, *, message=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"boosts","You need Manage Server.")
    cfg=compat_guild(ctx).setdefault("boost_messages",{})
    action=action.lower()
    if action=="variables":
        return await compat_reply(ctx,"boosts variables","Available variables: `{user}`, `{username}`, `{server}`, `{membercount}`, `{boostcount}`, `{channel}`.")
    if action=="add":
        if not channel or not message: return await compat_reply(ctx,"boosts","Usage: `,boosts add #channel <message>`")
        cfg[str(channel.id)]=message; compat_save()
        return await compat_reply(ctx,"boosts",f"Saved boost message for {channel.mention}.")
    if action=="remove":
        if not channel: return await compat_reply(ctx,"boosts","Usage: `,boosts remove #channel`")
        cfg.pop(str(channel.id),None); compat_save()
        return await compat_reply(ctx,"boosts",f"Removed boost message for {channel.mention}.")
    if action=="view":
        if not channel: channel=ctx.channel
        return await compat_reply(ctx,"boosts",cfg.get(str(channel.id),"No boost message configured for that channel."))
    await compat_reply(ctx,"boosts","\n".join(f"<#{cid}> — {msg}" for cid,msg in cfg.items()) or "No boost messages configured.")

@bot.command(name="stickymessage", aliases=["stickies"])
async def stickymessage_compat(ctx, action="list", channel: discord.TextChannel=None, *, message=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"stickymessage","You need Manage Server.")
    cfg=compat_guild(ctx).setdefault("sticky_messages",{})
    action=action.lower()
    if action=="add":
        channel=channel or ctx.channel
        if not message: return await compat_reply(ctx,"stickymessage","Usage: `,stickymessage add #channel <message>`")
        cfg[str(channel.id)]=message; compat_save()
        return await compat_reply(ctx,"stickymessage",f"Saved sticky text for {channel.mention}.")
    if action=="remove":
        channel=channel or ctx.channel; cfg.pop(str(channel.id),None); compat_save()
        return await compat_reply(ctx,"stickymessage",f"Removed sticky configuration for {channel.mention}.")
    if action=="view":
        channel=channel or ctx.channel
        return await compat_reply(ctx,"stickymessage",cfg.get(str(channel.id),"No sticky configured."))
    await compat_reply(ctx,"stickymessage","\n".join(f"<#{cid}> — {msg}" for cid,msg in cfg.items()) or "No sticky messages configured.")

@bot.command(name="imgonly", aliases=["galleryonly"])
async def imgonly_compat(ctx, action="list", channel: discord.TextChannel=None):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"imgonly","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("imgonly",[])
    action=action.lower(); channel=channel or ctx.channel
    if action=="add":
        if channel.id not in cfg: cfg.append(channel.id)
        compat_save(); return await compat_reply(ctx,"imgonly",f"Added {channel.mention} to image-only channels.")
    if action=="remove":
        cfg[:]=[x for x in cfg if x!=channel.id]; compat_save()
        return await compat_reply(ctx,"imgonly",f"Removed {channel.mention} from image-only channels.")
    await compat_reply(ctx,"imgonly","\n".join(f"<#{cid}>" for cid in cfg) or "No image-only channels configured.")

@bot.command(name="invoke")
async def invoke_compat(ctx, action="list", *, value=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"invoke","You need Manage Server.")
    cfg=compat_guild(ctx).setdefault("invoke_messages",{})
    action=action.lower()
    if action in {"list","view"}:
        return await compat_reply(ctx,"invoke", "\n".join(f"`{k}`: {v}" for k,v in cfg.items()) or "No custom punishment messages configured.")
    if action=="reset":
        cfg.clear(); compat_save(); return await compat_reply(ctx,"invoke","Reset custom punishment messages.")
    # Syntax accepts `ban dm <message>` or `ban message <message>`.
    parts=value.split(maxsplit=1)
    if not parts or parts[0] not in {"dm","message"}:
        return await compat_reply(ctx,"invoke",f"Usage: `,invoke {action} dm <text>` or `,invoke {action} message <text>`")
    cfg[f"{action}_{parts[0]}"]=parts[1] if len(parts)>1 else ""
    compat_save(); await compat_reply(ctx,"invoke",f"Saved `{action} {parts[0]}` message template.")

@bot.command(name="pagination")
async def pagination_compat(ctx, action="list", *, value=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"pagination","You need Manage Messages.")
    cfg=compat_guild(ctx).setdefault("pagination",{})
    action=action.lower()
    if action=="list": return await compat_reply(ctx,"pagination", "\n".join(cfg.keys()) or "No pagination entries saved.")
    if action in {"reset","delete","remove"}:
        if action=="reset": cfg.clear()
        else: cfg.pop(value.strip(),None)
        compat_save(); return await compat_reply(ctx,"pagination","Updated pagination configuration.")
    if action in {"add","set","update"}:
        if not value: return await compat_reply(ctx,"pagination",f"Usage: `,pagination {action} <message-link or ID> <embed text>`")
        key=value.split()[0]; cfg[key]=value[len(key):].strip(); compat_save()
        return await compat_reply(ctx,"pagination",f"Saved pagination draft for `{key}`.")
    await compat_reply(ctx,"pagination","Actions: list, add, set, update, remove, delete, reset.")

@bot.command(name="disablecommand")
async def disablecommand_compat(ctx, action_or_target=None, *, command_name=None):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"disablecommand","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_commands",{})
    if action_or_target=="list":
        return await compat_reply(ctx,"disablecommand","\n".join(f"{k}: {', '.join(v)}" for k,v in cfg.items()) or "No channel command restrictions saved.")
    channel=ctx.guild.get_channel(int(re.sub(r"\D","",str(action_or_target or "")))) if str(action_or_target or "").isdigit() else ctx.channel
    name=command_name or str(action_or_target or "")
    if not name: return await compat_reply(ctx,"disablecommand","Usage: `,disablecommand [#channel] <command>`")
    cfg.setdefault(str(channel.id),[])
    if name not in cfg[str(channel.id)]: cfg[str(channel.id)].append(name)
    compat_save(); await compat_reply(ctx,"disablecommand",f"Saved `{name}` as disabled in {channel.mention}. (The restriction is recorded; runtime blocking is not enabled yet.)")

@bot.command(name="enablecommand")
async def enablecommand_compat(ctx, action_or_target=None, *, command_name=None):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"enablecommand","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_commands",{})
    if action_or_target=="all":
        name=command_name or ""
        for cid, names in cfg.items(): cfg[cid]=[x for x in names if x!=name]
        compat_save(); return await compat_reply(ctx,"enablecommand",f"Removed `{name}` from saved disabled-command lists.")
    channel=ctx.guild.get_channel(int(re.sub(r"\D","",str(action_or_target or "")))) if str(action_or_target or "").isdigit() else ctx.channel
    name=command_name or str(action_or_target or "")
    cfg[str(channel.id)]=[x for x in cfg.get(str(channel.id),[]) if x!=name]
    compat_save(); await compat_reply(ctx,"enablecommand",f"Enabled `{name}` in {channel.mention} in the saved configuration.")

@bot.command(name="disableevent")
async def disableevent_compat(ctx, action="list", *, event=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"disableevent","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_events",[])
    if action=="list": return await compat_reply(ctx,"disableevent",", ".join(cfg) or "No events disabled.")
    if event and event not in cfg: cfg.append(event)
    compat_save(); await compat_reply(ctx,"disableevent",f"Saved event setting: `{event or action}`.")

@bot.command(name="enableevent")
async def enableevent_compat(ctx, action="all", *, event=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"enableevent","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_events",[])
    target=event or ("" if action=="all" else action)
    if action=="all" or target=="all": cfg.clear()
    else: cfg[:]=[x for x in cfg if x!=target]
    compat_save(); await compat_reply(ctx,"enableevent",f"Updated event configuration for `{target or 'all'}`.")

@bot.command(name="disablemodule")
async def disablemodule_compat(ctx, module="list", *, channel_text=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"disablemodule","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_modules",{})
    if module=="list": return await compat_reply(ctx,"disablemodule","\n".join(f"{c}: {', '.join(v)}" for c,v in cfg.items()) or "No modules disabled.")
    cfg.setdefault(str(ctx.channel.id),[])
    if module not in cfg[str(ctx.channel.id)]: cfg[str(ctx.channel.id)].append(module)
    compat_save(); await compat_reply(ctx,"disablemodule",f"Saved module `{module}` as disabled in {ctx.channel.mention}.")

@bot.command(name="enablemodule")
async def enablemodule_compat(ctx, module="all", *, channel_text=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"enablemodule","You need Manage Channels.")
    cfg=compat_guild(ctx).setdefault("disabled_modules",{})
    if module=="all":
        cfg.clear()
    else:
        cfg[str(ctx.channel.id)]=[x for x in cfg.get(str(ctx.channel.id),[]) if x!=module]
    compat_save(); await compat_reply(ctx,"enablemodule",f"Updated module configuration for `{module}`.")

@bot.command(name="seticon")
async def seticon_compat(ctx, *, url=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"seticon","You need Manage Guild.")
    url=url.strip() or (ctx.message.attachments[0].url if ctx.message.attachments else "")
    if not url: return await compat_reply(ctx,"seticon","Provide an image URL or attach an image.")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status!=200: return await compat_reply(ctx,"seticon","Couldn't download that image.")
                data=await response.read()
        await ctx.guild.edit(icon=data, reason=f"Server icon changed by {ctx.author}")
        await compat_reply(ctx,"seticon","Updated the server icon.")
    except (discord.HTTPException, aiohttp.ClientError) as e:
        await compat_reply(ctx,"seticon",f"Couldn't update the icon: {e}")

@bot.command(name="setbanner")
async def setbanner_compat(ctx, *, url=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"setbanner","You need Manage Guild.")
    await compat_reply(ctx,"setbanner","Discord only allows server-banner changes for eligible servers. This bot build doesn't yet upload a banner image through the API.")

@bot.command(name="setsplashbackground")
async def setsplash_compat(ctx, *, url=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"setsplashbackground","You need Manage Guild.")
    await compat_reply(ctx,"setsplashbackground","This action is not supported by the installed discord.py API/server feature set.")

@bot.command(name="extractemotes", aliases=["extractemojis"])
async def extractemotes_compat(ctx):
    if not ctx.author.guild_permissions.administrator: return await compat_reply(ctx,"extractemotes","You need Administrator.")
    emotes=list(ctx.guild.emojis)
    if not emotes: return await compat_reply(ctx,"extractemotes","This server has no custom emojis.")
    lines=[f"{e.name}: {e.url}" for e in emotes]
    data=("\n".join(lines)).encode()
    await ctx.send(file=discord.File(io.BytesIO(data), filename=f"{ctx.guild.id}-emojis.txt"))

@bot.command(name="extractstickers")
async def extractstickers_compat(ctx):
    if not ctx.author.guild_permissions.administrator: return await compat_reply(ctx,"extractstickers","You need Administrator.")
    stickers=list(ctx.guild.stickers)
    data="\n".join(f"{s.name}: {s.url}" for s in stickers).encode()
    await ctx.send(file=discord.File(io.BytesIO(data), filename=f"{ctx.guild.id}-stickers.txt"))

@bot.command(name="reposter")
async def reposter_compat(ctx, action="view", *, value=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"reposter","You need Manage Server.")
    cfg=compat_guild(ctx).setdefault("reposter",{})
    action=action.lower()
    if action=="view": return await compat_reply(ctx,"reposter","\n".join(f"{k}: {v}" for k,v in cfg.items()) or "No repost settings configured.")
    if action=="reset": cfg.clear()
    else: cfg[action]=value or "on"
    compat_save(); await compat_reply(ctx,"reposter",f"Saved repost setting `{action}` = `{cfg.get(action,'off')}`.")

@bot.command(name="customize")
async def customize_compat(ctx, action="view", *, value=""):
    if ctx.guild.owner_id != ctx.author.id: return await compat_reply(ctx,"customize","Only the server owner can use this command.")
    cfg=compat_guild(ctx).setdefault("customize",{})
    if action=="view": return await compat_reply(ctx,"customize","\n".join(f"{k}: {v}" for k,v in cfg.items()) or "No custom bot appearance saved.")
    cfg[action]=value; compat_save()
    await compat_reply(ctx,"customize",f"Saved bot customization `{action}`. Applying per-server bot avatars/banners requires Discord application support not available to this bot.")

@bot.command(name="badge")
async def badge_compat(ctx, action="view", *, value=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"badge","You need Manage Server.")
    cfg=compat_guild(ctx).setdefault("badge",{})
    if action=="view": return await compat_reply(ctx,"badge","\n".join(f"{k}: {v}" for k,v in cfg.items()) or "No guild-tag reward settings.")
    cfg[action]=value or "on"; compat_save()
    await compat_reply(ctx,"badge",f"Saved badge setting `{action}`. Guild-tag detection/role awards require Discord guild-tag event support not available in this build.")

@bot.command(name="honeypot")
async def honeypot_compat(ctx, action="list", channel: discord.TextChannel=None, *, punishment="kick"):
    if not ctx.author.guild_permissions.administrator: return await compat_reply(ctx,"honeypot","You need Administrator.")
    cfg=compat_guild(ctx).setdefault("honeypot",{})
    action=action.lower()
    if action=="add":
        channel=channel or ctx.channel
        cfg[str(channel.id)]=punishment; compat_save()
        return await compat_reply(ctx,"honeypot",f"Added {channel.mention} as a honeypot with `{punishment}` configured.")
    if action=="remove":
        channel=channel or ctx.channel; cfg.pop(str(channel.id),None); compat_save()
        return await compat_reply(ctx,"honeypot",f"Removed {channel.mention} from honeypots.")
    await compat_reply(ctx,"honeypot","\n".join(f"<#{cid}> — `{pun}`" for cid,pun in cfg.items()) or "No honeypot channels configured.")

@bot.command(name="pins")
async def pins_compat(ctx, action="config", *, value=""):
    if not compat_need_manage(ctx): return await compat_reply(ctx,"pins","You need Manage Guild.")
    cfg=compat_guild(ctx).setdefault("pins",{"enabled":False,"channel":None,"unpin":True})
    action=action.lower()
    if action=="config":
        archive_channel = f"<#{cfg['channel']}>" if cfg.get("channel") else "`not set`"
        return await compat_reply(ctx, "pins", f"enabled: `{cfg['enabled']}`\narchive channel: {archive_channel}\nunpin during archive: `{cfg['unpin']}`")
    if action=="set": cfg["enabled"]=value.lower() in {"on","yes","true","enable","enabled"}
    elif action=="reset": cfg.update({"enabled":False,"channel":None,"unpin":True})
    elif action=="channel":
        channel=ctx.message.channel_mentions[0] if ctx.message.channel_mentions else None
        if not channel: return await compat_reply(ctx,"pins","Usage: `,pins channel #channel`")
        cfg["channel"]=channel.id
    elif action=="unpin": cfg["unpin"]=value.lower() in {"on","yes","true","enable","enabled"}
    elif action=="archive":
        pins=await ctx.channel.pins()
        if not pins: return await compat_reply(ctx,"pins","No pinned messages to archive.")
        dest=ctx.guild.get_channel(cfg.get("channel")) or ctx.channel
        await dest.send(embed=make_embed("pin archive", "\n".join(f"[{m.author}]({m.jump_url}): {m.content[:150]}" for m in pins[:20])))
        if cfg.get("unpin"):
            for m in pins:
                try: await m.unpin(reason=f"Pin archive by {ctx.author}")
                except discord.HTTPException: pass
    compat_save(); await compat_reply(ctx,"pins","Updated pin archive configuration.")

@bot.command(name="webhook")
async def webhook_compat(ctx, action="list", *, value=""):
    if not ctx.author.guild_permissions.manage_webhooks: return await compat_reply(ctx,"webhook","You need Manage Webhooks.")
    action=action.lower()
    try:
        hooks=await ctx.channel.webhooks()
        if action=="list":
            return await compat_reply(ctx,"webhook","\n".join(f"`{w.id}` — {w.name}" for w in hooks) or "No webhooks in this channel.")
        if action=="create":
            hook=await ctx.channel.create_webhook(name=(value.strip() or "bleeed webhook"))
            return await compat_reply(ctx,"webhook",f"Created webhook `{hook.name}` (`{hook.id}`).")
        if action=="delete":
            hook=next((w for w in hooks if str(w.id)==value.strip() or w.name==value.strip()),None)
            if not hook: return await compat_reply(ctx,"webhook","Couldn't find that webhook by ID or name.")
            await hook.delete(reason=f"Webhook deleted by {ctx.author}")
            return await compat_reply(ctx,"webhook",f"Deleted webhook `{hook.name}`.")
        await compat_reply(ctx,"webhook","Actions: list, create <name>, delete <ID or name>. Sending/editing requires a webhook URL or message link.")
    except discord.HTTPException as e: await compat_reply(ctx,"webhook",f"Webhook operation failed: {e}")

@bot.command(name="fakepermissions")
async def fakepermissions_compat(ctx, action="list", role: discord.Role=None, *, permission=""):
    if ctx.guild.owner_id != ctx.author.id: return await compat_reply(ctx,"fakepermissions","Only the server owner can use this command.")
    cfg=compat_guild(ctx).setdefault("fakepermissions",{})
    action=action.lower()
    if action=="reset": cfg.clear(); compat_save(); return await compat_reply(ctx,"fakepermissions","Reset fake permission labels.")
    if action=="list":
        if role: return await compat_reply(ctx,"fakepermissions",", ".join(cfg.get(str(role.id),[])) or "No fake permissions for that role.")
        return await compat_reply(ctx,"fakepermissions","\n".join(f"<@&{rid}>: {', '.join(perms)}" for rid,perms in cfg.items()) or "No fake permissions configured.")
    if not role or not permission: return await compat_reply(ctx,"fakepermissions","Usage: `,fakepermissions add @role <permission>` or `remove @role <permission>`")
    perms=cfg.setdefault(str(role.id),[])
    if action=="add" and permission not in perms: perms.append(permission)
    elif action=="remove": cfg[str(role.id)]=[p for p in perms if p!=permission]
    compat_save()
    await compat_reply(ctx,"fakepermissions",f"Updated informational fake-permission labels for {role.mention}. These do not grant real Discord permissions.")

@bot.command(name="enablecommandall")
async def enablecommandall_compat(ctx, *, command_name: str):
    ctx.message.content=f"{PREFIX}enablecommand all {command_name}"
    await enablecommand_compat(ctx, "all", command_name=command_name)

@bot.command(name="disablecommandall")
async def disablecommandall_compat(ctx, *, command_name: str):
    ctx.message.content=f"{PREFIX}disablecommand all {command_name}"
    await disablecommand_compat(ctx, "all", command_name=command_name)



def _bleeed_dynamic_prefix(bot_instance, message):
    guild_id = getattr(getattr(message, "guild", None), "id", None)
    configured = COMPAT.get(str(guild_id), {}).get("prefix") if guild_id else None
    return configured or PREFIX

bot.command_prefix = _bleeed_dynamic_prefix

# Expose the new command suite in the paginated command browser.
CATEGORIES.extend([
    ("Prefix & Setup", ["prefix", "settings", "seticon", "setbanner", "setsplashbackground"]),
    ("Booster Roles Plus", ["boosterrole", "br"]),
    ("Messages & Community", ["boosts", "stickymessage", "imgonly", "welcome", "goodbye", "suggest", "suggestchannel", "reposter", "badge", "honeypot"]),
    ("Configuration", ["invoke", "alias", "fakepermissions", "pagination", "pins", "webhook", "customize"]),
    ("Command Controls", ["disablecommand", "enablecommand", "disablecommandall", "enablecommandall", "disableevent", "enableevent", "disablemodule", "enablemodule", "ignore", "commandtoggle"]),
    ("Exports", ["extractemotes", "extractstickers"]),
])


COMMAND_INFO.update({
    "prefix": ("View or configure the server command prefix.", "prefix [view|set|remove] [prefix]", "prefix set !", []),
    "boosterrole": ("Manage booster role settings and tools.", "boosterrole <action> [value]", "boosterrole cleanup", ["brrole"]),
    "boosts": ("Configure boost messages per channel.", "boosts <add|view|list|remove|variables> [channel] [message]", "boosts add #general Thanks for boosting!", []),
    "stickymessage": ("Manage sticky message templates by channel.", "stickymessage <add|view|list|remove> [channel] [message]", "stickymessage add #chat Read the rules!", ["stickies"]),
    "imgonly": ("Configure image-only channels.", "imgonly <add|remove|list> [channel]", "imgonly add #gallery", ["galleryonly"]),
    "invoke": ("Configure custom punishment response templates.", "invoke <punishment> <dm|message> <text>", "invoke ban dm You were banned from {server}.", []),
    "pagination": ("Save and manage pagination/embed drafts.", "pagination <list|add|set|update|remove|reset> [value]", "pagination list", []),
    "disablecommand": ("Record a command restriction for a channel.", "disablecommand [channel] <command>", "disablecommand #general poll", []),
    "enablecommand": ("Remove a saved command restriction.", "enablecommand [channel|all] <command>", "enablecommand #general poll", []),
    "disablecommandall": ("Record a command restriction for every channel.", "disablecommandall <command>", "disablecommandall poll", []),
    "enablecommandall": ("Remove a saved global command restriction.", "enablecommandall <command>", "enablecommandall poll", []),
    "disableevent": ("Record an event setting as disabled.", "disableevent <event>", "disableevent welcome", []),
    "enableevent": ("Enable a previously disabled event setting.", "enableevent <event|all>", "enableevent all", []),
    "disablemodule": ("Record a module restriction for this channel.", "disablemodule <module>", "disablemodule music", []),
    "enablemodule": ("Enable a saved module setting.", "enablemodule <module|all>", "enablemodule all", []),
    "seticon": ("Change the server icon.", "seticon <url>", "seticon https://example.com/icon.png", []),
    "setbanner": ("Change the server banner when supported.", "setbanner <url>", "setbanner https://example.com/banner.png", []),
    "setsplashbackground": ("Change the server invite splash when supported.", "setsplashbackground <url>", "setsplashbackground https://example.com/splash.png", []),
    "extractemotes": ("Export custom server emoji URLs to a text file.", "extractemotes", "extractemotes", ["extractemojis"]),
    "extractstickers": ("Export custom server sticker URLs to a text file.", "extractstickers", "extractstickers", []),
    "reposter": ("Configure social-media repost preferences.", "reposter <setting|view|reset> [value]", "reposter embed on", []),
    "customize": ("Save bot appearance preferences for this server.", "customize <setting> [value]", "customize bio Welcome to our server", []),
    "badge": ("Configure guild-tag reward preferences.", "badge <setting> [value]", "badge role on", []),
    "honeypot": ("Manage honeypot channels.", "honeypot <add|remove|list> [channel] [punishment]", "honeypot add #bait kick", []),
    "pins": ("Archive pinned messages and manage pin settings.", "pins <config|set|reset|channel|unpin|archive> [value]", "pins archive", []),
    "webhook": ("List, create, or delete channel webhooks.", "webhook <list|create|delete> [name or ID]", "webhook create announcements", []),
    "fakepermissions": ("Manage informational fake-permission labels.", "fakepermissions <add|remove|list|reset> [role] [permission]", "fakepermissions add @VIP manage messages", []),
})


# =========================
# Additional moderation/server commands requested from the command reference
# =========================

@bot.command(name="tempban", aliases=["tban"])
async def tempban(ctx, member: discord.Member, duration: str, *, reason="no reason provided"):
    if not (ctx.author.guild_permissions.ban_members or role_ok(ctx.author, {BAN_ROLE})):
        return await ctx.send(embed=make_embed("no permission", "you need Ban Members or the configured ban role."))
    seconds = parse_duration(duration)
    if not seconds:
        return await ctx.send(embed=make_embed("invalid duration", "use a duration like `10m`, `2h`, or `3d`."))
    if not bot_can(ctx, "ban_members") or not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot tempban", "check bot permissions and role hierarchy."))
    uid, guild_id = member.id, ctx.guild.id
    try:
        await member.ban(reason=f"Temporary ban by {ctx.author}: {reason}", delete_message_seconds=0)
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("tempban failed", "Discord denied the ban."))
    record_modlog(ctx.guild, uid, "Tempban", ctx.author, f"{reason} (duration {duration})")
    await ctx.send(embed=make_embed("member temporarily banned", f"**User**\n`{uid}`\n\n**Duration**\n`{duration}`\n\n**Reason**\n{reason}"))
    async def expire_tempban():
        await asyncio.sleep(seconds)
        guild = bot.get_guild(guild_id)
        if guild:
            try: await guild.unban(discord.Object(id=uid), reason="Temporary ban expired")
            except (discord.NotFound, discord.Forbidden, discord.HTTPException): pass
    asyncio.create_task(expire_tempban())

@bot.command(name="softban")
async def softban(ctx, member: discord.Member, delete_history: int = 86400, *, reason="no reason provided"):
    if not (ctx.author.guild_permissions.ban_members or role_ok(ctx.author, {BAN_ROLE})):
        return await ctx.send(embed=make_embed("no permission", "you need Ban Members or the configured ban role."))
    if not bot_can(ctx, "ban_members") or not target_ok(ctx, member):
        return await ctx.send(embed=make_embed("cannot softban", "check bot permissions and role hierarchy."))
    seconds = max(0, min(int(delete_history), 604800))
    try:
        await member.ban(reason=f"Softban by {ctx.author}: {reason}", delete_message_seconds=seconds)
        await ctx.guild.unban(discord.Object(id=member.id), reason=f"Softban reversal by {ctx.author}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("softban failed", "Discord denied the action."))
    record_modlog(ctx.guild, member.id, "Softban", ctx.author, reason)
    await ctx.send(embed=make_embed("member softbanned", f"**User**\n`{member.id}`\n\n**Message history deleted**\n`{seconds}` seconds\n\n**Reason**\n{reason}"))

@bot.command(name="timeoutlist", aliases=["timeout-list"])
@commands.has_permissions(moderate_members=True)
async def timeoutlist(ctx):
    now = datetime.now(timezone.utc)
    members = [m for m in ctx.guild.members if m.timed_out_until and m.timed_out_until > now]
    lines = [f"`{i:02}` {m.mention} · ends <t:{int(m.timed_out_until.timestamp())}:R>" for i,m in enumerate(sorted(members, key=lambda x:x.timed_out_until), 1)]
    await ctx.send(embed=make_embed("timed out members", "\n".join(lines[:50]) or "no members are currently timed out."))

@bot.command(name="jail")
async def jail(ctx, member: discord.Member, duration: str = "10m", *, reason="no reason provided"):
    if not (ctx.author.guild_permissions.manage_messages or role_ok(ctx.author, MUTE_ROLES)):
        return await ctx.send(embed=make_embed("no permission", "you need Manage Messages or a configured moderation role."))
    seconds = parse_duration(duration)
    if not seconds:
        return await ctx.send(embed=make_embed("invalid duration", "use `10m`, `2h`, or `1d`."))
    role = discord.utils.get(ctx.guild.roles, name="Jailed") or discord.utils.get(ctx.guild.roles, name="Jail")
    if role is None:
        try:
            role = await ctx.guild.create_role(name="Jailed", reason="Jail system setup")
            for ch in ctx.guild.channels:
                try: await ch.set_permissions(role, view_channel=False, send_messages=False, connect=False, reason="Jail role setup")
                except discord.HTTPException: pass
        except discord.HTTPException:
            return await ctx.send(embed=make_embed("jail failed", "I couldn't create the jail role. Check Manage Roles."))
    if role >= ctx.guild.me.top_role or member.top_role >= ctx.guild.me.top_role:
        return await ctx.send(embed=make_embed("jail failed", "The member and jail role must be below my highest role."))
    old_roles = [r.id for r in member.roles if r != ctx.guild.default_role and r < ctx.guild.me.top_role]
    jail_store = _load_json_config("jail_config.json", {})
    jail_store.setdefault(str(ctx.guild.id), {})[str(member.id)] = {"roles": old_roles, "until": int(time.time())+seconds, "reason": reason}
    _save_json_file("jail_config.json", jail_store)
    try:
        if old_roles:
            await member.remove_roles(*[r for r in member.roles if r.id in old_roles], reason=f"Jailed by {ctx.author}: {reason}")
        await member.add_roles(role, reason=f"Jailed by {ctx.author}: {reason}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("jail failed", "Discord denied the role change."))
    record_modlog(ctx.guild, member, "Jail", ctx.author, reason)
    await ctx.send(embed=make_embed("member jailed", f"{member.mention} was jailed for `{duration}`.\n\n**Reason**\n{reason}"))
    async def release():
        await asyncio.sleep(seconds)
        guild=bot.get_guild(ctx.guild.id)
        if not guild: return
        target=guild.get_member(member.id); jail_role=discord.utils.get(guild.roles, name="Jailed") or discord.utils.get(guild.roles, name="Jail")
        if not target: return
        try:
            if jail_role and jail_role in target.roles: await target.remove_roles(jail_role, reason="Jail duration expired")
            restore=[guild.get_role(rid) for rid in old_roles]
            restore=[r for r in restore if r and r < guild.me.top_role]
            if restore: await target.add_roles(*restore, reason="Jail duration expired")
        except discord.HTTPException: pass
        data=_load_json_config("jail_config.json", {}); data.get(str(guild.id), {}).pop(str(member.id), None); _save_json_file("jail_config.json", data)
    asyncio.create_task(release())

@bot.command(name="unjail")
async def unjail(ctx, member: discord.Member, *, reason="released by moderator"):
    if not (ctx.author.guild_permissions.manage_messages or role_ok(ctx.author, MUTE_ROLES)):
        return await ctx.send(embed=make_embed("no permission", "you need Manage Messages or a configured moderation role."))
    data=_load_json_config("jail_config.json", {}); saved=data.get(str(ctx.guild.id), {}).get(str(member.id))
    if not saved: return await ctx.send(embed=make_embed("unjail", "that member isn't in the saved jail list."))
    role=discord.utils.get(ctx.guild.roles, name="Jailed") or discord.utils.get(ctx.guild.roles, name="Jail")
    try:
        if role and role in member.roles: await member.remove_roles(role, reason=f"Unjailed by {ctx.author}: {reason}")
        restore=[ctx.guild.get_role(rid) for rid in saved.get("roles", [])]
        restore=[r for r in restore if r and r < ctx.guild.me.top_role]
        if restore: await member.add_roles(*restore, reason=f"Unjailed by {ctx.author}: {reason}")
    except discord.HTTPException:
        return await ctx.send(embed=make_embed("unjail failed", "Discord denied the role change."))
    data.get(str(ctx.guild.id), {}).pop(str(member.id), None); _save_json_file("jail_config.json", data)
    await ctx.send(embed=make_embed("member unjailed", f"{member.mention} has been released.\n\n**Reason**\n{reason}"))

@bot.command(name="moveall")
@commands.has_permissions(administrator=True, move_members=True)
async def moveall(ctx, channel: discord.VoiceChannel):
    if not ctx.author.voice or not ctx.author.voice.channel:
        return await ctx.send(embed=make_embed("move all", "join a voice channel first."))
    source=ctx.author.voice.channel; moved=0
    for m in list(source.members):
        try: await m.move_to(channel, reason=f"moveall by {ctx.author}"); moved+=1
        except discord.HTTPException: pass
    await ctx.send(embed=make_embed("members moved", f"Moved `{moved}` members from {source.mention} to {channel.mention}."))

@bot.command(name="drag")
@commands.has_permissions(move_members=True)
async def drag(ctx, members: commands.Greedy[discord.Member], channel: discord.VoiceChannel):
    moved=0
    for m in members:
        try: await m.move_to(channel, reason=f"drag by {ctx.author}"); moved+=1
        except discord.HTTPException: pass
    await ctx.send(embed=make_embed("members moved", f"Moved `{moved}` members to {channel.mention}."))

@bot.command(name="stripstaff")
@commands.has_permissions(administrator=True)
async def stripstaff(ctx, member: discord.Member):
    staff_ids=set(WARN_ROLES)|set(KICK_ROLES)|{BAN_ROLE}
    roles=[r for r in member.roles if r.id in staff_ids and r < ctx.guild.me.top_role]
    if not roles: return await ctx.send(embed=make_embed("strip staff", "no configured moderation roles found on that member."))
    await member.remove_roles(*roles, reason=f"staff roles stripped by {ctx.author}")
    await ctx.send(embed=make_embed("staff roles removed", f"Removed `{len(roles)}` configured moderation roles from {member.mention}."))

@bot.command(name="clearinvites")
@commands.has_permissions(manage_guild=True)
async def clearinvites(ctx):
    try: invites=await ctx.guild.invites()
    except discord.HTTPException: return await ctx.send(embed=make_embed("clear invites failed", "I couldn't fetch server invites."))
    deleted=0
    for invite in invites:
        try: await invite.delete(reason=f"clearinvites by {ctx.author}"); deleted+=1
        except discord.HTTPException: pass
    await ctx.send(embed=make_embed("invites cleared", f"Deleted `{deleted}` invites."))

@bot.command(name="newmembers")
async def newmembers(ctx, count: int = 10):
    count=max(1,min(count,50))
    members=sorted(ctx.guild.members, key=lambda m:m.joined_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)[:count]
    lines=[f"`{i:02}` {m.mention} · <t:{int(m.joined_at.timestamp())}:R>" for i,m in enumerate(members,1) if m.joined_at]
    await ctx.send(embed=make_embed("recently joined members", "\n".join(lines) or "no join dates available."))

@bot.command(name="recentban")
@commands.has_permissions(ban_members=True)
async def recentban(ctx, count: int = 5, *, reason="recent join moderation"):
    count=max(1,min(count,25)); now=datetime.now(timezone.utc); cutoff=now-timedelta(days=7)
    candidates=[m for m in ctx.guild.members if m.joined_at and m.joined_at >= cutoff and m != ctx.author and m.top_role < ctx.author.top_role]
    banned=0
    for m in candidates[:count]:
        try: await m.ban(reason=f"recentban by {ctx.author}: {reason}", delete_message_seconds=0); banned+=1
        except discord.HTTPException: pass
    await ctx.send(embed=make_embed("recent members banned", f"Banned `{banned}` members who joined in the last 7 days.\n\n**Reason**\n{reason}"))

@bot.command(name="hide")
@commands.has_permissions(manage_channels=True)
async def hide(ctx, channel: discord.TextChannel = None, target: discord.Member | discord.Role = None):
    channel=channel or ctx.channel; target=target or ctx.guild.default_role
    ow=channel.overwrites_for(target); ow.view_channel=False
    await channel.set_permissions(target, overwrite=ow, reason=f"hide by {ctx.author}")
    await ctx.send(embed=make_embed("channel hidden", f"{channel.mention} is now hidden from {target.mention if isinstance(target, discord.Member) else target.name}."))

@bot.command(name="unhide")
@commands.has_permissions(manage_channels=True)
async def unhide(ctx, channel: discord.TextChannel = None, target: discord.Member | discord.Role = None):
    channel=channel or ctx.channel; target=target or ctx.guild.default_role
    ow=channel.overwrites_for(target); ow.view_channel=None
    await channel.set_permissions(target, overwrite=ow, reason=f"unhide by {ctx.author}")
    await ctx.send(embed=make_embed("channel unhidden", f"Restored default visibility for {target.mention if isinstance(target, discord.Member) else target.name} in {channel.mention}."))

@bot.group(name="thread", invoke_without_command=True)
async def thread_group(ctx):
    await ctx.send(embed=make_embed("thread commands", f"`{PREFIX}thread rename <thread> <name>`\n`{PREFIX}thread lock <thread> [reason]`\n`{PREFIX}thread unlock <thread> [reason]`\n`{PREFIX}thread add <thread> <member>`\n`{PREFIX}thread remove <thread> <member>`\n`{PREFIX}thread watch <thread>`\n`{PREFIX}thread watch list`"))

@thread_group.command(name="rename")
@commands.has_permissions(manage_threads=True)
async def thread_rename(ctx, thread: discord.Thread, *, new_name: str):
    await thread.edit(name=new_name, reason=f"thread renamed by {ctx.author}")
    await ctx.send(embed=make_embed("thread renamed", f"Renamed thread to **{new_name}**."))

@thread_group.command(name="lock")
@commands.has_permissions(manage_threads=True)
async def thread_lock(ctx, thread: discord.Thread, *, reason="locked by moderator"):
    await thread.edit(locked=True, reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=make_embed("thread locked", f"{thread.mention}\n\n**Reason**\n{reason}"))

@thread_group.command(name="unlock")
@commands.has_permissions(manage_threads=True)
async def thread_unlock(ctx, thread: discord.Thread, *, reason="unlocked by moderator"):
    await thread.edit(locked=False, reason=f"{ctx.author}: {reason}")
    await ctx.send(embed=make_embed("thread unlocked", f"{thread.mention}\n\n**Reason**\n{reason}"))

@thread_group.command(name="add")
@commands.has_permissions(manage_threads=True)
async def thread_add(ctx, thread: discord.Thread, member: discord.Member):
    await thread.add_user(member)
    await ctx.send(embed=make_embed("thread member added", f"Added {member.mention} to {thread.mention}."))

@thread_group.command(name="remove")
@commands.has_permissions(manage_threads=True)
async def thread_remove(ctx, thread: discord.Thread, member: discord.Member):
    await thread.remove_user(member)
    await ctx.send(embed=make_embed("thread member removed", f"Removed {member.mention} from {thread.mention}."))

@thread_group.group(name="watch", invoke_without_command=True)
@commands.has_permissions(manage_channels=True)
async def thread_watch(ctx, thread: discord.Thread = None):
    store=_load_json_config("thread_watch.json", {}); key=str(ctx.guild.id); store.setdefault(key, [])
    if thread is None:
        ids=store[key]; lines=[f"`{i+1:02}` <#{tid}>" for i,tid in enumerate(ids) if ctx.guild.get_thread(tid)]
        return await ctx.send(embed=make_embed("watched threads", "\n".join(lines) or "no watched threads."))
    if thread.id in store[key]: store[key].remove(thread.id); action="removed from"
    else: store[key].append(thread.id); action="added to"
    _save_json_file("thread_watch.json", store)
    await ctx.send(embed=make_embed("thread watch", f"{thread.mention} {action} the watch list."))

@thread_watch.command(name="list")
@commands.has_permissions(manage_channels=True)
async def thread_watch_list(ctx):
    store=_load_json_config("thread_watch.json", {}); ids=store.get(str(ctx.guild.id), [])
    lines=[f"`{i+1:02}` <#{tid}>" for i,tid in enumerate(ids) if ctx.guild.get_thread(int(tid))]
    await ctx.send(embed=make_embed("watched threads", "\n".join(lines) or "no watched threads."))

@bot.command(name="banpurge")
@commands.has_permissions(manage_guild=True, ban_members=True)
async def banpurge(ctx, seconds: int = 604800):
    seconds=max(0,min(seconds,604800)); cfg=guild_cfg(ctx.guild.id); cfg["ban_delete_seconds"]=seconds; save_ultimate_config()
    await ctx.send(embed=make_embed("ban purge setting", f"Bans will delete up to `{seconds}` seconds of message history when supported."))

@bot.group(name="hardban", invoke_without_command=True)
@commands.has_permissions(administrator=True, ban_members=True)
async def hardban(ctx, user_id: int = None, *, reason="no reason provided"):
    if user_id is None: return await ctx.send(embed=make_embed("hardban", f"usage: `{PREFIX}hardban <user ID> [reason]` or `{PREFIX}hardban list`."))
    try: await ctx.guild.ban(discord.Object(id=user_id), reason=f"Hardban by {ctx.author}: {reason}", delete_message_seconds=0)
    except discord.HTTPException: return await ctx.send(embed=make_embed("hardban failed", "Discord denied the ban."))
    data=_load_json_config("hardbans.json", {}); data.setdefault(str(ctx.guild.id), {})[str(user_id)]={"reason":reason,"moderator":ctx.author.id,"time":int(time.time())}; _save_json_file("hardbans.json", data)
    await ctx.send(embed=make_embed("hardban added", f"User `{user_id}` has been hardbanned.\n\n**Reason**\n{reason}"))

@bot.command(name="hardbanlist", aliases=["hardban-list"])
@commands.has_permissions(administrator=True)
async def hardbanlist(ctx):
    data=_load_json_config("hardbans.json", {}).get(str(ctx.guild.id), {})
    lines=[f"`{uid}` · {entry.get('reason','No reason')}" for uid,entry in list(data.items())[-40:]]
    await ctx.send(embed=make_embed("hardbanned users", "\n".join(lines) or "no hardbans recorded."))

# Keep command directory/help metadata aligned with the added commands.
CATEGORIES.extend([
    ("Threads", ["thread", "thread rename", "thread lock", "thread unlock", "thread add", "thread remove", "thread watch"]),
    ("Additional Moderation", ["tempban", "softban", "jail", "unjail", "timeoutlist", "stripstaff", "hardban", "hardbanlist", "banpurge"]),
    ("Server Tools", ["moveall", "drag", "clearinvites", "newmembers", "recentban", "hide", "unhide"]),
])
COMMAND_INFO.update({
    "tempban": ("Temporarily ban a member; the bot schedules an automatic unban while it remains online.", "tempban <member> <duration> [reason]", "tempban @user 2d repeated spam", ["tban"]),
    "softban": ("Ban and immediately unban a member, optionally deleting recent message history.", "softban <member> [delete-seconds] [reason]", "softban @user 86400 spam", []),
    "timeoutlist": ("List members currently timed out.", "timeoutlist", "timeoutlist", ["timeout-list"]),
    "jail": ("Create/use a Jailed role, remove manageable roles, and schedule release.", "jail <member> [duration] [reason]", "jail @user 1h disruption", []),
    "unjail": ("Release a member from the saved jail list and restore saved roles.", "unjail <member> [reason]", "unjail @user appeal accepted", []),
    "moveall": ("Move everyone in your current voice channel to another voice channel.", "moveall <voice channel>", "moveall #General Voice", []),
    "drag": ("Move specified members to a voice channel.", "drag <members...> <voice channel>", "drag @user #General Voice", []),
    "stripstaff": ("Remove configured moderation roles from a member.", "stripstaff <member>", "stripstaff @user", []),
    "clearinvites": ("Delete all server invites.", "clearinvites", "clearinvites", []),
    "newmembers": ("List the most recently joined members.", "newmembers [count]", "newmembers 20", []),
    "recentban": ("Ban a number of members who joined within the last seven days.", "recentban [count] [reason]", "recentban 5 raid", []),
    "hide": ("Hide a channel from a member or @everyone.", "hide [channel] [member]", "hide #general @everyone", []),
    "unhide": ("Restore default channel visibility for a member or @everyone.", "unhide [channel] [member]", "unhide #general @everyone", []),
    "thread": ("Manage threads and forum posts.", "thread <subcommand>", "thread lock #thread", []),
    "thread rename": ("Rename a thread.", "thread rename <thread> <new name>", "thread rename #discussion Updates", []),
    "thread lock": ("Lock a thread or forum post.", "thread lock <thread> [reason]", "thread lock #discussion spam", []),
    "thread unlock": ("Unlock a thread or forum post.", "thread unlock <thread> [reason]", "thread unlock #discussion reopened", []),
    "thread add": ("Add a member to a thread.", "thread add <thread> <member>", "thread add #discussion @user", []),
    "thread remove": ("Remove a member from a thread.", "thread remove <thread> <member>", "thread remove #discussion @user", []),
    "thread watch": ("Toggle a thread in the saved watch list, or list watched threads.", "thread watch [thread]", "thread watch #discussion", []),
    "banpurge": ("Set the configured default message deletion window for future bans.", "banpurge [seconds]", "banpurge 86400", []),
    "hardban": ("Ban a user and record them in the hardban list.", "hardban <user ID> [reason]", "hardban 123456789012345678 ban evasion", []),
    "hardbanlist": ("View users recorded in the hardban list.", "hardbanlist", "hardbanlist", ["hardban-list"]),
})



# =========================
# Full supplied command-list expansion
# =========================

# Small persistence helpers used by management commands.
def _guild_cfg_section(ctx, section):
    cfg = guild_cfg(ctx.guild.id)
    return cfg.setdefault(section, {})

def _can_manage_messages(ctx):
    return bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_messages or any(r.id in WARN_ROLES for r in ctx.author.roles)))

def _case_lookup(ctx, case_id):
    for uid, entries in modlog_data[ctx.guild.id].items():
        for idx, entry in enumerate(entries):
            if str(entry.get("case_id", "")) == str(case_id) or str(entry.get("id", "")) == str(case_id):
                return uid, idx, entry
    return None

@remind.command(name="list")
async def remind_list(ctx):
    data = _load_json_config("reminders.json", {})
    items = data.get(str(ctx.author.id), [])
    body = "\n".join(f"`{x.get('id')}` · <t:{int(x.get('due', 0))}:R> · {str(x.get('message',''))[:100]}" for x in items[:15]) or "You have no active reminders."
    await ctx.send(embed=make_embed("your reminders", body))

@remind.command(name="remove")
async def remind_remove(ctx, reminder_id: int):
    data = _load_json_config("reminders.json", {})
    key = str(ctx.author.id); items = data.get(key, [])
    kept = [x for x in items if int(x.get("id", 0)) != reminder_id]
    if len(kept) == len(items):
        return await ctx.send(embed=make_embed("reminders", "that reminder ID was not found."))
    data[key] = kept; _save_json_file("reminders.json", data)
    await ctx.send(embed=make_embed("reminders", f"removed reminder `{reminder_id}`. It will no longer be delivered if its task has not already started."))

@bot.command(name="reminders")
async def reminders_cmd(ctx):
    await remind_list(ctx)

# Thread watch list command omitted from the original list implementation.
@bot.group(name="proof", invoke_without_command=True)
@commands.has_permissions(manage_messages=True)
async def proof(ctx):
    await ctx.send(embed=make_embed("proof", f"usage: `{PREFIX}proof <set|add|list|view|remove> <case id> ...`"))

@proof.command(name="set")
@commands.has_permissions(manage_messages=True)
async def proof_set(ctx, case_id: str, *, explanation: str):
    found = _case_lookup(ctx, case_id)
    if not found: return await ctx.send(embed=make_embed("proof", "case ID not found."))
    uid, idx, entry = found; entry["proof"] = explanation[:1000]; save_modlogs()
    await ctx.send(embed=make_embed("proof updated", f"saved proof explanation for case `{case_id}`."))

@proof.command(name="add")
@commands.has_permissions(manage_messages=True)
async def proof_add(ctx, case_id: str, media_url: str):
    found = _case_lookup(ctx, case_id)
    if not found: return await ctx.send(embed=make_embed("proof", "case ID not found."))
    uid, idx, entry = found; attachments = entry.setdefault("attachments", [])
    if not media_url.startswith(("https://", "http://")): return await ctx.send(embed=make_embed("proof", "provide a valid http(s) media URL."))
    attachments.append(media_url[:500]); entry["attachments"] = attachments[-10:]; save_modlogs()
    await ctx.send(embed=make_embed("proof", f"added attachment to case `{case_id}`."))

@proof.command(name="list")
@commands.has_permissions(manage_messages=True)
async def proof_list(ctx, case_id: str):
    found = _case_lookup(ctx, case_id)
    if not found: return await ctx.send(embed=make_embed("proof", "case ID not found."))
    entry = found[2]; lines = [f"**Explanation:** {entry.get('proof','none')}"]
    lines += [f"`{i}` {url}" for i, url in enumerate(entry.get("attachments", []), 1)]
    await ctx.send(embed=make_embed(f"proof · case {case_id}", "\n".join(lines)))

@proof.command(name="view")
@commands.has_permissions(manage_messages=True)
async def proof_view(ctx, case_id: str):
    await proof_list(ctx, case_id)

@proof.command(name="remove")
@commands.has_permissions(manage_messages=True)
async def proof_remove(ctx, case_id: str, index: int):
    found = _case_lookup(ctx, case_id)
    if not found: return await ctx.send(embed=make_embed("proof", "case ID not found."))
    entry = found[2]; attachments = entry.get("attachments", [])
    if index < 1 or index > len(attachments): return await ctx.send(embed=make_embed("proof", "attachment index not found."))
    attachments.pop(index-1); save_modlogs(); await ctx.send(embed=make_embed("proof", f"removed attachment `{index}` from case `{case_id}`."))

@cases.command(name="view")
@commands.has_permissions(manage_messages=True)
async def history_view(ctx, case_id: str):
    found = _case_lookup(ctx, case_id)
    if not found: return await ctx.send(embed=make_embed("history", "case ID not found."))
    uid, idx, entry = found
    await ctx.send(embed=make_embed(f"case {case_id}", f"**Member:** <@{uid}>\n**Action:** {entry.get('action','UNKNOWN')}\n**Reason:** {entry.get('reason','No reason provided')}\n**Moderator:** <@{entry.get('moderator_id',0)}>\n**Time:** <t:{int(entry.get('timestamp',time.time()))}:F>"))

@cases.command(name="remove")
@commands.has_permissions(manage_messages=True)
async def history_remove(ctx, member: discord.Member, case_id: str):
    if not ctx.author.guild_permissions.administrator and not any(r.id in WARN_ROLES for r in ctx.author.roles): return
    entries = modlog_data[ctx.guild.id].get(member.id, [])
    idx = next((i for i, entry in enumerate(entries) if str(entry.get("case_id", "")) == str(case_id)), -1)
    if idx < 0:
        try: idx = int(case_id) - 1
        except ValueError: idx = -1
    if idx < 0 or idx >= len(entries): return await ctx.send(embed=make_embed("history", "case not found for that member."))
    entries.pop(idx); save_modlogs(); await ctx.send(embed=make_embed("history", f"removed case `{case_id}` for {member.mention}."))

@cases.command(name="removeall")
@commands.has_permissions(administrator=True)
async def history_removeall(ctx, member: discord.Member):
    modlog_data[ctx.guild.id].pop(member.id, None); save_modlogs()
    warning_data[ctx.guild.id].pop(member.id, None)
    await ctx.send(embed=make_embed("history", f"cleared stored punishment history for {member.mention}."))


@mute.command(name="list")
@commands.has_permissions(moderate_members=True)
async def timeout_list_sub(ctx):
    members=[m for m in ctx.guild.members if m.timed_out_until and m.timed_out_until > discord.utils.utcnow()]
    body="\n".join(f"{m.mention} · <t:{int(m.timed_out_until.timestamp())}:R>" for m in members[:30]) or "No members are currently timed out."
    await ctx.send(embed=make_embed("timed out members", body))

@hardban.command(name="list")
@commands.has_permissions(administrator=True)
async def hardban_list_sub(ctx):
    await hardbanlist(ctx)

@modnote.command(name="add")
async def notes_add_sub(ctx, member: discord.Member, *, note: str):
    await modnote(ctx, "add", member, note=note)

@modnote.command(name="clear")
async def notes_clear_sub(ctx, member: discord.Member):
    await modnote(ctx, "clear", member)

@modnote.command(name="list")
async def notes_list_sub(ctx, member: discord.Member):
    await modnote(ctx, "list", member)

@modnote.command(name="remove")
async def notes_remove_sub(ctx, member: discord.Member, note_id: int):
    if not (ctx.author.guild_permissions.administrator or any(r.id in WARN_ROLES for r in ctx.author.roles)): return
    cfg=guild_cfg(ctx.guild.id); notes=cfg.setdefault("notes",{}).setdefault(str(member.id),[])
    if note_id < 1 or note_id > len(notes): return await ctx.send(embed=make_embed("mod notes", "note ID not found."))
    notes.pop(note_id-1); save_ultimate_config(); await ctx.send(embed=make_embed("mod notes", f"removed note `{note_id}` for {member.mention}."))

@bot.command(name="reason")
@commands.has_permissions(manage_messages=True)
async def reason_cmd(ctx, case_id: str, *, new_reason: str):
    found=_case_lookup(ctx,case_id)
    if not found: return await ctx.send(embed=make_embed("case reason", "case ID not found."))
    uid,idx,entry=found; entry["reason"]=new_reason[:500]; entry["reason_updated_by"]=ctx.author.id; entry["reason_updated_at"]=int(time.time()); save_modlogs()
    await ctx.send(embed=make_embed("case reason updated", f"updated reason for case `{case_id}`."))

@bot.command(name="setup")
@commands.has_permissions(administrator=True, manage_channels=True, manage_roles=True)
async def setup_moderation(ctx):
    log_channel=discord.utils.get(ctx.guild.text_channels,name="mod-logs")
    if log_channel is None: log_channel=await ctx.guild.create_text_channel("mod-logs", reason=f"moderation setup by {ctx.author}")
    muted=discord.utils.get(ctx.guild.roles,name="Muted")
    if muted is None: muted=await ctx.guild.create_role(name="Muted",reason=f"moderation setup by {ctx.author}")
    for channel in ctx.guild.text_channels:
        try:
            ow=channel.overwrites_for(muted); ow.send_messages=False; ow.add_reactions=False
            await channel.set_permissions(muted,overwrite=ow,reason="moderation setup")
        except (discord.Forbidden,discord.HTTPException): pass
    cfg=guild_cfg(ctx.guild.id); cfg["modlog_channel"]=log_channel.id; cfg["muted_role"]=muted.id; save_ultimate_config()
    await ctx.send(embed=make_embed("moderation setup complete", f"**Mod logs:** {log_channel.mention}\n**Muted role:** {muted.mention}"))

@bot.command(name="caselog")
@commands.has_permissions(manage_messages=True)
async def caselog(ctx, case_id: str):
    await history_view(ctx, case_id)

@bot.command(name="moderationhistory")
@commands.has_permissions(manage_messages=True)
async def moderationhistory(ctx, member: discord.Member, command: str = None):
    rows=[]
    for uid, entries in modlog_data[ctx.guild.id].items():
        for e in entries:
            if int(e.get("moderator_id",0)) == member.id and (not command or e.get("action","").lower() == command.lower()):
                rows.append((int(e.get("timestamp",0)), uid, e))
    rows.sort(reverse=True); body="\n".join(f"<@{uid}> · **{e.get('action')}** · {e.get('reason','')} · <t:{ts}:R>" for ts,uid,e in rows[:15]) or "No matching moderation actions."
    await ctx.send(embed=make_embed(f"moderation history · {member}", body))

@bot.command(name="jaillist")
@commands.has_permissions(manage_messages=True)
async def jaillist(ctx):
    data = _load_json_config("jail_config.json", {}).get(str(ctx.guild.id), {})
    body = "\n".join(f"<@{uid}> · {info.get('reason','No reason')}" for uid, info in data.items()) or "No saved jailed members."
    await ctx.send(embed=make_embed("jailed members", body[:4000]))

@bot.group(name="temprole", invoke_without_command=True)
@commands.has_permissions(manage_roles=True)
async def temprole(ctx, member: discord.Member = None, duration: str = None, role: discord.Role = None):
    if not member or not duration or not role: return await ctx.send(embed=make_embed("temprole", f"usage: `{PREFIX}temprole <member> <duration> <role>`"))
    seconds = parse_duration(duration)
    if not seconds or seconds < 1: return await ctx.send(embed=make_embed("temprole", "duration example: `30m`, `2h`, `3d`."))
    if role >= ctx.guild.me.top_role or (not ctx.author.guild_permissions.administrator and role >= ctx.author.top_role): return await ctx.send(embed=make_embed("temprole", "that role is too high."))
    await member.add_roles(role, reason=f"temporary role by {ctx.author}")
    data = _load_json_config("temprole.json", {}); gid=str(ctx.guild.id); data.setdefault(gid,[]).append({"member":member.id,"role":role.id,"due":int(time.time()+seconds)}) ; _save_json_file("temprole.json",data)
    async def remove_later():
        await asyncio.sleep(seconds)
        try: await member.remove_roles(role, reason="temporary role expired")
        except (discord.Forbidden, discord.HTTPException): pass
        d=_load_json_config("temprole.json",{}); d[gid]=[x for x in d.get(gid,[]) if not (x.get("member")==member.id and x.get("role")==role.id)]; _save_json_file("temprole.json",d)
    bot.loop.create_task(remove_later())
    await ctx.send(embed=make_embed("temporary role", f"gave {role.mention} to {member.mention} until <t:{int(time.time()+seconds)}:R>."))

@temprole.command(name="list")
@commands.has_permissions(manage_roles=True)
async def temprole_list(ctx):
    data=_load_json_config("temprole.json",{}).get(str(ctx.guild.id),[])
    body="\n".join(f"<@{x['member']}> · <@&{x['role']}> · <t:{int(x['due'])}:R>" for x in data) or "No temporary roles saved."
    await ctx.send(embed=make_embed("temporary roles", body[:4000]))

@bot.group(name="stickyrole", invoke_without_command=True)
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def stickyrole(ctx):
    await ctx.send(embed=make_embed("stickyrole", f"usage: `{PREFIX}stickyrole <add|remove|list> <member> <role>`"))

@stickyrole.command(name="add")
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def stickyrole_add(ctx, member: discord.Member, role: discord.Role):
    d=_load_json_config("stickyrole.json",{}); g=d.setdefault(str(ctx.guild.id),{}); g[str(member.id)]=sorted(set(g.get(str(member.id),[])+[role.id])); _save_json_file("stickyrole.json",d)
    await ctx.send(embed=make_embed("sticky role", f"will reapply {role.mention} to {member.mention} if they rejoin."))

@stickyrole.command(name="remove")
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def stickyrole_remove(ctx, member: discord.Member, role: discord.Role):
    d=_load_json_config("stickyrole.json",{}); g=d.setdefault(str(ctx.guild.id),{}); g[str(member.id)]=[x for x in g.get(str(member.id),[]) if int(x)!=role.id]; _save_json_file("stickyrole.json",d)
    await ctx.send(embed=make_embed("sticky role", f"removed sticky-role setting for {member.mention} / {role.mention}."))

@stickyrole.command(name="list")
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def stickyrole_list(ctx):
    d=_load_json_config("stickyrole.json",{}).get(str(ctx.guild.id),{}); body="\n".join(f"<@{uid}> → {', '.join(f'<@&{rid}>' for rid in roles)}" for uid,roles in d.items()) or "No sticky roles configured."
    await ctx.send(embed=make_embed("sticky roles", body[:4000]))

@bot.group(name="restrictcommand", aliases=["restrictcmd"], invoke_without_command=True)
@commands.has_guild_permissions(manage_guild=True)
async def restrictcommand(ctx, command_name: str = None, role: discord.Role = None):
    if not command_name or not role: return await ctx.send(embed=make_embed("restrict command", f"usage: `{PREFIX}restrictcommand add <command> <role>`"))
    d=_load_json_config("restricted_commands.json",{}); d.setdefault(str(ctx.guild.id),{}).setdefault(command_name.lower(),[]).append(role.id); _save_json_file("restricted_commands.json",d)
    await ctx.send(embed=make_embed("restrict command", f"{role.mention} can now use `{command_name}` as an allowed role."))

@restrictcommand.command(name="add")
@commands.has_guild_permissions(manage_guild=True)
async def restrictcommand_add(ctx, command_name: str, role: discord.Role):
    d=_load_json_config("restricted_commands.json",{}); items=d.setdefault(str(ctx.guild.id),{}).setdefault(command_name.lower(),[])
    if role.id not in items: items.append(role.id)
    _save_json_file("restricted_commands.json",d); await ctx.send(embed=make_embed("restrict command", f"added {role.mention} for `{command_name}`."))

@restrictcommand.command(name="remove")
@commands.has_guild_permissions(manage_guild=True)
async def restrictcommand_remove(ctx, command_name: str, role: discord.Role):
    d=_load_json_config("restricted_commands.json",{}); items=d.setdefault(str(ctx.guild.id),{}).get(command_name.lower(),[]); d[str(ctx.guild.id)][command_name.lower()]=[x for x in items if int(x)!=role.id]; _save_json_file("restricted_commands.json",d)
    await ctx.send(embed=make_embed("restrict command", f"removed {role.mention} from `{command_name}` restrictions."))

@restrictcommand.command(name="list")
@commands.has_guild_permissions(manage_guild=True)
async def restrictcommand_list(ctx):
    d=_load_json_config("restricted_commands.json",{}).get(str(ctx.guild.id),{}); body="\n".join(f"`{cmd}`: {', '.join(f'<@&{rid}>' for rid in roles)}" for cmd,roles in d.items()) or "No restricted commands configured."
    await ctx.send(embed=make_embed("restricted commands", body[:4000]))

@restrictcommand.command(name="reset")
@commands.has_guild_permissions(manage_guild=True)
async def restrictcommand_reset(ctx):
    d=_load_json_config("restricted_commands.json",{}); d[str(ctx.guild.id)]={}; _save_json_file("restricted_commands.json",d); await ctx.send(embed=make_embed("restricted commands", "cleared all command restrictions."))

@bot.group(name="nuke", invoke_without_command=True)
@commands.has_permissions(administrator=True)
async def nuke(ctx):
    clone = await ctx.channel.clone(reason=f"channel cloned by {ctx.author}")
    await clone.edit(position=ctx.channel.position)
    await ctx.channel.delete(reason=f"channel nuked by {ctx.author}")
    await clone.send(embed=make_embed("channel nuked", f"channel recreated by {ctx.author.mention}."))

@slowmode.command(name="on")
@commands.has_permissions(manage_channels=True)
async def slowmode_on(ctx, channel: discord.TextChannel = None, delay: str = "5s"):
    channel=channel or ctx.channel; seconds=parse_duration(delay)
    if seconds is None: 
        try: seconds=int(delay)
        except ValueError: seconds=None
    if seconds is None or not 0 <= seconds <= 21600: return await ctx.send(embed=make_embed("slowmode", "delay must be seconds or a duration like `10s`."))
    await channel.edit(slowmode_delay=seconds); await ctx.send(embed=make_embed("slowmode", f"enabled slowmode on {channel.mention} (`{seconds}s`)."))

@slowmode.command(name="off")
@commands.has_permissions(manage_channels=True)
async def slowmode_off(ctx, channel: discord.TextChannel = None):
    channel=channel or ctx.channel; await channel.edit(slowmode_delay=0); await ctx.send(embed=make_embed("slowmode", f"disabled slowmode on {channel.mention}."))

@bot.command(name="untimeout", aliases=["untimeoutmember"])
@commands.has_permissions(moderate_members=True)
async def untimeout_cmd(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.timeout(None, reason=f"{ctx.author}: {reason}"); record_modlog(ctx.guild, member, "UNTIMEOUT", ctx.author, reason)
    await ctx.send(embed=make_embed("timeout removed", f"removed timeout for {member.mention}."))

@bot.command(name="imute")
@commands.has_permissions(moderate_members=True)
async def imute(ctx, member: discord.Member, *, reason="No reason provided"):
    ow=ctx.channel.overwrites_for(member); ow.attach_files=False; ow.embed_links=False; await ctx.channel.set_permissions(member, overwrite=ow, reason=reason)
    record_modlog(ctx.guild, member, "IMUTE", ctx.author, reason); await ctx.send(embed=make_embed("imute", f"disabled file attachments and embeds for {member.mention} in {ctx.channel.mention}."))

@bot.command(name="iunmute")
@commands.has_permissions(moderate_members=True)
async def iunmute(ctx, member: discord.Member, *, reason="No reason provided"):
    ow=ctx.channel.overwrites_for(member); ow.attach_files=None; ow.embed_links=None; await ctx.channel.set_permissions(member, overwrite=ow, reason=reason)
    record_modlog(ctx.guild, member, "IUNMUTE", ctx.author, reason); await ctx.send(embed=make_embed("iunmute", f"restored file attachments and embeds for {member.mention} in {ctx.channel.mention}."))

@bot.command(name="rmute")
@commands.has_permissions(moderate_members=True)
async def rmute(ctx, member: discord.Member, *, reason="No reason provided"):
    ow=ctx.channel.overwrites_for(member); ow.add_reactions=False; ow.use_external_emojis=False; await ctx.channel.set_permissions(member, overwrite=ow, reason=reason)
    record_modlog(ctx.guild, member, "RMUTE", ctx.author, reason); await ctx.send(embed=make_embed("rmute", f"disabled reactions and external emojis for {member.mention} in {ctx.channel.mention}."))

@bot.command(name="runmute")
@commands.has_permissions(moderate_members=True)
async def runmute(ctx, member: discord.Member, *, reason="No reason provided"):
    ow=ctx.channel.overwrites_for(member); ow.add_reactions=None; ow.use_external_emojis=None; await ctx.channel.set_permissions(member, overwrite=ow, reason=reason)
    record_modlog(ctx.guild, member, "RUNMUTE", ctx.author, reason); await ctx.send(embed=make_embed("runmute", f"restored reactions and external emojis for {member.mention} in {ctx.channel.mention}."))

@bot.command(name="rename")
@commands.has_permissions(manage_nicknames=True)
async def rename_cmd(ctx, member: discord.Member, *, newnick: str):
    if not target_ok(ctx, member): return await ctx.send(embed=make_embed("rename", "you can't rename that member."))
    await member.edit(nick=newnick[:32], reason=f"renamed by {ctx.author}"); await ctx.send(embed=make_embed("nickname updated", f"set {member.mention}'s nickname to **{newnick[:32]}**."))

@bot.group(name="forcenickname", invoke_without_command=True)
@commands.has_guild_permissions(manage_guild=True, manage_nicknames=True)
async def forcenickname(ctx, member: discord.Member = None, *, nickname: str = None):
    if member is None or not nickname: return await ctx.send(embed=make_embed("forced nickname", f"usage: `{PREFIX}forcenickname <member> <nickname>` or `{PREFIX}forcenickname list`."))
    d=_load_json_config("forced_nicknames.json",{}); d.setdefault(str(ctx.guild.id),{})[str(member.id)]=nickname[:32]; _save_json_file("forced_nicknames.json",d)
    await member.edit(nick=nickname[:32], reason=f"forced nickname set by {ctx.author}"); await ctx.send(embed=make_embed("forced nickname", f"saved nickname for {member.mention}."))

@forcenickname.command(name="list")
@commands.has_guild_permissions(manage_guild=True, manage_nicknames=True)
async def forcenickname_list(ctx):
    d=_load_json_config("forced_nicknames.json",{}).get(str(ctx.guild.id),{}); body="\n".join(f"<@{uid}> · `{nick}`" for uid,nick in d.items()) or "No forced nicknames saved."
    await ctx.send(embed=make_embed("forced nicknames", body[:4000]))

@bot.command(name="talk")
@commands.has_permissions(manage_channels=True)
async def talk(ctx, channel: discord.TextChannel, role: discord.Role):
    ow=channel.overwrites_for(role); ow.view_channel=True; ow.send_messages=True; await channel.set_permissions(role, overwrite=ow, reason=f"talk enabled by {ctx.author}")
    await ctx.send(embed=make_embed("channel access", f"allowed {role.mention} to view and talk in {channel.mention}."))

@bot.command(name="revokefiles")
@commands.has_permissions(manage_channels=True)
async def revokefiles(ctx, setting: str = None, channel: discord.TextChannel = None):
    if setting not in ("on", "off"): return await ctx.send(embed=make_embed("revokefiles", f"usage: `{PREFIX}revokefiles <on|off> [channel]`."))
    channel=channel or ctx.channel; ow=channel.overwrites_for(ctx.guild.default_role); value=False if setting == "on" else None
    ow.attach_files=value; ow.embed_links=value; await channel.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"revokefiles {setting} by {ctx.author}")
    await ctx.send(embed=make_embed("revokefiles", f"updated file/embed permissions in {channel.mention}."))

@bot.command(name="naughty")
@commands.has_permissions(manage_channels=True)
async def naughty(ctx, channel: discord.TextChannel = None):
    channel=channel or ctx.channel
    if not hasattr(channel, "nsfw"): return await ctx.send(embed=make_embed("naughty", "that channel does not support NSFW settings."))
    await channel.edit(nsfw=True); await ctx.send(embed=make_embed("naughty", f"marked {channel.mention} as NSFW for 30 seconds.")); await asyncio.sleep(30)
    try: await channel.edit(nsfw=False)
    except (discord.Forbidden, discord.HTTPException): pass

@bot.command(name="setupmute")
@commands.has_guild_permissions(manage_guild=True, manage_channels=True)
async def setupmute(ctx):
    role=discord.utils.get(ctx.guild.roles, name="Muted")
    if role is None: role=await ctx.guild.create_role(name="Muted", reason=f"mute setup by {ctx.author}")
    changed=0
    for channel in ctx.guild.channels:
        try:
            ow=channel.overwrites_for(role)
            if isinstance(channel, (discord.TextChannel, discord.ForumChannel, discord.Thread)):
                ow.send_messages=False; ow.add_reactions=False
            if isinstance(channel, discord.VoiceChannel): ow.speak=False
            await channel.set_permissions(role, overwrite=ow, reason="muted role setup"); changed+=1
        except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("mute setup", f"configured {role.mention} across `{changed}` channels."))

@bot.command(name="permissions")
@commands.has_guild_permissions(manage_roles=True)
async def permissions_cmd(ctx, member: discord.Member = None, channel: discord.TextChannel = None):
    member=member or ctx.author; channel=channel or ctx.channel; perms=channel.permissions_for(member)
    names=[name.replace('_',' ').title() for name,value in perms if value]
    await ctx.send(embed=make_embed(f"permissions · {member.display_name}", f"**Channel:** {channel.mention}\n" + (", ".join(names[:60]) or "No permissions")))

@bot.group(name="unbanall", invoke_without_command=True)
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def unbanall(ctx):
    data=_load_json_config("unbanall_tasks.json",{}); data[str(ctx.guild.id)]={"started":int(time.time()),"cancel":False}; _save_json_file("unbanall_tasks.json",data)
    bans=[entry async for entry in ctx.guild.bans()]; unbanned=0
    for entry in bans:
        state=_load_json_config("unbanall_tasks.json",{}).get(str(ctx.guild.id),{})
        if state.get("cancel"): break
        try: await ctx.guild.unban(entry.user, reason=f"unbanall by server owner {ctx.author}"); unbanned+=1
        except (discord.Forbidden, discord.HTTPException): pass
        await asyncio.sleep(1)
    data=_load_json_config("unbanall_tasks.json",{}); data.pop(str(ctx.guild.id),None); _save_json_file("unbanall_tasks.json",data)
    await ctx.send(embed=make_embed("unbanall", f"unbanned `{unbanned}` users."))

@unbanall.command(name="cancel")
@commands.check(lambda ctx: bool(ctx.guild and ctx.author.id == ctx.guild.owner_id))
async def unbanall_cancel(ctx):
    data=_load_json_config("unbanall_tasks.json",{}); task=data.setdefault(str(ctx.guild.id),{}); task["cancel"]=True; _save_json_file("unbanall_tasks.json",data)
    await ctx.send(embed=make_embed("unbanall", "cancellation requested."))

@bot.command(name="roleicon")
@commands.has_permissions(manage_roles=True)
async def roleicon(ctx, role: discord.Role, url: str):
    if not hasattr(role, "edit") or not hasattr(role, "display_icon"):
        return await ctx.send(embed=make_embed("role icon", "this Discord server/API configuration may not support role icons."))
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200: return await ctx.send(embed=make_embed("role icon", "could not download that image URL."))
                data=await resp.read()
        await role.edit(display_icon=data, reason=f"role icon set by {ctx.author}")
    except (discord.HTTPException, discord.Forbidden, aiohttp.ClientError, ValueError):
        return await ctx.send(embed=make_embed("role icon", "could not set that role icon; check the URL, role position, and server boost requirements."))
    await ctx.send(embed=make_embed("role icon", f"updated icon for {role.mention}."))

@bot.command(name="rolementionable")
@commands.has_permissions(manage_roles=True)
async def rolementionable(ctx, role: discord.Role):
    await role.edit(mentionable=not role.mentionable, reason=f"role mentionable toggled by {ctx.author}")
    await ctx.send(embed=make_embed("role mentionable", f"{role.mention} mentionable: **{not role.mentionable}**."))

@bot.command(name="rolehoist")
@commands.has_permissions(manage_roles=True)
async def rolehoist(ctx, role: discord.Role):
    await role.edit(hoist=not role.hoist, reason=f"role hoist toggled by {ctx.author}")
    await ctx.send(embed=make_embed("role hoist", f"{role.mention} hoisted: **{not role.hoist}**."))

@bot.command(name="rolecolor", aliases=["rolecolour"])
@commands.has_permissions(manage_roles=True)
async def rolecolor(ctx, role: discord.Role, colour: str):
    raw=colour.lstrip("#")
    try: value=int(raw,16)
    except ValueError: return await ctx.send(embed=make_embed("role color", "use a hex color like `#efcead`."))
    if len(raw) != 6: return await ctx.send(embed=make_embed("role color", "use a six-digit hex color like `#efcead`."))
    await role.edit(colour=discord.Colour(value), reason=f"role color set by {ctx.author}"); await ctx.send(embed=make_embed("role color", f"updated {role.mention} to `#{raw.lower()}`."))

@bot.command(name="rolecreate")
@commands.has_permissions(manage_roles=True)
async def rolecreate(ctx, *, name: str):
    role=await ctx.guild.create_role(name=name[:100], reason=f"role created by {ctx.author}"); await ctx.send(embed=make_embed("role created", f"created {role.mention}."))

@bot.command(name="roleedit")
@commands.has_permissions(manage_roles=True)
async def roleedit(ctx, role: discord.Role, *, name: str):
    old=role.name; await role.edit(name=name[:100], reason=f"role renamed by {ctx.author}"); await ctx.send(embed=make_embed("role edited", f"renamed `{old}` to {role.mention}."))

@bot.command(name="rolehumans")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def rolehumans(ctx, role: discord.Role):
    count=0
    for member in ctx.guild.members:
        if not member.bot and role not in member.roles:
            try: await member.add_roles(role, reason=f"bulk role by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role humans", f"added {role.mention} to `{count}` humans."))

@bot.command(name="rolehumansremove")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def rolehumansremove(ctx, role: discord.Role):
    count=0
    for member in ctx.guild.members:
        if not member.bot and role in member.roles:
            try: await member.remove_roles(role, reason=f"bulk role removal by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role humans", f"removed {role.mention} from `{count}` humans."))

@bot.command(name="rolebots")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def rolebots(ctx, role: discord.Role):
    count=0
    for member in ctx.guild.members:
        if member.bot and role not in member.roles:
            try: await member.add_roles(role, reason=f"bulk bot role by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role bots", f"added {role.mention} to `{count}` bots."))

@bot.command(name="rolebotsremove")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def rolebotsremove(ctx, role: discord.Role):
    count=0
    for member in ctx.guild.members:
        if member.bot and role in member.roles:
            try: await member.remove_roles(role, reason=f"bulk bot role removal by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role bots", f"removed {role.mention} from `{count}` bots."))

@bot.command(name="dump")
@commands.has_permissions(manage_roles=True)
async def dump(ctx, role: discord.Role):
    members=[m for m in ctx.guild.members if role in m.roles]
    data="\n".join(f"{m} ({m.id})" for m in members) or "No members have that role."
    file=discord.File(io.BytesIO(data.encode()), filename=f"role-{role.id}-members.txt")
    await ctx.send(embed=make_embed("role dump", f"exported `{len(members)}` members with {role.mention}."), file=file)

@lockdown.command(name="all")
@commands.has_permissions(manage_channels=True)
async def lockdown_all(ctx, *, reason="Server lockdown"):
    ctx.command=bot.get_command("lockdown"); await lockdown(ctx, None, reason=reason)

@lockdown.command(name="role")
@commands.has_guild_permissions(manage_guild=True)
async def lockdown_role(ctx, role: discord.Role):
    cfg=_guild_cfg_section(ctx,"lockdown"); cfg["role_id"]=role.id; save_ultimate_config(); await ctx.send(embed=make_embed("lockdown role", f"saved {role.mention} as the lockdown role."))

@lockdown.group(name="ignore", invoke_without_command=True)
@commands.has_guild_permissions(manage_guild=True)
async def lockdown_ignore(ctx):
    ignored=_guild_cfg_section(ctx,"lockdown").get("ignored",[]); body="\n".join(f"<#{cid}>" for cid in ignored) or "No ignored channels."
    await ctx.send(embed=make_embed("lockdown ignored channels", body))

@lockdown_ignore.command(name="add")
@commands.has_guild_permissions(manage_guild=True)
async def lockdown_ignore_add(ctx, channel: discord.TextChannel):
    cfg=_guild_cfg_section(ctx,"lockdown"); cfg["ignored"]=list(set(cfg.get("ignored",[])+[channel.id])); save_ultimate_config(); await ctx.send(embed=make_embed("lockdown", f"added {channel.mention} to the ignore list."))

@lockdown_ignore.command(name="remove")
@commands.has_guild_permissions(manage_guild=True)
async def lockdown_ignore_remove(ctx, channel: discord.TextChannel):
    cfg=_guild_cfg_section(ctx,"lockdown"); cfg["ignored"]=[x for x in cfg.get("ignored",[]) if int(x)!=channel.id]; save_ultimate_config(); await ctx.send(embed=make_embed("lockdown", f"removed {channel.mention} from the ignore list."))

@lockdown_ignore.command(name="list")
@commands.has_guild_permissions(manage_guild=True)
async def lockdown_ignore_list(ctx):
    await lockdown_ignore(ctx)

@unlock.command(name="all")
@commands.has_permissions(manage_channels=True)
async def unlock_all(ctx):
    await unlockall(ctx)

@purge.command(name="links")
@commands.has_permissions(manage_messages=True)
async def purge_links(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: bool(re.search(r"https?://|www\.", m.content, re.I)), search)

@purge.command(name="webhooks")
@commands.has_permissions(manage_messages=True)
async def purge_webhooks(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: m.webhook_id is not None, search)

@purge.command(name="humans")
@commands.has_permissions(manage_messages=True)
async def purge_humans(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: not m.author.bot and m.author != ctx.author, search)

@purge.command(name="bots")
@commands.has_permissions(manage_messages=True)
async def purge_bots(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: m.author.bot, search)

@purge.command(name="embeds")
@commands.has_permissions(manage_messages=True)
async def purge_embeds(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: bool(m.embeds), search)

@purge.command(name="files")
@commands.has_permissions(manage_messages=True)
async def purge_files(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: bool(m.attachments), search)

@purge.command(name="images")
@commands.has_permissions(manage_messages=True)
async def purge_images(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: any(a.content_type and a.content_type.startswith("image/") for a in m.attachments) or bool(re.search(r"\.(png|jpe?g|gif|webp)(?:\?|$)", m.content, re.I)), search)

@purge.command(name="stickers")
@commands.has_permissions(manage_messages=True)
async def purge_stickers(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: bool(m.stickers), search)

@purge.command(name="reactions")
@commands.has_permissions(manage_messages=True)
async def purge_reactions(ctx, search: int = 100):
    deleted=0
    async for msg in ctx.channel.history(limit=max(1,min(search,500))):
        if msg.reactions:
            try:
                await msg.clear_reactions(); deleted+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("purge reactions", f"cleared reactions on `{deleted}` messages."), delete_after=5)

@purge.command(name="mentions")
@commands.has_permissions(manage_messages=True)
async def purge_mentions(ctx, member: discord.Member, search: int = 100):
    await _purge_filter(ctx, lambda m: member in m.mentions, search)

@purge.command(name="contains")
@commands.has_permissions(manage_messages=True)
async def purge_contains(ctx, *, substring: str):
    await _purge_filter(ctx, lambda m: substring.lower() in m.content.lower(), 100)

@purge.command(name="startswith")
@commands.has_permissions(manage_messages=True)
async def purge_startswith(ctx, *, substring: str):
    await _purge_filter(ctx, lambda m: m.content.lower().startswith(substring.lower()), 100)

@purge.command(name="endswith")
@commands.has_permissions(manage_messages=True)
async def purge_endswith(ctx, *, substring: str):
    await _purge_filter(ctx, lambda m: m.content.lower().endswith(substring.lower()), 100)

@purge.command(name="emoji")
@commands.has_permissions(manage_messages=True)
async def purge_emoji(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: bool(re.search(r"<a?:[a-zA-Z0-9_]+:\d+>|[\U0001F300-\U0001FAFF]",m.content)), search)

@purge.command(name="emotes")
@commands.has_permissions(manage_messages=True)
async def purge_emotes(ctx, search: int = 100):
    await purge_emoji(ctx, search)

@purge.command(name="activity")
@commands.has_permissions(manage_messages=True)
async def purge_activity(ctx, search: int = 100):
    await _purge_filter(ctx, lambda m: m.type != discord.MessageType.default, search)

@purge.command(name="before")
@commands.has_permissions(manage_messages=True)
async def purge_before(ctx, message_id: str):
    try: mid=int(re.search(r"\d{15,22}",message_id).group())
    except (AttributeError, ValueError): return await ctx.send(embed=make_embed("purge", "provide a message ID or message link."))
    ref=await ctx.channel.fetch_message(mid); deleted=await ctx.channel.purge(limit=100, before=ref, bulk=True)
    await ctx.send(embed=make_embed("purge", f"deleted `{len(deleted)}` messages before that message."), delete_after=5)

@purge.command(name="after")
@commands.has_permissions(manage_messages=True)
async def purge_after(ctx, message_id: str):
    try: mid=int(re.search(r"\d{15,22}",message_id).group())
    except (AttributeError, ValueError): return await ctx.send(embed=make_embed("purge", "provide a message ID or message link."))
    ref=await ctx.channel.fetch_message(mid); deleted=await ctx.channel.purge(limit=100, after=ref, bulk=True)
    await ctx.send(embed=make_embed("purge", f"deleted `{len(deleted)}` messages after that message."), delete_after=5)

@purge.command(name="upto")
@commands.has_permissions(manage_messages=True)
async def purge_upto(ctx, message_id: str):
    try: mid=int(re.search(r"\d{15,22}",message_id).group())
    except (AttributeError, ValueError): return await ctx.send(embed=make_embed("purge", "provide a message ID or message link."))
    ref=await ctx.channel.fetch_message(mid); deleted=await ctx.channel.purge(limit=100, before=ref, bulk=True); await ref.delete()
    await ctx.send(embed=make_embed("purge", f"deleted `{len(deleted)+1}` messages up to that message."), delete_after=5)

@purge.command(name="between")
@commands.has_permissions(manage_messages=True)
async def purge_between(ctx, start_id: str, finish_id: str):
    try: a=int(re.search(r"\d{15,22}",start_id).group()); b=int(re.search(r"\d{15,22}",finish_id).group())
    except (AttributeError, ValueError): return await ctx.send(embed=make_embed("purge", "provide two message IDs or links."))
    first=await ctx.channel.fetch_message(a); last=await ctx.channel.fetch_message(b)
    lo,hi=(first,last) if first.id<last.id else (last,first); deleted=await ctx.channel.purge(limit=500, after=lo, before=hi, bulk=True)
    await ctx.send(embed=make_embed("purge", f"deleted `{len(deleted)}` messages between those messages."), delete_after=5)

async def _purge_filter(ctx, predicate, search=100):
    if not bot_can(ctx,"manage_messages"): return await ctx.send(embed=make_embed("purge", "I need Manage Messages permission."))
    limit=max(1,min(int(search),500)); deleted=await ctx.channel.purge(limit=limit+1, check=lambda m: m.id != ctx.message.id and predicate(m), bulk=True)
    await ctx.send(embed=make_embed("purge", f"deleted `{len(deleted)}` matching messages."), delete_after=5)

# Remaining role group actions.
@addrole.command(name="add")
@commands.has_permissions(manage_roles=True)
async def role_add_sub(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("role", "that role is too high for the bot."))
    await member.add_roles(role, reason=f"role added by {ctx.author}"); await ctx.send(embed=action_embed(f"Added {role.mention} to {member.mention}", added=True))

@addrole.command(name="remove")
@commands.has_permissions(manage_roles=True)
async def role_remove_sub(ctx, member: discord.Member, role: discord.Role):
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("role", "that role is too high for the bot."))
    await member.remove_roles(role, reason=f"role removed by {ctx.author}"); await ctx.send(embed=action_embed(f"Removed {role.mention} from {member.mention}", removed=True))

@addrole.command(name="delete")
@commands.has_permissions(manage_roles=True)
async def role_delete_sub(ctx, role: discord.Role):
    await deleterole(ctx, role)

@addrole.command(name="edit")
@commands.has_permissions(manage_roles=True)
async def role_edit_sub(ctx, role: discord.Role, *, name: str):
    await role.edit(name=name[:100], reason=f"role renamed by {ctx.author}"); await ctx.send(embed=make_embed("role edit", f"renamed role to {role.mention}."))

@addrole.command(name="mentionable")
@commands.has_permissions(manage_roles=True)
async def role_mentionable_sub(ctx, role: discord.Role):
    await rolementionable(ctx, role)

@addrole.command(name="hoist")
@commands.has_permissions(manage_roles=True)
async def role_hoist_sub(ctx, role: discord.Role):
    await rolehoist(ctx, role)

@addrole.group(name="color", aliases=["colour"], invoke_without_command=True)
@commands.has_permissions(manage_roles=True)
async def role_color_sub(ctx, colour: str = None, role: discord.Role = None, second_colour: str = None):
    if role is None or colour is None: return await ctx.send(embed=make_embed("role color", f"usage: `{PREFIX}role color <hex> <role>` or `{PREFIX}role color gradient <hex1> <hex2> <role>`."))
    raw=colour.lstrip("#")
    try: val=int(raw,16)
    except ValueError: return await ctx.send(embed=make_embed("role color", "use a hex color like `#efcead`."))
    if len(raw)!=6: return await ctx.send(embed=make_embed("role color", "use a six-digit hex color."))
    await role.edit(colour=discord.Colour(val), reason=f"role color set by {ctx.author}")
    extra=f" Gradient second color `{second_colour}` was noted, but Discord.py/your server may not support native gradient role colors." if second_colour else ""
    await ctx.send(embed=make_embed("role color", f"updated {role.mention} to `#{raw.lower()}`.{extra}"))

@addrole.command(name="create")
@commands.has_permissions(manage_roles=True)
async def role_create_sub(ctx, *, name: str):
    role=await ctx.guild.create_role(name=name[:100], reason=f"role created by {ctx.author}"); await ctx.send(embed=make_embed("role created", f"created {role.mention}."))

@addrole.command(name="icon")
@commands.has_permissions(manage_roles=True)
async def role_icon_sub(ctx, url: str, role: discord.Role):
    await roleicon(ctx, role, url)

@addrole.group(name="humans", invoke_without_command=True)
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_humans_group(ctx, role: discord.Role):
    await rolehumans(ctx, role)

@role_humans_group.command(name="remove")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_humans_remove_sub(ctx, role: discord.Role):
    await rolehumansremove(ctx, role)

@addrole.group(name="bots", invoke_without_command=True)
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_bots_group(ctx, role: discord.Role):
    await rolebots(ctx, role)

@role_bots_group.command(name="remove")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_bots_remove_sub(ctx, role: discord.Role):
    await rolebotsremove(ctx, role)

@addrole.command(name="topcolor")
@commands.has_permissions(manage_roles=True)
async def role_topcolor(ctx, colour: str, member: discord.Member = None):
    member=member or ctx.author; role=next((r for r in reversed(member.roles) if r < ctx.guild.me.top_role and not r.is_default()),None)
    if not role: return await ctx.send(embed=make_embed("role topcolor", "no manageable role found for that member."))
    raw=colour.lstrip("#")
    try: value=int(raw,16)
    except ValueError: return await ctx.send(embed=make_embed("role topcolor", "use a hex color like `#efcead`."))
    await role.edit(colour=discord.Colour(value), reason=f"top role color changed by {ctx.author}"); await ctx.send(embed=make_embed("role topcolor", f"updated {role.mention}."))

@addrole.group(name="has", invoke_without_command=True)
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_has(ctx, source_role: discord.Role = None, assign_role: discord.Role = None):
    if source_role is None or assign_role is None: return await ctx.send(embed=make_embed("role has", f"usage: `{PREFIX}role has <source role> <role to add>` or `{PREFIX}role has remove <source role> <role to remove>`."))
    count=0
    for member in ctx.guild.members:
        if source_role in member.roles and assign_role not in member.roles:
            try: await member.add_roles(assign_role, reason=f"conditional role by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role has", f"added {assign_role.mention} to `{count}` members with {source_role.mention}."))

@addrole.command(name="restore")
@commands.has_permissions(manage_roles=True)
async def role_restore(ctx, member: discord.Member):
    d=_load_json_config("role_backup.json",{}).get(str(ctx.guild.id),{}).get(str(member.id),[]); restored=0
    for rid in d:
        role=ctx.guild.get_role(int(rid))
        if role and role < ctx.guild.me.top_role:
            try: await member.add_roles(role, reason=f"roles restored by {ctx.author}"); restored+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role restore", f"restored `{restored}` saved roles to {member.mention}."))

@bot.command(name="raid")
@commands.has_permissions(ban_members=True)
async def raid(ctx, duration: str, action: str = "kick", *, reason="raid response"):
    seconds=parse_duration(duration)
    if seconds is None: return await ctx.send(embed=make_embed("raid", "duration example: `10m` or `1h`."))
    cutoff=discord.utils.utcnow()-timedelta(seconds=seconds); affected=0
    for member in list(ctx.guild.members):
        if member.bot or member.joined_at is None or member.joined_at < cutoff or member == ctx.author or member.guild_permissions.administrator: continue
        try:
            if action.lower()=="ban": await member.ban(reason=f"raid by {ctx.author}: {reason}", delete_message_seconds=0)
            elif action.lower()=="kick": await member.kick(reason=f"raid by {ctx.author}: {reason}")
            else: return await ctx.send(embed=make_embed("raid", "action must be `kick` or `ban`."))
            affected+=1
        except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("raid", f"processed `{affected}` recent members with action `{action}`. Use carefully; review your member list and permissions."))


@role_color_sub.command(name="gradient")
@commands.has_permissions(manage_roles=True)
async def role_color_gradient(ctx, first_colour: str, second_colour: str, role: discord.Role):
    def parse_hex(raw):
        raw=raw.lstrip("#")
        if len(raw)!=6: raise ValueError
        return int(raw,16), raw.lower()
    try: first, first_text=parse_hex(first_colour); second, second_text=parse_hex(second_colour)
    except ValueError: return await ctx.send(embed=make_embed("role color gradient", "use two six-digit hex colors, e.g. `#ff99cc #cc99ff`."))
    # Discord's public role API currently exposes one solid role color in discord.py.
    # Save the requested pair for reference and apply the first color as a graceful fallback.
    data=_load_json_config("role_gradients.json",{}); data.setdefault(str(ctx.guild.id),{})[str(role.id)]={"first":f"#{first_text}","second":f"#{second_text}","set_by":ctx.author.id}; _save_json_file("role_gradients.json",data)
    await role.edit(colour=discord.Colour(first), reason=f"gradient requested by {ctx.author}")
    await ctx.send(embed=make_embed("role gradient saved", f"saved gradient colors `#{first_text}` → `#{second_text}` for {role.mention}. Discord.py's role API only applies a solid color here, so `#{first_text}` is the visible fallback."))

@role_has.command(name="remove")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_has_remove(ctx, source_role: discord.Role, remove_role: discord.Role):
    count=0
    for member in ctx.guild.members:
        if source_role in member.roles and remove_role in member.roles:
            try: await member.remove_roles(remove_role, reason=f"conditional role removal by {ctx.author}"); count+=1
            except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("role has remove", f"removed {remove_role.mention} from `{count}` members with {source_role.mention}."))

@addrole.command(name="cancel")
@commands.has_guild_permissions(manage_roles=True, manage_guild=True)
async def role_cancel(ctx):
    data=_load_json_config("role_mass_tasks.json",{}); task=data.get(str(ctx.guild.id))
    if not task: return await ctx.send(embed=make_embed("role task", "there is no saved mass-role task to cancel."))
    task["cancel"]=True; data[str(ctx.guild.id)]=task; _save_json_file("role_mass_tasks.json",data)
    await ctx.send(embed=make_embed("role task", "cancellation requested for the saved mass-role task."))

@nuke.command(name="list")
@commands.has_permissions(administrator=True)
async def nuke_list(ctx):
    d=_load_json_config("scheduled_nukes.json",{}).get(str(ctx.guild.id),{}); body="\n".join(f"<#{cid}> · every `{v.get('interval','?')}` · {v.get('message','')}" for cid,v in d.items()) or "No scheduled nukes configured."
    await ctx.send(embed=make_embed("scheduled nukes", body[:4000]))

@nuke.command(name="view")
@commands.has_permissions(administrator=True)
async def nuke_view(ctx, channel: discord.TextChannel):
    d=_load_json_config("scheduled_nukes.json",{}).get(str(ctx.guild.id),{}).get(str(channel.id))
    await ctx.send(embed=make_embed("scheduled nuke", f"**Channel:** {channel.mention}\n**Settings:** `{d}`" if d else f"No scheduled nuke for {channel.mention}."))

@nuke.command(name="remove")
@commands.has_permissions(administrator=True)
async def nuke_remove(ctx, channel: discord.TextChannel):
    data=_load_json_config("scheduled_nukes.json",{}); g=data.setdefault(str(ctx.guild.id),{}); removed=g.pop(str(channel.id),None); _save_json_file("scheduled_nukes.json",data)
    await ctx.send(embed=make_embed("scheduled nuke", f"removed schedule for {channel.mention}." if removed else "no schedule was found for that channel."))

@nuke.command(name="archive")
@commands.has_permissions(administrator=True)
async def nuke_archive(ctx, channel: discord.TextChannel, setting: str):
    if setting.lower() not in ("on","off","true","false"): return await ctx.send(embed=make_embed("nuke archive", "setting must be `on` or `off`."))
    data=_load_json_config("scheduled_nukes.json",{}); g=data.setdefault(str(ctx.guild.id),{}); cfg=g.setdefault(str(channel.id),{"interval":"unset","message":"scheduled channel refresh"}); cfg["archive_pins"]=setting.lower() in ("on","true"); _save_json_file("scheduled_nukes.json",data)
    await ctx.send(embed=make_embed("nuke archive", f"pin archiving {'enabled' if cfg['archive_pins'] else 'disabled'} for {channel.mention}."))

@nuke.command(name="add")
@commands.has_permissions(administrator=True)
async def nuke_add(ctx, channel: discord.TextChannel, interval: str, *, message: str = "scheduled channel refresh"):
    seconds=parse_duration(interval)
    if seconds is None or seconds < 3600: return await ctx.send(embed=make_embed("nuke schedule", "use an interval of at least `1h`, e.g. `nuke add #general 1d refresh`."))
    data=_load_json_config("scheduled_nukes.json",{}); g=data.setdefault(str(ctx.guild.id),{}); g[str(channel.id)]={"interval":interval,"seconds":seconds,"message":message[:300],"archive_pins":False,"created_by":ctx.author.id,"next_run":int(time.time()+seconds)}; _save_json_file("scheduled_nukes.json",data)
    await ctx.send(embed=make_embed("nuke schedule saved", f"saved a schedule for {channel.mention} every `{interval}`. the bot will attempt the channel refresh while online."))

# Apply sticky roles and saved forced nicknames on joins, and keep role backups.
_reminder_worker_started = False

@bot.listen("on_ready")
async def start_reminder_worker():
    global _reminder_worker_started
    if _reminder_worker_started: return
    _reminder_worker_started = True
    async def worker():
        while not bot.is_closed():
            await asyncio.sleep(20)
            data=_load_json_config("reminders.json",{}); changed=False
            for uid, items in list(data.items()):
                user=bot.get_user(int(uid))
                if user is None:
                    try: user=await bot.fetch_user(int(uid))
                    except (discord.NotFound, discord.HTTPException): user=None
                remaining=[]
                for item in items:
                    if int(item.get("due",0)) > int(time.time()):
                        remaining.append(item); continue
                    if user:
                        try: await user.send(embed=make_embed("reminder", str(item.get("message","Reminder"))))
                        except discord.HTTPException: pass
                    changed=True
                data[uid]=remaining
            if changed: _save_json_file("reminders.json",data)
    asyncio.create_task(worker())

_scheduled_nuke_worker_started = False

@bot.listen("on_ready")
async def start_scheduled_nuke_worker():
    global _scheduled_nuke_worker_started
    if _scheduled_nuke_worker_started: return
    _scheduled_nuke_worker_started = True
    async def worker():
        while not bot.is_closed():
            await asyncio.sleep(30)
            data=_load_json_config("scheduled_nukes.json",{}); changed=False
            for gid, channels in list(data.items()):
                guild=bot.get_guild(int(gid))
                if guild is None: continue
                for cid, cfg in list(channels.items()):
                    try: due=int(cfg.get("next_run",0)); interval=int(cfg.get("seconds",0))
                    except (TypeError,ValueError): continue
                    if interval < 3600 or due > int(time.time()): continue
                    channel=guild.get_channel(int(cid))
                    if channel is None:
                        channels.pop(cid,None); changed=True; continue
                    try:
                        archive=None
                        if cfg.get("archive_pins") and isinstance(channel, discord.TextChannel):
                            pins=await channel.pins()
                            if pins:
                                lines=[f"{m.created_at.isoformat()} | {m.author} ({m.author.id}): {m.content}" for m in pins]
                                archive=discord.File(io.BytesIO("\n\n".join(lines).encode("utf-8")), filename=f"pins-{channel.id}.txt")
                        clone=await channel.clone(reason="scheduled channel refresh")
                        await clone.edit(position=channel.position)
                        if archive:
                            try: await clone.send(content="Pinned-message archive before scheduled refresh:", file=archive)
                            except discord.HTTPException: pass
                        try: await clone.send(embed=make_embed("scheduled refresh", str(cfg.get("message","scheduled channel refresh"))))
                        except discord.HTTPException: pass
                        await channel.delete(reason="scheduled channel refresh")
                        # A cloned channel gets a new ID, so move its schedule to that ID.
                        channels.pop(cid,None); cfg["next_run"]=int(time.time())+interval; channels[str(clone.id)]=cfg; changed=True
                    except (discord.Forbidden, discord.HTTPException):
                        cfg["next_run"]=int(time.time())+min(interval,3600); changed=True
            if changed: _save_json_file("scheduled_nukes.json",data)
    asyncio.create_task(worker())

@bot.listen("on_member_remove")
async def save_member_roles_before_leave(member):
    if member.bot: return
    data=_load_json_config("role_backup.json",{}); data.setdefault(str(member.guild.id),{})[str(member.id)]=[r.id for r in member.roles if not r.is_default() and not r.managed]; _save_json_file("role_backup.json",data)

@bot.listen("on_member_join")
async def reapply_saved_member_settings(member):
    sticky=_load_json_config("stickyrole.json",{}).get(str(member.guild.id),{}).get(str(member.id),[])
    for rid in sticky:
        role=member.guild.get_role(int(rid))
        if role and role < member.guild.me.top_role:
            try: await member.add_roles(role, reason="sticky role re-applied")
            except (discord.Forbidden, discord.HTTPException): pass
    forced=_load_json_config("forced_nicknames.json",{}).get(str(member.guild.id),{}).get(str(member.id))
    if forced:
        try: await member.edit(nick=forced, reason="forced nickname re-applied")
        except (discord.Forbidden, discord.HTTPException): pass

@bot.listen("on_member_update")
async def enforce_saved_nickname(before, after):
    forced=_load_json_config("forced_nicknames.json",{}).get(str(after.guild.id),{}).get(str(after.id))
    if forced and after.nick != forced:
        try: await after.edit(nick=forced, reason="forced nickname enforcement")
        except (discord.Forbidden, discord.HTTPException): pass

# Add all new command names to the command browser/help directory.
CATEGORIES.extend([
    ("Moderation Tools", ["tempban", "softban", "timeoutlist", "untimeout", "imute", "iunmute", "rmute", "runmute", "modstats", "moderationhistory", "jaillist", "caselog", "proof", "history", "unbanall", "raid"]),
    ("Role Management", ["temprole", "stickyrole", "role add", "role remove", "role delete", "role edit", "role icon", "role color", "role humans", "role bots", "role has", "role restore", "role topcolor", "role mentionable", "role hoist", "role create", "rolehumansremove", "rolebotsremove", "dump"]),
    ("Channel Management", ["lockdown all", "lockdown role", "lockdown ignore", "unlock all", "unlockall", "purge links", "purge webhooks", "purge humans", "purge bots", "purge embeds", "purge files", "purge images", "purge stickers", "purge reactions", "purge mentions", "purge contains", "purge startswith", "purge endswith", "purge emoji", "purge emotes", "purge activity", "purge before", "purge after", "purge upto", "purge between", "slowmode on", "slowmode off", "revokefiles", "topic", "talk", "naughty"]),
    ("Utilities", ["reminders", "restrictcommand", "forcenickname", "setupmute", "permissions", "rename"]),
])
COMMAND_INFO.update({
    "reminders": ("View your active reminders.", "reminders", "reminders", []),
    "proof": ("Manage proof and attachments on a moderation case.", "proof <set|add|list|view|remove> ...", "proof list 12", []),
    "history": ("View and manage stored moderation history.", "history <member|view|remove|removeall> ...", "history @member", ["cases"]),
    "modstats": ("View punishment statistics for a moderator.", "modstats [member]", "modstats @moderator", []),
    "moderationhistory": ("View actions taken by a staff member.", "moderationhistory <member> [command]", "moderationhistory @moderator ban", []),
    "jaillist": ("List saved jailed members.", "jaillist", "jaillist", []),
    "temprole": ("Give a role temporarily, with an automatic removal timer.", "temprole <member> <duration> <role>", "temprole @user 2h @Member", []),
    "stickyrole": ("Save roles to reapply after a member rejoins.", "stickyrole <add|remove|list> ...", "stickyrole add @user @role", []),
    "restrictcommand": ("Manage role-based command restrictions.", "restrictcommand <add|remove|list|reset> ...", "restrictcommand add ban @Staff", ["restrictcmd"]),
    "unbanall": ("Unban all users, with a cancellation subcommand.", "unbanall [cancel]", "unbanall", []),
    "raid": ("Moderate recently joined members in a raid window.", "raid <duration> <kick|ban> [reason]", "raid 10m kick raid response", []),
    "imute": ("Disable attachments and embeds for a member in this channel.", "imute <member> [reason]", "imute @user spam", []),
    "iunmute": ("Restore attachments and embeds for a member in this channel.", "iunmute <member> [reason]", "iunmute @user", []),
    "rmute": ("Disable reactions and external emojis for a member in this channel.", "rmute <member> [reason]", "rmute @user spam", []),
    "runmute": ("Restore reactions and external emojis for a member in this channel.", "runmute <member> [reason]", "runmute @user", []),
    "caselog": ("View a case log by ID.", "caselog <case id>", "caselog 12", []),
    "dump": ("Export all members with a specified role to a text file.", "dump <role>", "dump @Members", []),
    "rolehumansremove": ("Remove a role from all human members.", "rolehumansremove <role>", "rolehumansremove @Member", []),
    "rolebotsremove": ("Remove a role from all bot members.", "rolebotsremove <role>", "rolebotsremove @Bots", []),
    "setupmute": ("Create/configure a Muted role and channel overwrites.", "setupmute", "setupmute", []),
    "permissions": ("Display a member's effective channel permissions.", "permissions [member] [channel]", "permissions @user #general", []),
    "rename": ("Change a member's nickname.", "rename <member> <nickname>", "rename @user New Name", []),
    "forcenickname": ("Save and apply a forced nickname.", "forcenickname <member> <nickname>", "forcenickname @user Fixed Name", []),
    "topic": ("Set the current channel topic.", "topic <text>", "topic welcome to the server", []),
    "talk": ("Allow a role to talk in a channel.", "talk <channel> <role>", "talk #general @Members", []),
    "revokefiles": ("Toggle attachment/embed permissions in a channel.", "revokefiles <on|off> [channel]", "revokefiles on #general", []),
    "naughty": ("Temporarily mark a channel as NSFW for 30 seconds.", "naughty [channel]", "naughty #general", []),
    "roleicon": ("Set a role icon from an image URL.", "roleicon <role> <url>", "roleicon @VIP https://example.com/icon.png", []),
    "rolementionable": ("Toggle whether a role can be mentioned.", "rolementionable <role>", "rolementionable @Members", []),
    "rolehoist": ("Toggle whether a role is shown separately in the member list.", "rolehoist <role>", "rolehoist @Staff", []),
    "rolecolor": ("Set a role color using a hex code.", "rolecolor <role> <hex>", "rolecolor @VIP #efcead", ["rolecolour"]),
    "rolecreate": ("Create a role.", "rolecreate <name>", "rolecreate VIP", []),
    "roleedit": ("Rename a role.", "roleedit <role> <name>", "roleedit @VIP Premium", []),
})


@ban.command(name="recent")
@commands.has_permissions(ban_members=True)
async def ban_recent(ctx, count: int = 5, *, reason="recent join moderation"):
    count=max(1,min(count,25)); cutoff=discord.utils.utcnow()-timedelta(days=7)
    members=[m for m in ctx.guild.members if not m.bot and m.joined_at and m.joined_at>=cutoff and m!=ctx.author and not m.guild_permissions.administrator and m.top_role < ctx.guild.me.top_role]
    members.sort(key=lambda m:m.joined_at or discord.utils.utcnow(), reverse=True); done=0
    for member in members[:count]:
        try: await member.ban(reason=f"ban recent by {ctx.author}: {reason}", delete_message_seconds=0); done+=1
        except (discord.Forbidden, discord.HTTPException): pass
    await ctx.send(embed=make_embed("ban recent", f"banned `{done}` recent members. Review the count carefully before using this bulk action."))

@ban.command(name="purge")
@commands.has_permissions(manage_guild=True, ban_members=True)
async def ban_purge_sub(ctx, seconds: int = 604800):
    seconds=max(0,min(seconds,604800)); cfg=guild_cfg(ctx.guild.id); cfg["ban_delete_seconds"]=seconds; save_ultimate_config()
    await ctx.send(embed=make_embed("ban purge setting", f"normal bans will delete up to `{seconds}` seconds of message history."))

CATEGORIES.extend([
    ("Moderation Subcommands", ["remind list", "remind remove", "thread watch list", "lockdown all", "lockdown role", "lockdown ignore", "lockdown ignore add", "lockdown ignore remove", "lockdown ignore list", "history view", "history remove", "history removeall", "proof set", "proof add", "proof list", "proof view", "proof remove", "ban recent", "ban purge", "unbanall cancel", "hardban list", "timeout list", "temprole list"]),
    ("Role Subcommands", ["role add", "role remove", "role delete", "role icon", "role humans", "role humans remove", "role mentionable", "role cancel", "role edit", "role topcolor", "role restore", "role hoist", "role bots", "role bots remove", "role color", "role color gradient", "role create", "role has", "role has remove"]),
    ("Purge Subcommands", ["purge after", "purge webhooks", "purge between", "purge links", "purge humans", "purge endswith", "purge reactions", "purge stickers", "purge mentions", "purge activity", "purge emoji", "purge startswith", "purge emotes", "purge upto", "purge embeds", "purge files", "purge images", "purge contains", "purge before", "purge bots"]),
    ("Nuke Subcommands", ["nuke add", "nuke remove", "nuke list", "nuke archive", "nuke view"]),
])
COMMAND_INFO.update({
    "ban recent": ("Ban a limited number of members who joined within the last seven days.", "ban recent [count] [reason]", "ban recent 5 suspected raid", []),
    "ban purge": ("Set how much message history normal bans delete.", "ban purge [seconds]", "ban purge 86400", []),
    "role color gradient": ("Save two requested gradient colors; Discord.py applies a solid-color fallback because native gradient roles are not exposed here.", "role color gradient <hex1> <hex2> <role>", "role color gradient #ff99cc #cc99ff @VIP", []),
    "role has remove": ("Remove a role from members who have another specified role.", "role has remove <source role> <role to remove>", "role has remove @VIP @Member", []),
    "nuke add": ("Save a scheduled channel refresh configuration.", "nuke add <channel> <interval> [message]", "nuke add #general 1d daily refresh", []),
    "nuke remove": ("Remove a saved scheduled channel refresh configuration.", "nuke remove <channel>", "nuke remove #general", []),
    "nuke list": ("List saved scheduled channel refresh configurations.", "nuke list", "nuke list", []),
    "nuke archive": ("Set whether pin archiving is enabled for a scheduled refresh.", "nuke archive <channel> <on|off>", "nuke archive #general on", []),
    "nuke view": ("View a channel's saved scheduled refresh configuration.", "nuke view <channel>", "nuke view #general", []),
    "role cancel": ("Request cancellation of a saved mass-role task.", "role cancel", "role cancel", []),
    "thread watch list": ("List threads in the watch list.", "thread watch list", "thread watch list", []),
    "lockdown ignore add": ("Add a channel to the lockdown ignore list.", "lockdown ignore add <channel>", "lockdown ignore add #staff", []),
    "lockdown ignore remove": ("Remove a channel from the lockdown ignore list.", "lockdown ignore remove <channel>", "lockdown ignore remove #staff", []),
    "lockdown ignore list": ("List channels excluded from unlock-all.", "lockdown ignore list", "lockdown ignore list", []),
    "history view": ("View a moderation case by ID.", "history view <case id>", "history view 123-1", []),
    "history remove": ("Remove a case entry for a member.", "history remove <member> <case id>", "history remove @user 1", []),
    "history removeall": ("Clear all stored punishment history for a member.", "history removeall <member>", "history removeall @user", []),
    "proof set": ("Set the explanation attached to a case.", "proof set <case id> <explanation>", "proof set 123-1 repeated spam", []),
    "proof add": ("Add a media URL to a case.", "proof add <case id> <url>", "proof add 123-1 https://example.com/evidence.png", []),
    "proof list": ("List proof and attachments on a case.", "proof list <case id>", "proof list 123-1", []),
    "proof view": ("View proof attached to a case.", "proof view <case id>", "proof view 123-1", []),
    "proof remove": ("Remove an attachment from a case.", "proof remove <case id> <index>", "proof remove 123-1 1", []),
    "remind list": ("List your reminders.", "remind list", "remind list", []),
    "remind remove": ("Remove a reminder by ID.", "remind remove <id>", "remind remove 2", []),
    "unbanall cancel": ("Request cancellation of an unban-all operation.", "unbanall cancel", "unbanall cancel", []),
    "hardban list": ("List hardbanned users.", "hardban list", "hardban list", []),
    "timeout list": ("List members currently timed out.", "timeout list", "timeout list", []),
    "temprole list": ("List saved temporary roles.", "temprole list", "temprole list", []),
})
# Ensure every entry in the command browser has a help description, even when its parent
# command is implemented as a group/subcommand.
for _category_name, _category_commands in CATEGORIES:
    for _command_name in _category_commands:
        if _command_name not in COMMAND_INFO:
            _pretty = _command_name.replace("_", " ").strip()
            COMMAND_INFO[_command_name] = (f"Manage { _pretty }.", f"{_command_name} [arguments]", _command_name, [])


CATEGORIES.extend([
    ("Remaining Supplied Commands", ["modstats", "moderationhistory", "history", "history view", "history removeall", "history remove", "jaillist", "proof", "caselog", "reason", "timeout list", "untimeout", "mute", "unmute", "imute", "iunmute", "rmute", "runmute", "notes", "notes add", "notes clear", "notes remove", "hardban", "hardban list", "clearinvites", "drag", "unbanall", "unbanall cancel", "softban", "ban purge", "ban recent", "unjail", "temprole", "temprole list", "role", "role delete", "role icon", "role remove", "role humans", "role humans remove", "role add", "role mentionable", "role cancel", "role edit", "role topcolor", "role restore", "role hoist", "role bots", "role bots remove", "role color", "role color gradient", "role create", "role has", "role has remove"]),
    ("More Purge Commands", ["purge", "purge after", "purge webhooks", "purge between", "purge links", "purge humans", "purge endswith", "purge reactions", "purge stickers", "purge mentions", "purge activity", "purge emoji", "purge startswith", "purge emotes", "purge upto", "purge embeds", "purge files", "purge images", "purge contains", "purge before", "purge bots", "dump"]),
    ("More Server Commands", ["nuke", "nuke remove", "nuke list", "nuke archive", "nuke add", "nuke view", "newmembers", "recentban", "talk", "unhide", "hide", "slowmode", "slowmode on", "slowmode off", "revokefiles", "revokefiles on", "revokefiles off", "setup", "rename", "restrictcommand", "restrictcommand reset", "restrictcommand list", "restrictcommand remove", "restrictcommand add", "stickyrole", "stickyrole remove", "stickyrole add", "stickyrole list", "raid", "forcenickname", "forcenickname list", "topic", "naughty", "setupmute", "permissions"]),
])
for _category_name, _category_commands in CATEGORIES:
    for _command_name in _category_commands:
        if _command_name not in COMMAND_INFO:
            _pretty = _command_name.replace("_", " ").strip()
            COMMAND_INFO[_command_name] = (f"Manage {_pretty}.", f"{_command_name} [arguments]", _command_name, [])


CATEGORIES.extend([
    ("Case and Note Tools", ["reason", "notes", "notes add", "notes clear", "notes remove", "notes list", "setup"]),
])
COMMAND_INFO.update({
    "reason": ("Update the reason attached to a moderation case.", "reason <case id> <reason>", "reason 123-1 updated context", []),
    "setup": ("Create a mod-log channel and configure a Muted role.", "setup", "setup", []),
    "notes add": ("Add a note to a member.", "notes add <member> <note>", "notes add @user repeated spam", []),
    "notes clear": ("Clear all notes for a member.", "notes clear <member>", "notes clear @user", []),
    "notes remove": ("Remove a note by its list index.", "notes remove <member> <id>", "notes remove @user 2", []),
    "notes list": ("List notes stored for a member.", "notes list <member>", "notes list @user", []),
    "timeout list": ("List members currently timed out.", "timeout list", "timeout list", []),
    "hardban list": ("List hardbanned users.", "hardban list", "hardban list", []),
})
for _category_name, _category_commands in CATEGORIES:
    for _command_name in _category_commands:
        if _command_name not in COMMAND_INFO:
            _pretty = _command_name.replace("_", " ").strip()
            COMMAND_INFO[_command_name] = (f"Manage {_pretty}.", f"{_command_name} [arguments]", _command_name, [])

bot.run(TOKEN)
