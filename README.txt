bleeed v99 - Consistent command response layout

Changes:
- Audited the shared Context.send wrapper: command replies sent through ctx.send are normalized to the compact bleeed embed style (legacy title/author/footer/timestamp and inconsistent colors removed; useful fields, thumbnails, images and views preserved).
- Fixed `,nick` to use the same approve/deny action response format as other action commands: green approve response on success, red deny response on failure, with the invoking user's mention.
- Added handling for Discord permission/hierarchy failures when changing a nickname, so those return a red deny response rather than a traceback.
- Includes the v98 sticky message and personal to-do list features.

Install all three files on FadeHost and restart bleeed.
Validation: Python syntax compilation and ZIP integrity checks passed. Live Discord behavior was not tested. This shared wrapper covers command responses routed through ctx.send; direct Discord interaction responses and messages sent directly through channel/user objects may use separate code paths and are not guaranteed to be normalized by this wrapper.


v100 update:
- Converted `,nuke` into a command group while preserving the original `,nuke` channel-recreation flow.
- Added `,nuke roles`, an administrator-only role cleanup command with a 30-second confirmation prompt.
- The role nuke excludes @everyone, integration/bot-managed roles, and every role at or above bleeed's current highest role; hierarchy is checked again immediately before each delete.
- Nuke prompts and interaction results use the compact `# command` embed layout, with green approve and red deny action responses.
- Existing `ctx.send` embed normalization remains in place for prefix commands; direct interaction/event messages are normalized individually where updated.
- Validation: Python syntax compilation and ZIP integrity checks passed. Live Discord behavior has not been tested.
