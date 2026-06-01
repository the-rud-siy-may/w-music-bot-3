# Wakie Music Bot — Cursor Master Prompt

Use this prompt when continuing work on the Wakie bot in Cursor Agent mode.

## Project

Python bot for **LDPlayer + Wakie voice chat**: reads chat via uiautomator2, parses `/commands`, streams music with VLC, replies in chat.

**Run:** `py main.py` (or `.venv\Scripts\python.exe main.py`)

**Config:** `storage/.env` and `config.py`

```env
WAKIE_BOT_USERNAME=Anuraag
WAKIE_OWNER=your_owner_name
WAKIE_DELEGATED=mod1,mod2
WAKIE_ADB_SERIAL=emulator-5554
WAKIE_LOCAL_AUTOPLAY=true
WAKIE_SAFE_SEND=true
WAKIE_MESSAGE_TTL=120
```

**Local autoplay:** put `.mp3` files in `songs/` (e.g. `believer.mp3`, `faded.mp3`). When the user queue is empty, the bot loops these files — no YouTube fetch.

## Architecture

```
main.py → bot/runtime.py (WakieBot)
  ├── Poll loop: MessageReader → MessageDetector → CommandParser → CommandDispatcher
  ├── PlaybackEngine: StreamQueueManager → AudioPlayer (VLC)
  ├── LocalAutoplayManager (songs/) or AutoplayManager (YouTube JSON)
  ├── MessageFilter (self-message / bot-prefix / duplicate)
  ├── MessageCleanupScheduler (auto-delete after 2 min)
  └── ClubSessionMonitor (clear queue when call ends)
```

## Implemented behaviour

| Feature | Details |
|--------|---------|
| Self-loop fix | `WAKIE_BOT_USERNAME`, outbound cache, bot prefix filter |
| Skip / remove ownership | Users only skip/remove **their** songs; `WAKIE_OWNER` + `WAKIE_DELEGATED` = admins for anyone |
| `/siya` | Replies: "Siya is my gf i love her a lot 💕" |
| Fun replies | Random extras on greet, add, skip |
| Reply to command | `@username` prefix or long-press Reply when UI allows |
| Auto-delete chat | Bot replies + user commands deleted after `WAKIE_MESSAGE_TTL` (default 120s) |
| Club end | Missing chat UI → clear queue, stop playback, reset caches |
| First `/add` when idle | Extra line: "Give it a moment — your song will start shortly!" |
| Safe send | No Enter/hierarchy taps that hit LEAVE CALL — send button resource-id only |
| Unknown commands | 30s dedup per user+command; no repeat spam |
| Local autoplay | `songs/*.mp3` shuffle loop when queue empty |

## Key files

- `commands/public_commands.py` — add, skip, remove, siya, queue
- `commands/dispatcher.py` — routing, unknown dedup, reply/delete
- `player/stream_queue.py` — ownership checks on skip/remove/clear
- `player/local_autoplay.py` — local file loop
- `wakie/chat.py` + `send_finder.py` — safe send
- `wakie/chat_actions.py` — reply + delete bubbles
- `wakie/session_monitor.py` — club end detection
- `wakie/message_cleanup.py` — TTL deletion scheduler

## Admin setup

- **Owner:** `WAKIE_OWNER` in `.env`
- **Admins/mods:** comma-separated `WAKIE_DELEGATED` — can skip/remove/clear anyone's songs

## Common tasks for the agent

1. Add a command → `utils/constants.py` + handler in `commands/public_commands.py` (or delegated/owner)
2. Add local song → drop file in `songs/`, restart not required (autoplay rescans on cycle)
3. Debug chat read → `py test_chat_reader.py`, check `logs/`
4. Debug send leaving club → ensure `WAKIE_SAFE_SEND=true`, only `com.wakie.android:id/send` clicks

## Do not

- Block `unknown` username (real Wakie fallback when name not parsed)
- `await ensure_autoplay_track()` before poll loop (blocks chat for minutes on YouTube)
- Use global Enter / `action_filter` / `air_action` for send (leaves club)
