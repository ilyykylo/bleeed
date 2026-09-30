import os, random, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks

PREFIX = ','
EMBED_COLOR = 0x000001
TOKEN = os.getenv('DISCORD_TOKEN')
BAN_ROLE = 1541538650355929168
MUTE_ROLES = {1541538650355929168,1540101656824258771,1535418806984384563,1535419879493210254}
WARN_ROLES = set(MUTE_ROLES)
KICK_ROLES = {1541538650355929168,1535419879493210254}
PURGE_ROLES = {1541538650355929168,1535419879493210254}

intents = discord.Intents.default(); intents.message_content=True; intents.members=True
bot = commands.Bot(command_prefix=PREFIX,intents=intents,help_command=None,case_insensitive=True)
start_time=time.time(); deleted_messages={}; afk_users={}; warnings=defaultdict(list); xp=defaultdict(lambda:{'xp':0,'level':0})
config=defaultdict(lambda:{'welcome':None,'welcome_on':False})

def E(title=None,desc=None): return discord.Embed(title=title,description=desc,color=EMBED_COLOR,timestamp=datetime.now(timezone.utc))
async def err(ctx,s): await ctx.send(embed=E('error',s),delete_after=6)
def ok(member,roles): return isinstance(member,discord.Member) and any(r.id in roles for r in member.roles)

@bot.event
async def on_ready():
    print(f'BLEEED online as {bot.user} ({bot.user.id})')
    if not presence.is_running(): presence.start()
@tasks.loop(minutes=10)
async def presence():
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,name=f'{len(bot.guilds)} servers | ,help'))
@bot.event
async def on_message_delete(message):
    if not message.author.bot: deleted_messages[message.channel.id]={'author':message.author,'content':message.content or '*no text*'}
@bot.event
async def on_message(message):
    if message.author.bot:return
    for u in message.mentions:
        if u.id in afk_users: await message.channel.send(f'{u.mention} is AFK: {afk_users[u.id]}',delete_after=6)
    if message.author.id in afk_users:
        afk_users.pop(message.author.id,None); await message.channel.send(f'Welcome back, {message.author.mention}. Your AFK was removed.',delete_after=5)
    if message.guild:
        d=xp[(message.guild.id,message.author.id)]; d['xp']+=random.randint(5,12); need=100+d['level']*50
        if d['xp']>=need:
            d['xp']-=need; d['level']+=1; await message.channel.send(f'🎉 {message.author.mention} reached level **{d["level"]}**!',delete_after=7)
    await bot.process_commands(message)
@bot.event
async def on_member_join(member):
    c=config[member.guild.id]
    if not c['welcome_on'] or not c['welcome']: return
    ch=member.guild.get_channel(c['welcome']);
    if not ch:return
    e=E('welcome to BLEEED',f'Welcome {member.mention} to **{member.guild.name}**!\nYou are member **#{member.guild.member_count}**.')
    e.set_thumbnail(url=member.display_avatar.url); await ch.send(embed=e)
@bot.event
async def on_command_error(ctx,x):
    if isinstance(x,commands.CommandNotFound):return
    if isinstance(x,commands.MissingRequiredArgument):return await err(ctx,f'Missing argument: `{x.param.name}`.')
    if isinstance(x,commands.BadArgument):return await err(ctx,'One of the arguments is invalid.')
    if isinstance(x,commands.CheckFailure):return await err(ctx,"You don't have permission to use that command.")
    if isinstance(x,commands.CommandOnCooldown):return await err(ctx,f'Try again in `{x.retry_after:.1f}s`.')
    print(x); await err(ctx,'Something went wrong.')

