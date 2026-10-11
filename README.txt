bleeed v88 - consistent minimal responses

FadeHost settings
- Runtime: Python
- Build: pip install -r requirements.txt
- Start: python3 main.py
- Environment: DISCORD_TOKEN = your Discord bot token
- Environment: DASHBOARD_PASSWORD = a long, unique password for the web dashboard (if using it)

Response style
- Command errors are one line, no embeds.
- Invalid arguments, missing arguments, too many arguments, and bad user input use:
  ⚠️ @user: Invalid arguement use ',help commandname'
  The command name is filled in automatically, for example ',help warn'.
- Missing permissions use the warning style, for example:
  ⚠️ @user: You're missing permission: ban_members
- Cooldowns and command failures also use compact warning replies.
- Existing approve-style action responses and Booster Role response formatting are preserved.

Important
- Never share DISCORD_TOKEN or DASHBOARD_PASSWORD.
- Keep tokens and passwords in host environment variables, never in source code.
- Required Discord permissions and role hierarchy still apply.
- Syntax and ZIP integrity checks are run locally; the bot has not been tested against a live Discord server here.
