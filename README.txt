bleeed v77 - repository-inspired command directory

Changes:
- Used the public w6rd/bleed repository as general inspiration for a category-oriented command layout.
- The main help page now shows command categories and their registered command counts.
- Individual and group help cards now show an inferred module/category instead of incorrectly defaulting to "servers".
- Kept the existing Python/discord.py bot, prefix, moderation role configuration, booster-role system, and existing features.
- No JavaScript source was copied into the Python project.

Install:
1. Stop the bot.
2. Replace main.py with the included version.
3. Keep your existing DISCORD_TOKEN environment variable and requirements.txt.
4. Restart the bot.

Validation:
- Python syntax compilation passed.
- Static AST scan found no duplicate top-level literal command names.
- Runtime command registration was not tested in this environment because discord.py is not installed here.
