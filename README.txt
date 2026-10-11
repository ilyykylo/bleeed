bleeed v79 - dashboard + embed builder

FadeHost settings
- Runtime: Python
- Build: pip install -r requirements.txt
- Start: python3 main.py
- Environment: DISCORD_TOKEN = your Discord bot token
- Environment: DASHBOARD_PASSWORD = a long, unique password for the web dashboard
- Port: set PORT to the port assigned by your host if it does not provide 8080 by default

Dashboard
- Open the web service URL/port provided by your host.
- Browser authentication username: admin
- Password: the value of DASHBOARD_PASSWORD
- The dashboard lets you select a server and text channel, compose an embed, preview it, send it, or send a plain message.
- Only channels where the bot has Send Messages and Embed Links are listed for embeds.

Discord prefix embed command
,embed title | description | #000001 | https://example.com/image.png
Color and image URL are optional. Requires Manage Messages or Administrator.

Important
- Never share DISCORD_TOKEN or DASHBOARD_PASSWORD.
- Keep both values in FadeHost environment variables, never in GitHub source files.
- The bot needs appropriate Discord channel permissions to send messages and embeds.
- Dashboard reachability depends on FadeHost exposing the configured port and, ideally, HTTPS.
- Syntax and ZIP integrity checks passed. The dashboard and commands have not been tested against a live Discord server in this environment.
