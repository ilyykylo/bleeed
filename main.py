import os
import time
import random
import asyncio
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
warnings = {}
afks = {}
welcome_channels = {}
boost_roles = {}
autoresponders = {}
autoroles = {}


def embed(title=None, description=None):
    return discord.Embed(title=title, description=description, color=COLOR)


def role_ok(member, role_ids):
    return any(role.id in role_ids for role in member.roles)


def target_ok(ctx, member):
    return member != ctx.author and member != ctx.guild.owner and member.top_role < ctx.author.top_role


def fmt_user(member):
    return f"{member.mention} (`{member.id}`)"


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help â¢ bleeed"))
    print(f"bleeed online as {bot.user} ({bot.user.id})")


@bot.event
async def on_member_join(member):
    channel_id = welcome_channels.get(member.guild.id)
    if channel_id:
        channel = member.guild.get_channel(channel_id)
        if channel:
            e = embed("welcome", f"welcome {member.mention} to **{member.guild.name}**!\n\nmember **#{member.guild.member_count}**")
            e.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=e)

    role_id = autoroles.get(member.guild.id)
    if role_id:
        role = member.guild.get_role(role_id)
        me = member.guild.me
        if role and me and role < me.top_role:
            try:
                await member.add_roles(role, reason="bleeed autorole")
            except discord.HTTPException:
                pass


@bot.event
async def on_member_update(before, after):
    if before.premium_since is None and after.premium_since is not None:
        role_id = boost_roles.get(after.guild.id)
        if role_id:
            role = after.guild.get_role(role_id)
            if role and role < after.guild.me.top_role:
                try:
                    await after.add_roles(role, reason="bleeed booster role")
                except discord.HTTPException:
                    pass
        channel = after.guild.system_channel
        if channel:
            await channel.send(embed=embed("boost", f"thank you {after.mention} for boosting **{after.guild.name}**! â¡"))


@bot.event
async def on_message_delete(message):
    if not message.author.bot:
        bot._last_deleted = (message.author, message.content, message.channel, time.time())


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    content = message.content.lower().strip()

    if message.author.id in afks and not content.startswith(PREFIX):
        afks.pop(message.author.id, None)
        await message.channel.send(embed=embed("afk removed", f"welcome back {message.author.mention}! your AFK has been removed."), delete_after=5)

    for uid, data in list(afks.items()):
        if uid != message.author.id and f"<@{uid}>" in message.content:
            await message.channel.send(embed=embed("afk", f"**{data['name']}** is AFK â {data['reason']}"), delete_after=8)

    # autoresponders only run on normal messages, never commands
    if message.guild and not content.startswith(PREFIX):
        guild_responders = autoresponders.get(message.guild.id, {})
        response = guild_responders.get(content)
        if response:
            await message.channel.send(response)

    await bot.process_commands(message)


