# menubar-pomodoro

A macOS-native Pomodoro timer that lives in your menu bar. Single Python script, no Electron, no dependencies beyond PyObjC.

Cycle: 45m work → 5m short break, repeated 3 times, then a 15m long break.

## Features
- Native macOS menu bar icon (PyObjC/AppKit), changes to a "sleepy" icon during breaks
- Manual pause/resume from the menu
- Auto-pause during video calls (detects camera use via IOKit) and auto-resume when the call ends
- Detects system sleep/wake and restarts the cycle cleanly
- Notification + sound when a session ends

## Requirements
- macOS
- Python 3 with `pyobjc` installed: `pip3 install pyobjc`

## Running

```bash
python3 pomodoro.py           # start
python3 pomodoro.py --toggle  # pause/resume a running instance
```

## Running as a background service (Launch Agent)

1. Edit `com.user.pomodoro.plist` and replace `/Users/YOUR_USER/path/to/pomodoro/` with your actual path.
2. Install it:

```bash
cp com.user.pomodoro.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.pomodoro.plist
```

3. After editing `pomodoro.py`, restart the service:

```bash
launchctl kickstart -k gui/$(id -u)/com.user.pomodoro
```

## Configuration

Session lengths and paths are constants at the top of `pomodoro.py`. There's no config file, just edit the script.