PAGES=[
('BLEEED • home','Use ◀ ▶ to browse commands.\n\nPrefix: `,`\nPages: moderation • fun • utility • social • config'),
('BLEEED • moderation','`,ban` `,unban` `,kick` `,mute` `,warn`\n`,warnings` `,purge` `,lock` `,unlock` `,snipe`'),
('BLEEED • fun','`,8ball` `,coinflip` `,roll` `,choose` `,rps`\n`,ship` `,rate` `,roast` `,compliment` `,joke`\n`,fact` `,wyr` `,mock` `,reverse`'),
('BLEEED • utility','`,ping` `,uptime` `,avatar` `,userinfo`\n`,serverinfo` `,afk` `,level` `,leaderboard` `,poll`'),
('BLEEED • social','`,hug` `,pat` `,slap` `,love` `,simp`\n`,gayrate` `,howlucky` `,shipname`'),
('BLEEED • config','`,welcome #channel`\n`,disablewelcome`\n\nWelcome is the only join/leave-style system enabled.')]
class Help(discord.ui.View):
    def __init__(self,uid): super().__init__(timeout=120); self.uid=uid; self.page=0
    async def interaction_check(self,i):
        if i.user.id!=self.uid: await i.response.send_message("This help menu isn't yours.",ephemeral=True); return False
        return True
    async def update(self,i):
        t,d=PAGES[self.page]; self.prev.disabled=self.page==0; self.nxt.disabled=self.page==len(PAGES)-1; e=E(t,d); e.set_footer(text=f'Page {self.page+1}/{len(PAGES)}'); await i.response.edit_message(embed=e,view=self)
    @discord.ui.button(emoji='◀',style=discord.ButtonStyle.secondary)
    async def prev(self,i,b): self.page=max(0,self.page-1); await self.update(i)
    @discord.ui.button(emoji='🏠',style=discord.ButtonStyle.secondary)
    async def home(self,i,b): self.page=0; await self.update(i)
    @discord.ui.button(emoji='▶',style=discord.ButtonStyle.secondary)
    async def nxt(self,i,b): self.page=min(len(PAGES)-1,self.page+1); await self.update(i)
@bot.command(name='help',aliases=['h'])
async def help_cmd(ctx):
    t,d=PAGES[0]; e=E(t,d); e.set_footer(text=f'Page 1/{len(PAGES)}'); await ctx.send(embed=e,view=Help(ctx.author.id))

@bot.command(name='ban',aliases=['b'])
@commands.guild_only()
async def ban(ctx,m:discord.Member,*,reason='No reason provided'):
    if not ok(ctx.author,{BAN_ROLE}):return await err(ctx,"You don't have permission to ban members.")
    if m==ctx.author or m.top_role>=ctx.author.top_role:return await err(ctx,"You can't ban that member.")
    try: await m.ban(reason=reason); await ctx.send(embed=E('member banned',f'{m.mention} was banned.\n**Reason:** {reason}'))
    except discord.Forbidden: await err(ctx,'Discord rejected the ban. Check role hierarchy.')
@bot.command(name='unban',aliases=['ub'])
@commands.guild_only()
async def unban(ctx,uid:int):
    if not ok(ctx.author,{BAN_ROLE}):return await err(ctx,"You don't have permission to unban members.")
    try: u=await bot.fetch_user(uid); await ctx.guild.unban(u); await ctx.send(embed=E('member unbanned',f'**{u}** was unbanned.'))
    except (discord.NotFound,discord.HTTPException): await err(ctx,'That user is not banned or the ID is invalid.')
@bot.command(name='kick',aliases=['k'])
@commands.guild_only()
async def kick(ctx,m:discord.Member,*,reason='No reason provided'):
    if not ok(ctx.author,KICK_ROLES):return await err(ctx,"You don't have permission to kick members.")
    if m==ctx.author or m.top_role>=ctx.author.top_role:return await err(ctx,"You can't kick that member.")
    try: await m.kick(reason=reason); await ctx.send(embed=E('member kicked',f'{m.mention} was kicked.\n**Reason:** {reason}'))
    except discord.Forbidden: await err(ctx,'Discord rejected the kick.')
@bot.command(name='mute',aliases=['timeout','to'])
@commands.guild_only()
async def mute(ctx,m:discord.Member,minutes:int=10,*,reason='No reason provided'):
    if not ok(ctx.author,MUTE_ROLES):return await err(ctx,"You don't have permission to mute members.")
    if not 1<=minutes<=40320:return await err(ctx,'Minutes must be between 1 and 40320.')
    if m==ctx.author or m.top_role>=ctx.author.top_role:return await err(ctx,"You can't mute that member.")
    try: await m.timeout(timedelta(minutes=minutes),reason=reason); await ctx.send(embed=E('member muted',f'{m.mention} was timed out for **{minutes} minutes**.\n**Reason:** {reason}'))
    except discord.Forbidden: await err(ctx,'Discord rejected the timeout.')