@bot.command(aliases=["h"])
async def help(ctx, command_name: str = None):
    if command_name:
        command = bot.get_command(command_name.lower())
        if command is None:
            return await ctx.send(embed=embed("command not found", f"I couldn't find `,{command_name}`. Use `,commands` to see all commands."))

        info = {
            "help": ("Shows the bot help menu.", "help [command]", ",help 8ball"),
            "commands": ("Shows every available command.", "commands", ",commands"),
            "ping": ("Shows the bot's latency.", "ping", ",ping"),
            "uptime": ("Shows how long bleeed has been online.", "uptime", ",uptime"),
            "avatar": ("Shows a user's avatar.", "avatar [member]", ",avatar @user"),
            "userinfo": ("Shows information about a user.", "userinfo [member]", ",userinfo @user"),
            "serverinfo": ("Shows information about the server.", "serverinfo", ",serverinfo"),
            "botinfo": ("Shows information about bleeed.", "botinfo", ",botinfo"),
            "banner": ("Shows a user's banner.", "banner [member]", ",banner @user"),
            "channelinfo": ("Shows information about a channel.", "channelinfo [channel]", ",channelinfo #general"),
            "roleinfo": ("Shows information about a role.", "roleinfo <role>", ",roleinfo @Member"),
            "membercount": ("Shows the server member count.", "membercount", ",membercount"),
            "roles": ("Lists the server's roles.", "roles", ",roles"),
            "emojis": ("Lists the server's custom emojis.", "emojis", ",emojis"),
            "stickers": ("Lists the server's stickers.", "stickers", ",stickers"),
            "permissions": ("Shows your permissions in this server.", "permissions [member]", ",permissions @user"),
            "guildicon": ("Shows the server icon.", "guildicon", ",guildicon"),
            "boost": ("Shows the server's boost information.", "boost", ",boost"),
            "autorole": ("Configures a role to give new members automatically.", "autorole [role]", ",autorole @Member"),
            "timeout": ("Mutes a member for a set amount of time.", "timeout <member> [minutes] [reason]", ",timeout @user 10 spam"),
            "unmute": ("Removes a member's timeout.", "unmute <member>", ",unmute @user"),
            "um": ("Removes a member's timeout.", "um <member>", ",um @user"),
            "untimeout": ("Removes a member's timeout.", "untimeout <member>", ",untimeout @user"),
            "ban": ("Bans a member from the server.", "ban <member> [reason]", ",ban @user breaking rules"),
            "unban": ("Unbans a user by ID.", "unban <user_id>", ",unban 123456789"),
            "kick": ("Kicks a member from the server.", "kick <member> [reason]", ",kick @user spam"),
            "warn": ("Gives a member a warning.", "warn <member> [reason]", ",warn @user spam"),
            "warnings": ("Shows a member's warnings.", "warnings [member]", ",warnings @user"),
            "purge": ("Deletes messages from the channel.", "purge [amount]", ",purge 25"),
            "lock": ("Locks the current channel.", "lock", ",lock"),
            "unlock": ("Unlocks the current channel.", "unlock", ",unlock"),
            "snipe": ("Shows the most recently deleted message.", "snipe", ",snipe"),
            "welcome": ("Sets the welcome message channel.", "welcome [channel]", ",welcome #welcome"),
            "disablewelcome": ("Disables welcome messages.", "disablewelcome", ",disablewelcome"),
            "booster": ("Configures or checks the server booster role.", "booster [role]", ",booster @Booster"),
            "boosterremove": ("Removes the configured booster role.", "boosterremove", ",boosterremove"),
            "ar": ("Manages server autoresponders.", "ar <add|remove|list|clear> [trigger] [response]", ",ar add hello | hi there!"),
            "autoresponder": ("Manages server autoresponders.", "autoresponder <add|remove|list|clear> [trigger] [response]", ",autoresponder add hello | hi there!"),
            "afk": ("Sets your AFK status.", "afk [reason]", ",afk eating"),
            "poll": ("Creates a yes/no poll.", "poll <question>", ",poll should we revamp?"),
            "choose": ("Chooses between options separated by |.", "choose <option1 | option2>", ",choose red | blue"),
            "8ball": ("Ask a question to the 8ball.", "8ball <question>", ",8ball will i ever get married?"),
            "coinflip": ("Flips a coin.", "coinflip", ",coinflip"),
            "roll": ("Rolls a random number.", "roll [sides]", ",roll 20"),
            "rate": ("Rates something from 0 to 100.", "rate <thing>", ",rate my setup"),
            "joke": ("Sends a random joke.", "joke", ",joke"),
            "fact": ("Sends a random fact.", "fact", ",fact"),
            "wyr": ("Creates a would-you-rather prompt.", "wyr <question>", ",wyr would you rather fly or be invisible?"),
            "mock": ("Turns text into alternating-case mock text.", "mock <text>", ",mock you are so funny"),
            "reverse": ("Reverses text.", "reverse <text>", ",reverse hello"),
            "simp": ("Gives a random simp percentage.", "simp [member]", ",simp @user"),
            "gayrate": ("Gives a random fun percentage.", "gayrate [member]", ",gayrate @user"),
            "howlucky": ("Gives your random luck percentage.", "howlucky", ",howlucky"),
            "shipname": ("Combines two users' names.", "shipname <member1> <member2>", ",shipname @user1 @user2"),
            "ship": ("Gives two users a random ship percentage.", "ship <member1> <member2>", ",ship @user1 @user2"),
            "hug": ("Gives someone a hug.", "hug [member]", ",hug @user"),
            "pat": ("Gives someone a pat.", "pat [member]", ",pat @user"),
            "slap": ("Bonks someone.", "slap [member]", ",slap @user"),
            "love": ("Sends someone some love.", "love [member]", ",love @user"),
            "roast": ("Roasts someone.", "roast [member]", ",roast @user"),
            "compliment": ("Compliments someone.", "compliment [member]", ",compliment @user"),
        }
        key = command.qualified_name.lower()
        description, syntax, example = info.get(key, (command.help or "No description available.", command.signature or command.qualified_name, f",{command.qualified_name}"))
        aliases = ", ".join(command.aliases) or "none"
        desc = (
            f"Command: {command.qualified_name}\n"
            f"{description}\n\n"
            f"**Aliases**\n{aliases}\n\n"
            f"**Usage**\n`Syntax: {PREFIX}{syntax}\nExample: {example}`"
        )
        return await ctx.send(embed=embed(None, desc))

    e = embed("bleeed", f"to use **bleeed** you must use the prefix `{PREFIX}`.\n\nexample: `{PREFIX}ping`\n\nuse `{PREFIX}commands` to see every command.\nuse `{PREFIX}help <command>` for command usage, aliases, and examples.")
    e.set_footer(text="bleeed â¢ simple, fast, clean")
    await ctx.send(embed=e)

