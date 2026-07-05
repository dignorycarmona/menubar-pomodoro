# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

macOS-specific Pomodoro timer — a single Python 3 script (`pomodoro.py`) using PyObjC/AppKit for a native macOS menu bar icon. Managed as a background service via a macOS Launch Agent.

## Running

```bash
python3 pomodoro.py          # Start the timer
python3 pomodoro.py --toggle  # Pause/resume a running instance
```

**As a background service:**
```bash
cp com.user.pomodoro.plist ~/Library/LaunchAgents/
launchctl kickstart -k gui/$(id -u)/com.user.pomodoro  # restart after changes
```

## Architecture

Two components run in parallel within a single process:

- **GUI thread (main):** `PomodoroStatusBar` class (subclasses `NSObject`) — native macOS menu bar icon. Polls pause state every 1s via `NSTimer`. Menu has a single "Pause"/"Unpause" item that updates dynamically based on manual pause state.
- **Timer thread (daemon):** `run_pomodoro()` — cycles through work/break sessions (45m work → 5m short break, repeating 3 times, then 15m long break). Detects system wake via time jumps > 10s and restarts the cycle.

**IPC:** Two file-based pause flags:
- `~/.pomodoro_paused` — manual pause (toggled via menu item)
- `~/.pomodoro_camera_paused` — auto-pause when camera is in use (video call detection)

Timer resumes where it left off after any pause. Manual pause takes priority — if you manually pause during a call, it stays paused after the call ends.

**Camera detection:** `is_camera_in_use()` polls `ioreg -c IOAVCVideoDeviceType` every second to detect active video calls. Auto-pauses with a notification when camera turns on; auto-resumes when camera turns off (unless manually paused).

**macOS-specific:** Uses `osascript` for notifications, `afplay` for audio alerts (Ripples.m4r ringtone).

## Configuration

Session lengths and paths are constants at the top of `pomodoro.py`. No config files — edit the script directly.
