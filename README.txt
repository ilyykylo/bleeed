bleeed v104 — all command embeds consistency pass

This update expands the shared Context.send response normalizer so simple replies from all prefix commands use the compact bleeed style:
- successful actions use <:approve:1558768853058588682> and green
- errors/permission failures use <:deny:1558768856552439878> and red
- action lines include the command user mention and no old title/footer/author
- informational, help, fun, and rich embeds keep their useful content while using compact lowercase headings, black color, and no footer/author/timestamp
- examples in help/usage text use backticks

Install by replacing main.py, requirements.txt, and README.txt on FadeHost, then restart the bot.

Validation: Python syntax compilation and ZIP integrity checks passed. This is not a live Discord test; check your server after restart for command-specific edge cases.