@bot.command(name='warn',aliases=['w'])
@commands.guild_only()
async def warn(ctx,m:discord.Member,*,reason='No reason provided'):
    if not ok(ctx.author,WARN_ROLES):return await err(ctx,"You don't have permission to warn members.")
    key=(ctx.guild.id,m.id); warnings[key].append(reason); await ctx.send(embed=E('member warned',f'{m.mention} received warning **#{len(warnings[key])}**.\n**Reason:** {reason}'))
@bot.command(name='warnings')
@commands.guild_only()
async def warns(ctx,m:discord.Member=None):
    m=m or ctx.author; items=warnings.get((ctx.guild.id,m.id),[]); await ctx.send(embed=E('warnings', '\n'.join(f'**{i}.** {x}' for i,x in enumerate(items[-10:],1)) if items else f'{m.mention} has no stored warnings.'))
@bot.command(name='purge',aliases=['p','clear'])
@commands.guild_only()
async def purge(ctx,amount:int):
    if not ok(ctx.author,PURGE_ROLES):return await err(ctx,"You don't have permission to purge.")
    if not 1<=amount<=100:return await err(ctx,'Amount must be between 1 and 100.')
    d=await ctx.channel.purge(limit=amount+1); await ctx.send(embed=E('messages purged',f'Deleted **{max(0,len(d)-1)}** messages.'),delete_after=4)
@bot.command(name='lock',aliases=['l'])
@commands.guild_only()
async def lock(ctx):
    if not ok(ctx.author,PURGE_ROLES):return await err(ctx,"You don't have permission to lock channels.")
    o=ctx.channel.overwrites_for(ctx.guild.default_role); o.send_messages=False; await ctx.channel.set_permissions(ctx.guild.default_role,overwrite=o); await ctx.send(embed=E('channel locked',f'{ctx.channel.mention} is now locked.'))
@bot.command(name='unlock',aliases=['ul'])
@commands.guild_only()
async def unlock(ctx):
    if not ok(ctx.author,PURGE_ROLES):return await err(ctx,"You don't have permission to unlock channels.")
    o=ctx.channel.overwrites_for(ctx.guild.default_role); o.send_messages=None; await ctx.channel.set_permissions(ctx.guild.default_role,overwrite=o); await ctx.send(embed=E('channel unlocked',f'{ctx.channel.mention} is now unlocked.'))
@bot.command(name='snipe',aliases=['s'])
async def snipe(ctx):
    d=deleted_messages.get(ctx.channel.id)
    if not d:return await err(ctx,'There is nothing to snipe.')
    e=E('sniped message',d['content']); e.set_author(name=str(d['author']),icon_url=d['author'].display_avatar.url); await ctx.send(embed=e)

@bot.command(name='8ball',aliases=['8b'])
async def ball(ctx,*,q): await ctx.send(embed=E('🎱 8ball',f'**Question:** {q}\n**Answer:** {random.choice(["yes.","no.","probably.","maybe.","ask me later.","definitely."])}'))
@bot.command(name='coinflip',aliases=['cf','flip'])
async def coin(ctx): await ctx.send(embed=E('🪙 coinflip',f'The coin landed on **{random.choice(["heads","tails"])}**.'))
@bot.command(name='roll',aliases=['dice'])
async def roll(ctx,sides:int=6):
    if not 2<=sides<=1000000:return await err(ctx,'Sides must be between 2 and 1,000,000.')
    await ctx.send(embed=E('🎲 roll',f'You rolled **{random.randint(1,sides)}**.'))
@bot.command(name='choose')
async def choose(ctx,*options):
    if len(options)<2:return await err(ctx,'Give me at least 2 options.')
    await ctx.send(embed=E('choose',f'I choose **{random.choice(options)}**.'))
