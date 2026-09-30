import os, time, random, asyncio
from collections import defaultdict, deque
from datetime import timedelta
import discord
from discord.ext import commands

PREFIX = ","
COLOR = 0x000001
TOKEN = os.getenv("DISCORD_TOKEN")

BAN_ROLE = 1541538650355929168
MUTE_ROLES = {1541538650355929168, 1540101656824258771, 1535418806984384563, 1535419879493210254}
WARN_ROLES = MUTE_ROLES
KICK_ROLES = {1541538650355929168, 1535419879493210254}
PURGE_ROLES = {1541538650355929168, 1535419879493210254}

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
start_time = time.time()
warnings = defaultdict(lambda: defaultdict(list))
afk_data = {}
welcome_channels = {}
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


def role_ok(member, role_ids):
    return any(r.id in role_ids for r in member.roles)


def target_ok(ctx, member):
    return member != ctx.author and member != ctx.guild.owner and member.top_role < ctx.author.top_role


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
    "welcome": ("Configure welcome messages.", "welcome [channel]", "welcome #welcome", []),
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
    "create": ("Create a server role, text channel, or voice channel.", "create <role|channel|vc> <name>", "create role VIP", []),
    "create role": ("Create a new server role.", "create role <name>", "create role VIP", []),
    "create channel": ("Create a new text channel.", "create channel <name>", "create channel general", []),
    "create vc": ("Create a new voice channel.", "create vc <name>", "create vc Gaming", ["create voice"]),
    "remind": ("Create a personal reminder.", "remind <duration> <message>", "remind 30m check chat", []),
}

CATEGORIES = [
    ("Information", ["afk", "avatar", "banner", "botinfo", "channelinfo", "commands", "emojis", "guildicon", "help", "membercount", "permissions", "roleinfo", "roles", "serverinfo", "stickers", "userinfo"]),
    ("Server", ["ar", "autorole", "autoreact", "booster", "boosterremove", "boost", "filter", "welcome", "disablewelcome", "poll", "ticket", "close", "giveaway", "gaw", "announce", "create", "remind"]),
    ("Security", ["antinuke", "antiraid", "security"]),
    ("Moderation", ["ban", "unban", "kick", "mute", "unmute", "warn", "warnings", "purge", "lock", "unlock", "snipe", "slowmode", "nick", "addrole", "removerole"]),
    ("Fun", ["8ball", "coinflip", "roll", "choose", "rps", "joke", "fact", "rate", "wyr", "mock", "reverse", "truth", "dare", "wouldyou"]),
    ("Social", ["hug", "pat", "slap", "love", "simp", "gayrate", "howlucky", "ship", "shipname", "roast", "compliment"]),
]


def command_text(name):
    return f"`{name}`"


def build_pages():
    page_groups = [["Information", "Server"], ["Security", "Moderation"], ["Fun", "Social"]]
    lookup = dict(CATEGORIES)
    pages = []
    for group in page_groups:
        blocks = []
        for title in group:
            blocks.append(f"# {title}\n" + " ".join(command_text(name) for name in lookup[title]))
        pages.append("\n\n".join(blocks))
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
    channel_id = welcome_channels.get(member.guild.id)
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            e = make_embed("welcome", f"welcome {member.mention} to **{member.guild.name}**!\n\nmember **#{member.guild.member_count}**")
            e.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=e)


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


@bot.event
async def on_message_delete(message):
    if not message.author.bot:
        bot._last_deleted = (message.author, message.content, message.channel, time.time())


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
                try: await message.add_reaction(reaction)
                except discord.HTTPException: pass
        if content in autoresponders[message.guild.id]:
            await message.channel.send(autoresponders[message.guild.id][content])
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

@bot.command(aliases=["ui"])
async def userinfo(ctx, member: discord.Member=None):
    member = member or ctx.author
    roles = ", ".join(r.mention for r in member.roles[1:]) or "none"
    joined = f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "unknown"
    e = info_embed(ctx, "User Information", [
        ("User", f"{member.mention} · `{member.id}`", False),
        ("Created", f"<t:{int(member.created_at.timestamp())}:F>\n<t:{int(member.created_at.timestamp())}:R>", True),
        ("Joined", f"{joined}", True),
        ("Roles", roles, False),
    ], thumbnail=False)
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)

@bot.command(aliases=["si"])
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

@bot.command()
async def channelinfo(ctx, channel: discord.TextChannel=None):
    c = channel or ctx.channel
    e = info_embed(ctx, "Channel Information", [
        ("Channel", f"{c.mention} · `{c.id}`", False),
        ("Type", f"`{c.type}`", True),
        ("Position", f"`{c.position}`", True),
        ("Created", f"<t:{int(c.created_at.timestamp())}:R>", False),
    ])
    await ctx.send(embed=e)

