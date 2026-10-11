bleeed v94 - standardized help cards and cleaned command directory

FadeHost settings
- Runtime: Python
- Branch: main
- Build: pip install -r requirements.txt
- Start: python3 main.py
- Environment: DISCORD_TOKEN = your Discord bot token
- Environment: DASHBOARD_PASSWORD = a long, unique password for the web dashboard (if using it)

What's updated
- Prefix-command embeds use one compact black bleeed style with lowercase heading lines; legacy embed authors, footers, timestamps, and inconsistent colors are removed. Useful fields, images, thumbnails, and views are preserved.
- Shared make_embed replies are black everywhere, including command errors and event notices. Moderation DMs use a compact heading and retain the server icon thumbnail.
- The command directory is split into seven category-oriented pages for this build. Every page is capped to safe field/source lengths before rendering; page 7 is included and was checked against Discord's documented embed limits using static validation.
- Pagination errors are logged and get a private fallback notice when Discord allows it. Buttons still expire after 60 seconds, as configured.
- Added ,botcount / ,botscount, ,humancount / ,humanscount, and ,customrolecount / ,customroles.
- Existing ,channelcount and ,servercreated commands remain registered without duplicate entries.
- Static directory check: all 309 command-directory entries appear exactly once across seven pages.

Important
- Never share DISCORD_TOKEN or DASHBOARD_PASSWORD.
- Keep tokens and passwords in host environment variables, never in source code.
- Required Discord permissions and role hierarchy still apply.
- Python syntax, ZIP integrity, and static seven-page directory checks passed locally. This build has not been tested against a live Discord server here, so live button interaction cannot be guaranteed from this environment.


Version 94 updates
- Every `,h <command>` / `,help <command>` detail uses the same layout: Group Command, Aliases, Parameters, Information, and Usage.
- Nested group commands can be looked up by full path, e.g. `,h purge links`.
- The ban help card uses the requested syntax/example format: `Syntax: ban (user) (delete history) <reason> Example: ban jonathan 1d Threatening members`.
- The command directory now filters out stale documentation-only entries and duplicate command paths; it only lists commands that resolve to registered commands. This cleans the browser without deleting working bot functionality.
- Syntax compilation and archive integrity are checked locally. A live Discord run is still required to confirm runtime command registration and button interactions.