@bot.command(name='rps')
async def rps(ctx,choice):
    c=choice.lower(); choices=['rock','paper','scissors']
    if c not in choices:return await err(ctx,'Choose rock, paper, or scissors.')
    b=random.choice(choices); result='Tie.' if c==b else ('You win!' if (c,b) in [('rock','scissors'),('paper','rock'),('scissors','paper')] else 'I win!'); await ctx.send(embed=E('✂️ rock paper scissors',f'You: **{c}**\nMe: **{b}**\n\n{result}'))
@bot.command(name='joke')
async def joke(ctx): await ctx.send(embed=E('joke',random.choice(['Why did the developer go broke? Because they used up all their cache.','I told my bot a joke. It said it needed better intents.','Why was the Discord bot calm? It had good moderation.'])))
@bot.command(name='fact')
async def fact(ctx): await ctx.send(embed=E('fact',random.choice(['Octopuses have three hearts.','Bananas are berries, botanically speaking.','A group of flamingos is commonly called a flamboyance.'])))
@bot.command(name='rate')
async def rate(ctx,*,thing): await ctx.send(embed=E('rating',f'I rate **{thing}** **{random.randint(0,100)}%**.'))
@bot.command(name='roast')
async def roast(ctx,m:discord.Member=None): await ctx.send(embed=E('🔥 roast',f'{(m or ctx.author).mention} — {random.choice(["Your Wi-Fi has more personality than you.","Even my error handler has more stability.","I would roast you, but I respect my CPU."])}'))
@bot.command(name='compliment')
async def compliment(ctx,m:discord.Member=None): await ctx.send(embed=E('💗 compliment',f'{(m or ctx.author).mention} {random.choice(["has immaculate vibes.","is genuinely awesome.","makes the server better just by being here."])}'))
@bot.command(name='wyr',aliases=['wouldyourather'])
async def wyr(ctx,*,q): await ctx.send(embed=E('would you rather',q))
@bot.command(name='mock')
async def mock(ctx,*,text): await ctx.send(embed=E('mock',''.join(c.upper() if i%2 else c.lower() for i,c in enumerate(text))))
@bot.command(name='reverse')
async def reverse(ctx,*,text): await ctx.send(embed=E('reverse',text[::-1]))

async def social(ctx,m,title,verb): m=m or ctx.author; await ctx.send(embed=E(title,f'{ctx.author.mention} {verb} {m.mention}'))
@bot.command(name='hug')
async def hug(ctx,m:discord.Member=None): await social(ctx,m,'🤗 hug','gave a big hug to')
@bot.command(name='pat')
async def pat(ctx,m:discord.Member=None): await social(ctx,m,'pat','gave a pat to')
@bot.command(name='slap')
async def slap(ctx,m:discord.Member=None): await social(ctx,m,'slap','gave a cartoon slap to')
@bot.command(name='love')
async def love(ctx,m:discord.Member=None): m=m or ctx.author; await ctx.send(embed=E('💗 love',f'{ctx.author.mention} love meter for {m.mention}: **{random.randint(0,100)}%**'))
@bot.command(name='simp')
async def simp(ctx,m:discord.Member=None): m=m or ctx.author; await ctx.send(embed=E('simp meter',f'{m.mention}: **{random.randint(0,100)}%** simp.'))
@bot.command(name='gayrate',aliases=['howgay'])
async def gayrate(ctx,m:discord.Member=None): m=m or ctx.author; await ctx.send(embed=E('🌈 rate',f'{m.mention}: **{random.randint(0,100)}%**'))
@bot.command(name='howlucky')
async def lucky(ctx,m:discord.Member=None): m=m or ctx.author; await ctx.send(embed=E('🍀 luck',f'{m.mention} is **{random.randint(0,100)}%** lucky today.'))
@bot.command(name='shipname')
async def shipname(ctx,a,b): await ctx.send(embed=E('💞 ship name',f'**{a} + {b}** = **{a[:max(1,len(a)//2)]+b[max(1,len(b)//2):]}**'))
@bot.command(name='ship')
async def ship(ctx,a:discord.Member,b:discord.Member): await ctx.send(embed=E('💞 ship',f'{a.mention} × {b.mention}\nCompatibility: **{random.randint(0,100)}%**'))