@bot.command()
async def roleinfo(ctx, role: discord.Role):
    e = info_embed(ctx, "Role Information", [
        ("Role", f"{role.mention} · `{role.id}`", False),
        ("Members", f"`{len(role.members)}`", True),
        ("Position", f"`{role.position}`", True),
        ("Color", f"`{role.color}`", True),
        ("Created", f"<t:{int(role.created_at.timestamp())}:R>", True),
    ])
    await ctx.send(embed=e)

@bot.command()
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

@bot.command()
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

@bot.command()
async def emojis(ctx): await ctx.send(embed=make_embed("emojis", " ".join(str(e) for e in ctx.guild.emojis) or "no custom emojis."))

@bot.command()
async def stickers(ctx): await ctx.send(embed=make_embed("stickers", " ".join(f"`{s.name}`" for s in ctx.guild.stickers) or "no stickers."))

@bot.command()
async def permissions(ctx, member: discord.Member=None):
    member=member or ctx.author; perms=[p.replace("_", " ") for p,v in member.guild_permissions if v]; await ctx.send(embed=make_embed("permissions", f"**{member.mention}**\n" + ", ".join(perms)))

@bot.command()
async def guildicon(ctx):
    e=make_embed("server icon"); e.set_image(url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty); await ctx.send(embed=e)

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
async def welcome(ctx, channel: discord.TextChannel=None):
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    channel=channel or ctx.channel; welcome_channels[ctx.guild.id]=channel.id; await ctx.send(embed=make_embed("welcome enabled", f"welcome messages will be sent in {channel.mention}."))

@bot.command()
async def disablewelcome(ctx):
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    welcome_channels.pop(ctx.guild.id,None); await ctx.send(embed=make_embed("welcome disabled", "welcome messages are now disabled."))

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
    if action=="remove": d.pop(data.lower().strip(),None); return await ctx.send(embed=make_embed("autoresponder removed", f"removed `{data}`."))
    if action=="clear": d.clear(); return await ctx.send(embed=make_embed("autoresponders cleared", "all autoresponders were removed."))
    text="\n".join(f"`{k}` → {v}" for k,v in d.items()) or "no autoresponders are configured."; await ctx.send(embed=make_embed("autoresponders", text))

@bot.command()
async def autorole(ctx, role: discord.Role=None):
    if role is None:
        rid=autoroles.get(ctx.guild.id); return await ctx.send(embed=make_embed("autorole", f"{ctx.guild.get_role(rid).mention if rid and ctx.guild.get_role(rid) else 'not configured'}"))
    if not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    if role >= ctx.guild.me.top_role: return await ctx.send(embed=make_embed("error", "my role must be above that role."))
    autoroles[ctx.guild.id]=role.id; await ctx.send(embed=make_embed("autorole set", f"new members will receive {role.mention}."))

@bot.command()
async def autoreact(ctx, action="list", *, data=""):
    if action in {"add","remove","clear"} and not has_manage(ctx): return await ctx.send(embed=make_embed("no permission", "you need Manage Server."))
    d=autoreacts[ctx.guild.id]
    if action=="add":
        if "|" not in data: return await ctx.send(embed=make_embed("autoreact", f"usage: `{PREFIX}autoreact add trigger | emoji`"))
        t,e=[x.strip() for x in data.split("|",1)]; d.setdefault(t.lower(),[]).append(e); return await ctx.send(embed=make_embed("autoreact added", f"`{t}` → {e}"))
    if action=="remove": d.pop(data.lower().strip(),None); return await ctx.send(embed=make_embed("autoreact removed", f"removed `{data}`."))
    if action=="clear": d.clear(); return await ctx.send(embed=make_embed("autoreacts cleared", "all automatic reactions were removed."))
    await ctx.send(embed=make_embed("autoreacts", "\n".join(f"`{k}` → {' '.join(v)}" for k,v in d.items()) or "none configured."))

@bot.command(aliases=["b"])
async def ban(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author,{BAN_ROLE}): return await ctx.send(embed=make_embed("no permission", "you don't have the required ban role."))
    if not target_ok(ctx,member): return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    await member.ban(reason=reason); await ctx.send(embed=make_embed("member banned", f"**{member}** was banned.\nreason: {reason}"))

@bot.command(aliases=["ub"])
async def unban(ctx,user_id:int):
    if not role_ok(ctx.author,{BAN_ROLE}): return await ctx.send(embed=make_embed("no permission", "you don't have the required ban role."))
    try: await ctx.guild.unban(discord.Object(id=user_id)); await ctx.send(embed=make_embed("member unbanned", f"`{user_id}` was unbanned."))
    except discord.NotFound: await ctx.send(embed=make_embed("error", "that user isn't banned or the ID is invalid."))