@bot.command(name="commands", aliases=["cmd"])
async def command_list(ctx):
    groups = {
        "Information": ["afk", "avatar", "banner", "botinfo", "channelinfo", "emojis", "membercount", "permissions", "reverse", "roleinfo", "roles", "serverinfo", "stickers", "userinfo", "guildicon"],
        "Server": ["autoreact", "autoresponder", "autorole", "boost", "booster", "boosterremove", "disablewelcome", "snipe", "welcome"],
        "Security": ["lock", "unlock", "snipe"],
        "Moderation": ["ban", "unban", "kick", "mute", "unmute", "um", "untimeout", "warn", "warnings", "purge"],
        "Fun": ["8ball", "coinflip", "choose", "fact", "joke", "mock", "rate", "roll", "wyr", "reverse"],
        "Social": ["hug", "pat", "slap", "love", "simp", "gayrate", "howlucky", "shipname", "ship", "roast", "compliment"],
    }
    text = (
        "## bleeed help\n"
        "-# Experience the ultimate Discord bot designed for seamless management and community engagement.\n\n"
        + "\n\n".join(f"### {k}\n" + " ".join(f"`{x}`" for x in v) for k, v in groups.items())
        + f"\n\n-# Use `{PREFIX}help (command)` for details on a specific command"
    )
    e = embed(None, text)
    await ctx.send(embed=e)


@bot.command()
async def ping(ctx):
    await ctx.send(embed=embed("pong", f"`{round(bot.latency * 1000)}ms`"))


@bot.command()
async def uptime(ctx):
    s = int(time.time() - start_time)
    await ctx.send(embed=embed("uptime", f"<t:{int(start_time)}:R>\n`{s // 3600}h {(s % 3600) // 60}m {s % 60}s`"))


@bot.command(aliases=["av"])
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    e = embed(f"{member.display_name}'s avatar")
    e.set_image(url=member.display_avatar.url)
    await ctx.send(embed=e)


@bot.command(aliases=["ui"])
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = ", ".join(r.mention for r in member.roles[1:]) or "none"
    e = embed("user info", f"**user:** {fmt_user(member)}\n**joined:** <t:{int(member.joined_at.timestamp())}:R>\n**created:** <t:{int(member.created_at.timestamp())}:R>\n**roles:** {roles}")
    e.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=e)


@bot.command(aliases=["si"])
async def serverinfo(ctx):
    g = ctx.guild
    await ctx.send(embed=embed("server info", f"**name:** {g.name}\n**id:** `{g.id}`\n**owner:** <@{g.owner_id}>\n**members:** `{g.member_count}`\n**channels:** `{len(g.channels)}`\n**roles:** `{len(g.roles)}`\n**created:** <t:{int(g.created_at.timestamp())}:R>"))


