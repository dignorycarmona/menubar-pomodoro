import time
import os
import subprocess
import signal
import sys
import argparse
import threading
import objc
from AppKit import (
    NSApplication, NSStatusBar, NSMenu, NSMenuItem, NSTimer, NSRunLoop,
    NSDefaultRunLoopMode, NSVariableStatusItemLength, NSFont,
    NSAttributedString, NSFontAttributeName, NSApplicationActivationPolicyAccessory,
    NSBeep,
)
from Foundation import NSDate, NSObject

# Configuration
WORK_MIN = 45
SHORT_BREAK_MIN = 5
LONG_BREAK_MIN = 15
TOTAL_WORK_SESSIONS = 3
# Notification sound: an Apple ringtone first, then a stable system sound. If both are ever
# moved by a macOS update, notify() falls back to NSBeep so the chime never silently vanishes.
SOUND_PATHS = [
    "/System/Library/PrivateFrameworks/ToneLibrary.framework/Versions/A/Resources/Ringtones/Hillside.m4r",
    "/System/Library/Sounds/Ping.aiff",  # always-present system alert sound
]
SLEEP_THRESHOLD = 10  # Seconds jump to trigger restart
PAUSE_FILE = os.path.expanduser("~/.pomodoro_paused")
CAMERA_PAUSE_FILE = os.path.expanduser("~/.pomodoro_camera_paused")  # auto-pause during video calls
BREAK_FILE = os.path.expanduser("~/.pomodoro_break")  # set by timer thread while on a break

class PomodoroStatusBar(NSObject):
    def init(self):
        self = objc.super(PomodoroStatusBar, self).init()
        if self is None:
            return None

        self.app = NSApplication.sharedApplication()
        self.app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )

        # Build the dropdown menu
        menu = NSMenu.alloc().init()
        self.toggle_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Pause", "togglePause:", ""
        )
        self.toggle_item.setTarget_(self)
        menu.addItem_(self.toggle_item)

        menu.addItem_(NSMenuItem.separatorItem())
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit", "terminate:", "q"
        )
        quit_item.setTarget_(self.app)
        menu.addItem_(quit_item)

        self.status_item.setMenu_(menu)

        self.update_icon()

        # Poll pause state every second
        self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
            1.0, self, "updateIcon:", None, True
        )
        NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSDefaultRunLoopMode)
        return self

    def update_icon(self):
        manually_paused = os.path.exists(PAUSE_FILE)
        sleepy = manually_paused or os.path.exists(CAMERA_PAUSE_FILE) or os.path.exists(BREAK_FILE)
        title = "(ᴗ˳ᴗ)ᶻ𝗓𐰁" if sleepy else "( ◡̀_◡́)ᕤ"
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(14)}
        self.status_item.button().setAttributedTitle_(
            NSAttributedString.alloc().initWithString_attributes_(title, attrs)
        )
        self.toggle_item.setTitle_("Unpause" if manually_paused else "Pause")

    @objc.typedSelector(b"v@:@")
    def updateIcon_(self, timer):
        self.update_icon()

    @objc.typedSelector(b"v@:@")
    def togglePause_(self, sender):
        toggle_paused()
        self.update_icon()


def play_sound():
    """Plays the first available sound; falls back to NSBeep so a missing file never goes silent."""
    for path in SOUND_PATHS:
        if os.path.exists(path):
            subprocess.Popen(["afplay", path])
            return
    NSBeep()

def notify(title, message):
    """Sends a macOS notification and plays a soft alert sound."""
    print(f"[{time.strftime('%H:%M:%S')}] {title}: {message}", flush=True)

    safe_title = title.replace('\\', '\\\\').replace('"', '\\"')
    safe_message = message.replace('\\', '\\\\').replace('"', '\\"')
    script = f'display notification "{safe_message}" with title "{safe_title}"'
    subprocess.run(["osascript", "-e", script])

    play_sound()

def set_paused(state):
    """Creates or removes the pause file and sends a notification."""
    if state:
        if not os.path.exists(PAUSE_FILE):
            with open(PAUSE_FILE, "w") as f:
                f.write("paused")
            print(f"Pomodoro paused. File created: {PAUSE_FILE}", flush=True)
            notify("Pomodoro Paused", "The timer is now paused.")
    else:
        try:
            os.remove(PAUSE_FILE)
            print("Pomodoro resumed.", flush=True)
            notify("Pomodoro Resumed", "Continuing your cycle.")
        except FileNotFoundError:
            pass

def is_camera_in_use():
    """True if any camera is streaming. Matches on the FrontCameraStreaming key across all
    camera classes, so it works on any chip — class names like AppleH16CamIn are
    chip-generation-specific and differ across M1/M2/M3/M4."""
    try:
        result = subprocess.run(
            ["ioreg", "-r", "-k", "FrontCameraStreaming", "-w", "0"],
            capture_output=True, text=True, timeout=3
        )
        return '"FrontCameraStreaming" = Yes' in result.stdout
    except Exception:
        pass
    return False

