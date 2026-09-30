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
level_data = {}
boost_roles = {}


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
    await bot.change_presence(activity=discord.Game(name=f"{PREFIX}help • bleeed"))
    print(f"bleeed online as {bot.user} ({bot.user.id})")


@bot.event
async def on_member_join(member):
    channel_id = welcome_channels.get(member.guild.id)
    if not channel_id:
        return
    channel = member.guild.get_channel(channel_id)
    if not channel:
        return
    e = embed("welcome", f"welcome {member.mention} to **{member.guild.name}**!\n\nmember **#{member.guild.member_count}**")
    e.set_thumbnail(url=member.display_avatar.url)
    await channel.send(embed=e)


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
            await channel.send(embed=embed("boost", f"thank you {after.mention} for boosting **{after.guild.name}**! ♡"))


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
            await message.channel.send(embed=embed("afk", f"**{data['name']}** is AFK — {data['reason']}"), delete_after=8)

    if not content.startswith(PREFIX):
        key = (message.guild.id, message.author.id) if message.guild else None
        if key:
            level_data[key] = level_data.get(key, 0) + random.randint(1, 3)
    await bot.process_commands(message)


@bot.command(aliases=["h"])
async def help(ctx, command_name: str = None):
    if command_name:
        command = bot.get_command(command_name.lower())
        if command is None:
            return await ctx.send(embed=embed("command not found", f"I couldn't find `,{command_name}`. Use `,commands` to see all commands."))
        aliases = ", ".join(f"`{PREFIX}{a}`" for a in command.aliases) or "none"
        usage = command.usage or (f"{PREFIX}{command.qualified_name}")
        desc = command.help or "no description available."
        return await ctx.send(embed=embed(f"{PREFIX}{command.qualified_name}", f"**description**\n{desc}\n\n**usage**\n`{usage}`\n\n**aliases**\n{aliases}"))

    e = embed("bleeed", f"to use **bleeed** you must use the prefix `{PREFIX}`.\n\nexample: `{PREFIX}ping`\n\nuse `{PREFIX}commands` to see every command.\nuse `{PREFIX}help <command>` for command usage and aliases.")
    e.set_footer(text="bleeed • simple, fast, clean")
    await ctx.send(embed=e)


@bot.command(aliases=["cmd"])
async def commands(ctx):
    groups = {
        "moderation": ["ban", "unban", "kick", "mute", "warn", "warnings", "purge", "lock", "unlock", "snipe"],
        "utility": ["ping", "uptime", "avatar", "userinfo", "serverinfo", "poll", "afk", "welcome", "disablewelcome", "booster"],
        "fun": ["8ball", "coinflip", "roll", "choose", "rps", "joke", "fact", "rate", "roast", "compliment", "wyr", "mock", "reverse"],
        "social": ["hug", "pat", "slap", "love", "simp", "gayrate", "howlucky", "shipname", "ship"],
        "levels": ["rank", "level", "leaderboard"],
    }
    text = "\n\n".join(f"**{k}**\n" + " • ".join(f"`{PREFIX}{x}`" for x in v) for k, v in groups.items())
    e = embed("bleeed commands", text)
    e.set_footer(text=f"use {PREFIX}help <command> for details")
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
    await ctx.send(embed=embed(f"warnings • {member.display_name}", text))


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
@commands.check(lambda ctx: role_ok(ctx.author, PURGE_ROLES))
async def lock(ctx):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(embed=embed("locked", f"{ctx.channel.mention} is now locked."))


@bot.command(aliases=["ul"])
@commands.check(lambda ctx: role_ok(ctx.author, PURGE_ROLES))
async def unlock(ctx):
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
    await ctx.send(embed=embed("booster role set", f"boosters will receive {role.mention}."))


@bot.command(aliases=["afkset"])
async def afk(ctx, *, reason="AFK"):
    afks[ctx.author.id] = {"name": str(ctx.author), "reason": reason}
    await ctx.send(embed=embed("afk", f"{ctx.author.mention} is now AFK: {reason}"))


@bot.command()
async def poll(ctx, *, question):
    msg = await ctx.send(embed=embed("poll", question + "\n\n👍 yes\n👎 no"))
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")


@bot.command()
async def choose(ctx, *, choices):
    options = [x.strip() for x in choices.split("|") if x.strip()]
    if len(options) < 2: return await ctx.send(embed=embed("choose", "separate choices with `|`."))
    await ctx.send(embed=embed("choice", random.choice(options)))


@bot.command(name="8ball")
async def eightball(ctx, *, question):
    answers = ["yes.", "no.", "probably.", "maybe.", "ask again later.", "definitely."]
    await ctx.send(embed=embed("8ball", random.choice(answers)))


@bot.command()
async def coinflip(ctx): await ctx.send(embed=embed("coinflip", random.choice(["heads", "tails"])))

@bot.command()
async def roll(ctx, sides: int = 6): await ctx.send(embed=embed("roll", f"🎲 **{random.randint(1, max(2, sides))}**"))

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
    await ctx.send(embed=embed("ship name", f"💗 **{n}**"))

@bot.command()
async def ship(ctx, a: discord.Member, b: discord.Member): await ctx.send(embed=embed("ship", f"{a.mention} × {b.mention} = **{random.randint(0,100)}%**"))

for name, text in {
    "hug":"gave someone a hug.", "pat":"gave someone a pat.", "slap":"bonked someone.", "love":"sent some love.", "roast":"got roasted.", "compliment":"got a compliment."
}.items():
    async def social(ctx, member: discord.Member = None, _text=text):
        member = member or ctx.author
        await ctx.send(embed=embed(name, f"{ctx.author.mention} {_text.replace('someone', member.mention)}"))
    social.__name__ = name
    bot.command()(social)


@bot.command(aliases=["level"])
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    xp = level_data.get((ctx.guild.id, member.id), 0)
    level = xp // 100
    await ctx.send(embed=embed("rank", f"{member.mention}\n**level:** `{level}`\n**xp:** `{xp % 100}/100`"))


@bot.command(aliases=["lb"])
async def leaderboard(ctx):
    rows = [(m, level_data.get((ctx.guild.id, m.id), 0)) for m in ctx.guild.members if not m.bot]
    rows.sort(key=lambda x: x[1], reverse=True)
    text = "\n".join(f"**{i}.** {m.mention} — `{xp} xp`" for i,(m,xp) in enumerate(rows[:10],1)) or "no data yet."
    await ctx.send(embed=embed("leaderboard", text))


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

client.login(process.env.DISCORD_TOKEN)