@bot.command(name='ping')
async def ping(ctx): await ctx.send(embed=E('🏓 ping',f'Latency: **{round(bot.latency*1000)}ms**'))
@bot.command(name='uptime')
async def uptime(ctx):
    s=int(time.time()-start_time); d,s=divmod(s,86400); h,s=divmod(s,3600); m,s=divmod(s,60); await ctx.send(embed=E('uptime',f'**{d}d {h}h {m}m {s}s**'))
@bot.command(name='avatar',aliases=['av'])
async def avatar(ctx,m:discord.Member=None): m=m or ctx.author; e=E(f'{m} • avatar'); e.set_image(url=m.display_avatar.url); await ctx.send(embed=e)
@bot.command(name='userinfo',aliases=['ui'])
async def userinfo(ctx,m:discord.Member=None):
    m=m or ctx.author; e=E(f'{m} • user info',f'**ID:** `{m.id}`\n**Created:** <t:{int(m.created_at.timestamp())}:F>\n**Joined:** <t:{int(m.joined_at.timestamp())}:F>'); e.set_thumbnail(url=m.display_avatar.url); await ctx.send(embed=e)
@bot.command(name='serverinfo',aliases=['si'])
async def serverinfo(ctx):
    g=ctx.guild; e=E(f'{g.name} • server info',f'**Owner:** <@{g.owner_id}>\n**Members:** {g.member_count}\n**Channels:** {len(g.channels)}\n**Roles:** {len(g.roles)}\n**Created:** <t:{int(g.created_at.timestamp())}:F>');
    if g.icon:e.set_thumbnail(url=g.icon.url)
    await ctx.send(embed=e)
@bot.command(name='level',aliases=['rank'])
async def level(ctx,m:discord.Member=None):
    m=m or ctx.author; d=xp[(ctx.guild.id,m.id)]; await ctx.send(embed=E('📈 level',f'{m.mention}\n**Level:** {d["level"]}\n**XP:** {d["xp"]}/{100+d["level"]*50}'))
@bot.command(name='leaderboard',aliases=['lb'])
async def leaderboard(ctx):
    rows=sorted([(uid,d['level'],d['xp']) for (gid,uid),d in xp.items() if gid==ctx.guild.id],key=lambda x:(x[1],x[2]),reverse=True); lines=[]
    for i,(uid,l,x) in enumerate(rows[:10],1):
        m=ctx.guild.get_member(uid)
        if m: lines.append(f'**{i}.** {m.mention} — level **{l}** ({x} XP)')
    await ctx.send(embed=E('🏆 leaderboard','\n'.join(lines) or 'No XP data yet.'))
@bot.command(name='afk')
async def afk(ctx,*,reason='AFK'): afk_users[ctx.author.id]=reason; await ctx.send(embed=E('AFK enabled',f'{ctx.author.mention} is now AFK: **{reason}**'))
@bot.command(name='poll')
async def poll(ctx,*,question):
    m=await ctx.send(embed=E('📊 poll',question)); await m.add_reaction('👍'); await m.add_reaction('👎')

@bot.command(name='welcome')
@commands.guild_only()
async def welcome(ctx,channel:discord.TextChannel=None):
    if not ok(ctx.author,WARN_ROLES):return await err(ctx,"You don't have permission to configure welcome messages.")
    if not channel:return await err(ctx,'Use `,welcome #channel`.')
    config[ctx.guild.id]['welcome']=channel.id; config[ctx.guild.id]['welcome_on']=True; await ctx.send(embed=E('welcome enabled',f'Welcome messages will be sent in {channel.mention}.'))
@bot.command(name='disablewelcome')
async def disablewelcome(ctx):
    if not ok(ctx.author,WARN_ROLES):return await err(ctx,"You don't have permission to configure this.")
    config[ctx.guild.id]['welcome_on']=False; await ctx.send(embed=E('welcome disabled','Welcome messages are now disabled.'))

if not TOKEN: raise RuntimeError('DISCORD_TOKEN environment variable is missing.')
bot.run(TOKEN)
