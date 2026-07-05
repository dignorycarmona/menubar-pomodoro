"""
Build a standalone .app: python3 setup.py py2app
"""
from setuptools import setup

setup(
    app=["pomodoro.py"],
    name="Pomodoro",
    options={
        "py2app": {
            "argv_emulation": False,
            "iconfile": "assets/icon.icns",
            "plist": {
                "CFBundleName": "Pomodoro",
                "CFBundleIdentifier": "com.user.pomodoro",
                "LSUIElement": True,
                "LSBackgroundOnly": False,
            },
        }
    },
    setup_requires=["py2app"],
)