def toggle_paused():
    """Toggles the pause state."""
    set_paused(not os.path.exists(PAUSE_FILE))

def sync_camera_pause():
    """Auto-pause when the camera turns on, auto-resume when it turns off (unless manually
    paused). Single source of truth for camera state, used by both wait and pause loops."""
    if is_camera_in_use():
        if not os.path.exists(CAMERA_PAUSE_FILE):
            open(CAMERA_PAUSE_FILE, "w").close()
            notify("Pomodoro Paused", "Video call detected — timer paused.")
        return
    if os.path.exists(CAMERA_PAUSE_FILE):
        os.remove(CAMERA_PAUSE_FILE)
        if not os.path.exists(PAUSE_FILE):
            notify("Pomodoro Resumed", "Call ended — continuing your cycle.")

def check_paused():
    """Blocks while either pause is active; syncs camera state so the call-end resume fires."""
    while os.path.exists(PAUSE_FILE) or os.path.exists(CAMERA_PAUSE_FILE):
        sync_camera_pause()
        if not os.path.exists(PAUSE_FILE) and not os.path.exists(CAMERA_PAUSE_FILE):
            break
        time.sleep(1)

def wait_with_wake_check(seconds, label):
    """Waits for specified seconds, returns True if a system wake is detected."""
    last_t = time.time()
    start_t = last_t
    remaining = seconds

    while remaining > 0:
        time.sleep(1)

        sync_camera_pause()

        # Block while either pause is active
        if os.path.exists(PAUSE_FILE) or os.path.exists(CAMERA_PAUSE_FILE):
            check_paused()
            last_t = time.time()
            start_t = last_t - (seconds - remaining)

        curr_t = time.time()

        if curr_t - last_t > SLEEP_THRESHOLD:
            print(f"Wake detected! Restarting Pomodoro cycle...", flush=True)
            return True

        last_t = curr_t
        remaining = seconds - round(curr_t - start_t)
    return False

def set_break(state):
    """Creates or removes the break flag that drives the 'sleepy' menu bar icon."""
    if state:
        if not os.path.exists(BREAK_FILE):
            open(BREAK_FILE, "w").close()
    elif os.path.exists(BREAK_FILE):
        os.remove(BREAK_FILE)

def run_pomodoro():
    while True:
        # Check if we should start in paused mode
        set_break(False)
        check_paused()
        
        print("Starting a new Pomodoro cycle (3 sessions).", flush=True)
        
        for session in range(1, TOTAL_WORK_SESSIONS + 1):
            # Work Session
            set_break(False)
            notify(f"Work Session {session}/{TOTAL_WORK_SESSIONS}", f"Time to focus for {WORK_MIN} minutes.")

            if wait_with_wake_check(WORK_MIN * 60, f"Work {session}"):
                break # Wake or Resume: Restart from Outer Loop

            # Break Session
            set_break(True)
            if session < TOTAL_WORK_SESSIONS:
                notify("Short Break", f"Rest for {SHORT_BREAK_MIN} minutes.")
                if wait_with_wake_check(SHORT_BREAK_MIN * 60, f"Short Break {session}"):
                    break
            else:
                notify("Long Break", f"Rest for {LONG_BREAK_MIN} minutes.")
                if wait_with_wake_check(LONG_BREAK_MIN * 60, "Long Break"):
                    break
                # Cycle finished naturally, 'else' will trigger 'continue' to restart sessions.
        else:
            # If for loop finished without 'break', we loop back naturally.
            continue
        
        # If 'break' was hit (wake, resume, or deactivate), we are here and the 'while True' restarts.

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pomodoro Timer for macOS")
    parser.add_argument("--toggle", action="store_true", help="Toggle the pause state of the running timer")
    args = parser.parse_args()

    if args.toggle:
        toggle_paused()
        sys.exit(0)

    # Start Pomodoro logic in a background thread
    threading.Thread(target=run_pomodoro, daemon=True).start()

    # Start macOS status bar app on main thread
    bar = PomodoroStatusBar.alloc().init()

    # Terminate cleanly on external SIGINT/SIGTERM. Python signal handlers don't run while the
    # main thread is blocked in NSApp.run() (AppKit's C run loop), so hop back onto it with
    # callAfter — the 1s status-bar timer gives Python the window to notice the pending signal.
    import PyObjCTools.AppHelper as AppHelper
    def _graceful_exit(*_):
        AppHelper.callAfter(bar.app.terminate_, None)
    signal.signal(signal.SIGINT, _graceful_exit)
    signal.signal(signal.SIGTERM, _graceful_exit)

    bar.app.run()