@bot.command(aliases=["k"])
async def kick(ctx,member:discord.Member,*,reason="no reason provided"):
    if not role_ok(ctx.author,KICK_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required kick role."))
    if not target_ok(ctx,member): return await ctx.send(embed=make_embed("error", "you can't kick that member."))
    await member.kick(reason=reason); await ctx.send(embed=make_embed("member kicked", f"**{member}** was kicked.\nreason: {reason}"))

@bot.command(aliases=["timeout","to"])
async def mute(ctx,member:discord.Member,minutes:int=10,*,reason="no reason provided"):
    if not role_ok(ctx.author,MUTE_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required mute role."))
    if not target_ok(ctx,member): return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    await member.timeout(timedelta(minutes=minutes),reason=reason); await ctx.send(embed=make_embed("member muted", f"{member.mention} was muted for **{minutes}m**.\nreason: {reason}"))

@bot.command(aliases=["um","untimeout"])
async def unmute(ctx,member:discord.Member):
    if not role_ok(ctx.author,MUTE_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required mute role."))
    if not target_ok(ctx,member): return await ctx.send(embed=make_embed("error", "you can't moderate that member."))
    await member.timeout(None,reason=f"unmuted by {ctx.author}"); await ctx.send(embed=make_embed("member unmuted", f"{member.mention} is no longer muted."))

@bot.command(aliases=["w"])
async def warn(ctx,member:discord.Member,*,reason="no reason provided"):
    if not role_ok(ctx.author,WARN_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required warn role."))
    if not target_ok(ctx,member): return await ctx.send(embed=make_embed("error", "you can't warn that member."))
    warnings[ctx.guild.id][member.id].append(reason); await ctx.send(embed=make_embed("member warned", f"{member.mention} received a warning.\nreason: {reason}"))

@bot.command()
async def warnings(ctx,member:discord.Member=None):
    member=member or ctx.author; items=warnings[ctx.guild.id][member.id]; await ctx.send(embed=make_embed(f"warnings • {member.display_name}", "\n".join(f"**{i}.** {r}" for i,r in enumerate(items,1)) or "no warnings."))

@bot.command(aliases=["p","clear"])
async def purge(ctx,amount:int=10):
    if not role_ok(ctx.author,PURGE_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required purge role."))
    deleted=await ctx.channel.purge(limit=max(1,min(amount,100))+1); msg=await ctx.send(embed=make_embed("purged",f"deleted **{max(0,len(deleted)-1)}** messages.")); await asyncio.sleep(3)
    try: await msg.delete()
    except discord.HTTPException: pass

@bot.command(aliases=["l"])
async def lock(ctx):
    if not role_ok(ctx.author,PURGE_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required moderation role."))
    await ctx.channel.set_permissions(ctx.guild.default_role,send_messages=False); await ctx.send(embed=make_embed("locked",f"{ctx.channel.mention} is now locked."))

@bot.command(aliases=["ul"])
async def unlock(ctx):
    if not role_ok(ctx.author,PURGE_ROLES): return await ctx.send(embed=make_embed("no permission", "you don't have the required moderation role."))
    await ctx.channel.set_permissions(ctx.guild.default_role,send_messages=None); await ctx.send(embed=make_embed("unlocked",f"{ctx.channel.mention} is now unlocked."))

@bot.command(aliases=["s"])
async def snipe(ctx):
    d=getattr(bot,"_last_deleted",None)
    if not d or d[2].id!=ctx.channel.id or time.time()-d[3]>60: return await ctx.send(embed=make_embed("snipe","nothing to snipe here."))
    await ctx.send(embed=make_embed("sniped message",f"**{d[0]}:** {d[1] or '[no text]'}"))

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

@bot.command(name="8ball", aliases=["8","ball"])
async def eightball(ctx,*,question): await ctx.send(embed=make_embed("8ball",random.choice(["yes.","no.","probably.","maybe.","ask again later.","definitely.","the stars say yes.","not looking good."])))

@bot.command()
async def coinflip(ctx): await ctx.send(embed=make_embed("coinflip",random.choice(["heads","tails"])))

@bot.command()
async def roll(ctx,sides:int=6): await ctx.send(embed=make_embed("roll",f"🎲 **{random.randint(1,max(2,min(sides,100000)))}**"))

@bot.command()
async def choose(ctx,*,choices):
    o=[x.strip() for x in choices.split("|") if x.strip()]; await ctx.send(embed=make_embed("choice",random.choice(o) if len(o)>=2 else "separate choices with `|`."))

@bot.command()
async def rps(ctx,choice):
    choice=choice.lower(); options=["rock","paper","scissors"]
    if choice not in options: return await ctx.send(embed=make_embed("rps","choose rock, paper, or scissors."))
    botc=random.choice(options); result="tie" if choice==botc else "you win" if (choice,botc) in [("rock","scissors"),("paper","rock"),("scissors","paper")] else "you lose"
    await ctx.send(embed=make_embed("rock paper scissors",f"you: **{choice}**\nbleeed: **{botc}**\n\n**{result}**"))

@bot.command()
async def joke(ctx): await ctx.send(embed=make_embed("joke",random.choice(["why did the computer get cold? it left its windows open.","I told my PC I needed a break. now it won't stop sending vacation ads.","what do you call a sleeping bull? a bulldozer.","why was the server cold? it left its cache open."])))

@bot.command()
async def fact(ctx): await ctx.send(embed=make_embed("fact",random.choice(["octopuses have three hearts.","bananas are botanically berries.","a day on Venus is longer than its year.","honey can stay edible for a very long time when stored properly."])))

@bot.command()
async def rate(ctx,*,thing): await ctx.send(embed=make_embed("rate",f"I'd rate **{thing}** a **{random.randint(0,100)}/100**."))

@bot.command()
async def roast(ctx,member:discord.Member=None):
    member=member or ctx.author; await ctx.send(embed=make_embed("roast",f"{member.mention}: you're running on the free trial of confidence."))

@bot.command()
async def compliment(ctx,member:discord.Member=None):
    member=member or ctx.author; await ctx.send(embed=make_embed("compliment",f"{member.mention} is genuinely a great person to have around."))

@bot.command()
async def wyr(ctx,*,question): await ctx.send(embed=make_embed("would you rather",question))

@bot.command()
async def mock(ctx,*,text): await ctx.send(embed=make_embed("mock","".join(c.upper() if i%2 else c.lower() for i,c in enumerate(text))))

@bot.command()
async def reverse(ctx,*,text): await ctx.send(embed=make_embed("reverse",text[::-1]))

@bot.command()
async def hug(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("hug",f"{ctx.author.mention} gave {member.mention} a hug ♡"))
@bot.command()
async def pat(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("pat",f"{ctx.author.mention} gave {member.mention} a pat ♡"))
@bot.command()
async def slap(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("slap",f"{ctx.author.mention} bonked {member.mention} (cartoon-style)."))
@bot.command()
async def love(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("love",f"{ctx.author.mention} sent some love to {member.mention} ♡"))
@bot.command()
async def simp(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("simp rate",f"{member.mention} is **{random.randint(0,100)}%** simp."))
@bot.command()
async def gayrate(ctx,member:discord.Member=None): member=member or ctx.author; await ctx.send(embed=make_embed("rate",f"{member.mention} got **{random.randint(0,100)}%**."))
@bot.command()
async def howlucky(ctx): await ctx.send(embed=make_embed("luck",f"your luck today is **{random.randint(0,100)}%**."))
@bot.command()
async def ship(ctx,a:discord.Member,b:discord.Member): await ctx.send(embed=make_embed("ship",f"{a.mention} × {b.mention} = **{random.randint(0,100)}%**"))
@bot.command()
async def shipname(ctx,a:discord.Member,b:discord.Member):
    n=(a.display_name[:max(1,len(a.display_name)//2)]+b.display_name[max(1,len(b.display_name)//2):]).replace(" ",""); await ctx.send(embed=make_embed("ship name",f"💗 **{n}**"))
@bot.command()
async def truth(ctx): await ctx.send(embed=make_embed("truth",random.choice(["what is a hobby you wish you were better at?","what is the funniest thing you've seen today?","what game could you play for hours?"])))
@bot.command()
async def dare(ctx): await ctx.send(embed=make_embed("dare",random.choice(["send a funny emoji in chat.","change your status for 5 minutes.","say something nice about the next person who messages you."])))
@bot.command()
async def wouldyou(ctx): await ctx.send(embed=make_embed("would you rather",random.choice(["would you rather always have perfect Wi-Fi or perfect battery life?","would you rather have unlimited games or unlimited snacks?","would you rather teleport or pause time?"])))

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


@bot.hybrid_group(name="create", invoke_without_command=True)
@commands.has_permissions(manage_channels=True)
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
    e.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)
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
async def on_command_error(ctx,error):
    if isinstance(error,commands.CommandNotFound): return
    if isinstance(error,commands.MissingRequiredArgument): return await ctx.send(embed=make_embed("missing argument",f"use `{PREFIX}help {ctx.command.qualified_name}` to see the correct usage."))
    if isinstance(error,commands.BadArgument): return await ctx.send(embed=make_embed("invalid argument",f"use `{PREFIX}help {ctx.command.qualified_name}` for usage."))
    if isinstance(error,commands.CommandInvokeError):
        print(f"Command error: {error.original}"); return await ctx.send(embed=make_embed("error","something went wrong while running that command."))
    print(f"Command error: {error}")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

bot.run(TOKEN)

client.run(os.getenv("DISCORD_TOKEN"))