@bot.command()
async def botinfo(ctx):
    e = embed("bleeed", f"**name:** `{bot.user}`\n**id:** `{bot.user.id}`\n**servers:** `{len(bot.guilds)}`\n**users:** `{sum(g.member_count or 0 for g in bot.guilds)}`\n**latency:** `{round(bot.latency * 1000)}ms`\n**prefix:** `{PREFIX}`")
    e.set_thumbnail(url=bot.user.display_avatar.url)
    await ctx.send(embed=e)

@bot.command()
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    asset = member.banner
    if asset is None:
        return await ctx.send(embed=embed("banner", f"{member.mention} doesn't have a banner."))
    e = embed(f"{member.display_name}'s banner")
    e.set_image(url=asset.url)
    await ctx.send(embed=e)

@bot.command()
async def channelinfo(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    e = embed("channel info", f"**name:** {channel.mention}\n**id:** `{channel.id}`\n**type:** `{channel.type}`\n**created:** <t:{int(channel.created_at.timestamp())}:R>")
    await ctx.send(embed=e)

@bot.command()
async def roleinfo(ctx, role: discord.Role):
    e = embed("role info", f"**role:** {role.mention}\n**id:** `{role.id}`\n**members:** `{len(role.members)}`\n**position:** `{role.position}`\n**managed:** `{role.managed}`")
    await ctx.send(embed=e)

@bot.command()
async def membercount(ctx):
    await ctx.send(embed=embed("member count", f"**{ctx.guild.member_count}** members are in **{ctx.guild.name}**."))

@bot.command()
async def roles(ctx):
    items = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
    text = " ".join(items) if items else "no roles."
    await ctx.send(embed=embed("roles", text[:4000]))

@bot.command()
async def emojis(ctx):
    text = " ".join(str(e) for e in ctx.guild.emojis) or "no custom emojis."
    await ctx.send(embed=embed("emojis", text[:4000]))

@bot.command()
async def stickers(ctx):
    text = " ".join(f"`{s.name}`" for s in ctx.guild.stickers) or "no stickers."
    await ctx.send(embed=embed("stickers", text[:4000]))

@bot.command()
async def permissions(ctx, member: discord.Member = None):
    member = member or ctx.author
    perms = [name.replace("_", " ") for name, value in member.guild_permissions if value]
    await ctx.send(embed=embed("permissions", f"**{member.mention}**\n\n" + " â¢ ".join(f"`{p}`" for p in perms)))

@bot.command()
async def guildicon(ctx):
    e = embed("server icon")
    if ctx.guild.icon:
        e.set_image(url=ctx.guild.icon.url)
    else:
        e.description = "this server doesn't have an icon."
    await ctx.send(embed=e)

@bot.command()
async def boost(ctx):
    g = ctx.guild
    await ctx.send(embed=embed("boost", f"**level:** `{g.premium_tier}`\n**boosts:** `{g.premium_subscription_count or 0}`\n**boosters:** `{sum(1 for m in g.members if m.premium_since)}`"))

@bot.command()
async def autorole(ctx, role: discord.Role = None):
    if role is None:
        current = autoroles.get(ctx.guild.id)
        return await ctx.send(embed=embed("autorole", f"current role: {current and current.mention or 'not configured'}"))
    if not ctx.author.guild_permissions.manage_roles:
        return await ctx.send(embed=embed("no permission", "you need Manage Roles."))
    me = ctx.guild.me
    if not me or role >= me.top_role:
        return await ctx.send(embed=embed("error", "my role must be above the autorole."))
    autoroles[ctx.guild.id] = role.id
    await ctx.send(embed=embed("autorole set", f"new members will receive {role.mention}."))

@bot.command(aliases=["to", "mute"])
async def timeout(ctx, member: discord.Member, minutes: int = 10, *, reason="no reason provided"):
    if not role_ok(ctx.author, MUTE_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required moderation role."))
    if not target_ok(ctx, member): return await ctx.send(embed=embed("error", "you can't moderate that member."))
    await member.timeout(timedelta(minutes=minutes), reason=reason)
    await ctx.send(embed=embed("member muted", f"{member.mention} was muted for **{minutes}m**.\nreason: {reason}"))


async def _remove_timeout(ctx, member):
    if not role_ok(ctx.author, MUTE_ROLES):
        return await ctx.send(embed=embed("no permission", "you don't have the required moderation role."))
    if not target_ok(ctx, member):
        return await ctx.send(embed=embed("error", "you can't moderate that member."))
    await member.timeout(None, reason=f"unmuted by {ctx.author}")
    await ctx.send(embed=embed("member unmuted", f"{member.mention} is no longer muted."))

@bot.command(name="unmute")
async def unmute_command(ctx, member: discord.Member):
    await _remove_timeout(ctx, member)

@bot.command(name="um")
async def um(ctx, member: discord.Member):
    await _remove_timeout(ctx, member)

@bot.command(name="untimeout")
async def untimeout(ctx, member: discord.Member):
    await _remove_timeout(ctx, member)


@bot.command(aliases=["b"])
async def ban(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author, {BAN_ROLE}): return await ctx.send(embed=embed("no permission", "you don't have the required ban role."))
    if not target_ok(ctx, member): return await ctx.send(embed=embed("error", "you can't ban that member."))
    await member.ban(reason=reason)
    await ctx.send(embed=embed("member banned", f"**{member}** was banned.\nreason: {reason}"))


@bot.command(aliases=["ub"])
async def unban(ctx, user_id: int):
    if not role_ok(ctx.author, {BAN_ROLE}): return await ctx.send(embed=embed("no permission", "you don't have the required ban role."))
    try:
        await ctx.guild.unban(discord.Object(id=user_id))
        await ctx.send(embed=embed("member unbanned", f"`{user_id}` was unbanned."))
    except discord.NotFound:
        await ctx.send(embed=embed("error", "that user isn't banned or the ID is invalid."))


@bot.command(aliases=["k"])
async def kick(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author, KICK_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required kick role."))
    if not target_ok(ctx, member): return await ctx.send(embed=embed("error", "you can't kick that member."))
    await member.kick(reason=reason)
    await ctx.send(embed=embed("member kicked", f"**{member}** was kicked.\nreason: {reason}"))


@bot.command(aliases=["w"])
async def warn(ctx, member: discord.Member, *, reason="no reason provided"):
    if not role_ok(ctx.author, WARN_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required warn role."))
    if not target_ok(ctx, member): return await ctx.send(embed=embed("error", "you can't warn that member."))
    warnings.setdefault(ctx.guild.id, {}).setdefault(member.id, []).append(reason)
    await ctx.send(embed=embed("member warned", f"{member.mention} received a warning.\nreason: {reason}"))


@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    items = warnings.get(ctx.guild.id, {}).get(member.id, [])
    text = "\n".join(f"**{i}.** {r}" for i, r in enumerate(items, 1)) or "no warnings."
    await ctx.send(embed=embed(f"warnings â¢ {member.display_name}", text))


@bot.command(aliases=["p", "clear"])
async def purge(ctx, amount: int = 10):
    if not role_ok(ctx.author, PURGE_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required purge role."))
    amount = max(1, min(amount, 100))
    deleted = await ctx.channel.purge(limit=amount + 1)
    msg = await ctx.send(embed=embed("purged", f"deleted **{len(deleted)-1}** messages."))
    await asyncio.sleep(3)
    try: await msg.delete()
    except discord.HTTPException: pass


@bot.command(aliases=["l"])
async def lock(ctx):
    if not role_ok(ctx.author, PURGE_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required purge role."))
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=embed("locked", f"{ctx.channel.mention} is now locked."))


@bot.command(aliases=["ul"])
async def unlock(ctx):
    if not role_ok(ctx.author, PURGE_ROLES): return await ctx.send(embed=embed("no permission", "you don't have the required purge role."))
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
    await ctx.send(embed=embed("unlocked", f"{ctx.channel.mention} is now unlocked."))


@bot.command(aliases=["s"])
async def snipe(ctx):
    data = getattr(bot, "_last_deleted", None)
    if not data or data[2].id != ctx.channel.id or time.time() - data[3] > 60:
        return await ctx.send(embed=embed("snipe", "nothing to snipe here."))
    author, content, channel, _ = data
    await ctx.send(embed=embed("sniped message", f"**{author}:** {content or '[no text]'}"))


@bot.command()
async def welcome(ctx, channel: discord.TextChannel = None):
    if not ctx.author.guild_permissions.manage_guild: return await ctx.send(embed=embed("no permission", "you need Manage Server."))
    channel = channel or ctx.channel
    welcome_channels[ctx.guild.id] = channel.id
    await ctx.send(embed=embed("welcome enabled", f"welcome messages will be sent in {channel.mention}."))


@bot.command()
async def disablewelcome(ctx):
    if not ctx.author.guild_permissions.manage_guild: return await ctx.send(embed=embed("no permission", "you need Manage Server."))
    welcome_channels.pop(ctx.guild.id, None)
    await ctx.send(embed=embed("welcome disabled", "welcome messages are now disabled."))


@bot.command()
async def booster(ctx, role: discord.Role = None):
    if role is None:
        current = boost_roles.get(ctx.guild.id)
        text = f"booster role: {current and current.mention or 'not configured'}\n\nboosters automatically receive the configured role when they boost."
        return await ctx.send(embed=embed("booster", text))
    if not ctx.author.guild_permissions.manage_roles:
        return await ctx.send(embed=embed("no permission", "you need Manage Roles."))
    if role >= ctx.guild.me.top_role:
        return await ctx.send(embed=embed("error", "my role must be above the booster role."))
    boost_roles[ctx.guild.id] = role.id
    await ctx.send(embed=embed("booster role set", f"boosters will receive {role.mention} when they boost."))

@bot.command(name="boosterremove", aliases=["booster-off"])
async def booster_remove(ctx):
    if not ctx.author.guild_permissions.manage_roles:
        return await ctx.send(embed=embed("no permission", "you need Manage Roles."))
    if boost_roles.pop(ctx.guild.id, None) is None:
        return await ctx.send(embed=embed("booster", "no booster role was configured."))
    await ctx.send(embed=embed("booster role removed", "the automatic booster role has been disabled."))


@bot.command(name="ar", aliases=["autoresponder"])
async def autoresponder(ctx, action: str = "list", *, data: str = ""):
    action = action.lower()
    guild_data = autoresponders.setdefault(ctx.guild.id, {})

    if action == "add":
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=embed("no permission", "you need Manage Server."))
        if "|" not in data:
            return await ctx.send(embed=embed("autoresponder", f"usage: `{PREFIX}ar add trigger | response`"))
        trigger, response = [x.strip() for x in data.split("|", 1)]
        if not trigger or not response:
            return await ctx.send(embed=embed("autoresponder", "both a trigger and response are required."))
        if trigger.lower().startswith(PREFIX):
            return await ctx.send(embed=embed("autoresponder", "triggers cannot start with the bot prefix."))
        if len(response) > 2000:
            return await ctx.send(embed=embed("autoresponder", "the response must be 2000 characters or less."))
        guild_data[trigger.lower()] = response
        return await ctx.send(embed=embed("autoresponder added", f"when someone says `{trigger}`, bleeed will respond with:\n{response}"))

    if action == "remove":
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=embed("no permission", "you need Manage Server."))
        trigger = data.strip().lower()
        if not trigger or trigger not in guild_data:
            return await ctx.send(embed=embed("autoresponder", "that autoresponder doesn't exist."))
        guild_data.pop(trigger, None)
        return await ctx.send(embed=embed("autoresponder removed", f"removed `{trigger}`."))

    if action == "clear":
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(embed=embed("no permission", "you need Manage Server."))
        guild_data.clear()
        return await ctx.send(embed=embed("autoresponders cleared", "all autoresponders for this server were removed."))

    if action == "list":
        if not guild_data:
            return await ctx.send(embed=embed("autoresponders", "no autoresponders are configured."))
        text = "\n".join(f"`{trigger}` â {response}" for trigger, response in list(guild_data.items())[:25])
        return await ctx.send(embed=embed("autoresponders", text))

    await ctx.send(embed=embed("autoresponder", f"usage: `{PREFIX}ar add trigger | response`"))

@bot.command(aliases=["afkset"])
async def afk(ctx, *, reason="AFK"):
    afks[ctx.author.id] = {"name": str(ctx.author), "reason": reason}
    await ctx.send(embed=embed("afk", f"{ctx.author.mention} is now AFK: {reason}"))


@bot.command()
async def poll(ctx, *, question):
    msg = await ctx.send(embed=embed("poll", question + "\n\nð yes\nð no"))
    await msg.add_reaction("ð")
    await msg.add_reaction("ð")


@bot.command()
async def choose(ctx, *, choices):
    options = [x.strip() for x in choices.split("|") if x.strip()]
    if len(options) < 2: return await ctx.send(embed=embed("choose", "separate choices with `|`."))
    await ctx.send(embed=embed("choice", random.choice(options)))


@bot.command(name="8ball", aliases=["8", "ball"])
async def eightball(ctx, *, question):
    answers = ["yes.", "no.", "probably.", "maybe.", "ask again later.", "definitely."]
    await ctx.send(embed=embed("8ball", random.choice(answers)))


@bot.command()
async def coinflip(ctx): await ctx.send(embed=embed("coinflip", random.choice(["heads", "tails"])))

@bot.command()
async def roll(ctx, sides: int = 6): await ctx.send(embed=embed("roll", f"ð² **{random.randint(1, max(2, sides))}**"))

@bot.command()
async def rate(ctx, *, thing): await ctx.send(embed=embed("rate", f"I'd rate **{thing}** a **{random.randint(0,100)}/100**."))

@bot.command()
async def joke(ctx): await ctx.send(embed=embed("joke", random.choice(["why did the computer get cold? it left its windows open.", "I told my PC I needed a break. now it won't stop sending me vacation ads.", "what do you call a sleeping bull? a bulldozer."])))

@bot.command()
async def fact(ctx): await ctx.send(embed=embed("fact", random.choice(["octopuses have three hearts.", "bananas are berries botanically.", "honey can remain edible for a very long time when properly stored."])))

@bot.command()
async def wyr(ctx, *, question): await ctx.send(embed=embed("would you rather", question))

@bot.command()
async def mock(ctx, *, text): await ctx.send(embed=embed("mock", " ".join(c.upper() if i % 2 else c.lower() for i,c in enumerate(text))))

@bot.command()
async def reverse(ctx, *, text): await ctx.send(embed=embed("reverse", text[::-1]))

@bot.command()
async def simp(ctx, member: discord.Member = None): await ctx.send(embed=embed("simp rate", f"{(member or ctx.author).mention} is **{random.randint(0,100)}%** simp."))

@bot.command()
async def gayrate(ctx, member: discord.Member = None): await ctx.send(embed=embed("rate", f"{(member or ctx.author).mention} got **{random.randint(0,100)}%**."))

@bot.command()
async def howlucky(ctx): await ctx.send(embed=embed("luck", f"your luck today is **{random.randint(0,100)}%**."))

@bot.command()
async def shipname(ctx, a: discord.Member, b: discord.Member):
    n = (a.display_name[:len(a.display_name)//2] + b.display_name[len(b.display_name)//2:]).replace(" ", "")
    await ctx.send(embed=embed("ship name", f"ð **{n}**"))

@bot.command()
async def ship(ctx, a: discord.Member, b: discord.Member): await ctx.send(embed=embed("ship", f"{a.mention} Ã {b.mention} = **{random.randint(0,100)}%**"))

for name, text in {
    "hug":"gave someone a hug.", "pat":"gave someone a pat.", "slap":"bonked someone.", "love":"sent some love.", "roast":"got roasted.", "compliment":"got a compliment."
}.items():
    def make_social(command_name, command_text):
        async def social(ctx, member: discord.Member = None):
            target = member or ctx.author
            await ctx.send(embed=embed(command_name, f"{ctx.author.mention} {command_text.replace('someone', target.mention)}"))
        social.__name__ = command_name
        return social
    bot.command()(make_social(name, text))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(embed=embed("missing argument", f"use `{PREFIX}help {ctx.command.qualified_name}` to see the correct usage."))
    if isinstance(error, commands.BadArgument):
        return await ctx.send(embed=embed("invalid argument", f"use `{PREFIX}help {ctx.command.qualified_name}` for usage."))
    if isinstance(error, commands.MissingPermissions):
        return await ctx.send(embed=embed("no permission", "you don't have permission to use that command."))
    if isinstance(error, commands.CommandInvokeError):
        print(f"Command error: {error.original}")
        return await ctx.send(embed=embed("error", "something went wrong while running that command."))
    raise error


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")

bot.run(TOKEN)
