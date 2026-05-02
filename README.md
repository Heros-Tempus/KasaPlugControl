# Kasa Plug Battery Charge Controller

A cross-platform utility to control a Kasa smart plug for safe laptop battery charging.

Features

- Normal operation mode: battery monitoring via periodic polling.
- Vigilance mode when battery is in a risky window; can trigger hibernation on emergency.
- Optional multi-cycle calibration routine to exercise full charge/discharge cycles.
- Pushover notifications for critical alerts.
- System tray icon for at-a-glance status and manual mode control (Windows, macOS, and Linux desktop environments).

Prerequisites

- Python 3.8+
- Kasa-compatible smart plug reachable on the LAN (IP or MAC)

Python dependencies

Run:

```bash
pip install kasa psutil requests pystray Pillow
```

Linux system tray dependencies (desktop only, not required on headless systems):

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1
```

Note: GNOME users will also need the [AppIndicator and KStatusNotifierItem Support](https://extensions.gnome.org/extension/615/appindicator-support/) extension. On headless systems the tray is skipped automatically and the program runs without it.

Configuration

Copy the example config and edit the values.

Windows:

```powershell
copy config.example.py config.py
```

Linux / macOS:

```bash
cp config.example.py config.py
```

Then edit `config.py` to set `PLUG_IP`, `PLUG_MAC`, `KASA_USERNAME`, `KASA_PASSWORD`, `PUSHOVER_*`, and thresholds.

See [config.example.py](config.example.py) for all settings and sensible defaults.

Quick usage

Run the controller:

```bash
python main.pyw
```

Notes

- Calibration cycles (long-running) are enabled via `DO_CALIBRATION_CYCLES` and controlled by `CALIBRATION_CYCLES` in `config.py`.
- Logs are written to the file defined by `LOG_FILE` (default: `battery_charge_controller.log`).
- Emergency notifications use Pushover — provide `PUSHOVER_USER_KEY` and `PUSHOVER_APP_TOKEN` in `config.py`.

Behavior summary

- When the battery percent falls below `NORMAL_CHARGE_ON_BELOW` the plug will be turned ON.
- When the battery percent rises above `NORMAL_CHARGE_OFF_ABOVE` the plug will be turned OFF.
- If the battery drops suddenly while in a vigilance window and not charging, the system will hibernate.
- If the plug is turned ON but charging does not start, the system retries and can send an emergency notification.

Development and testing

- For quick testing, set `DO_CALIBRATION_CYCLES = False` to avoid long calibration waits.
- Be sure to set the smart plug's `PLUG_MAC` or `PLUG_IP` properly.

Security & safety

- Battery emergencies trigger an immediate system hibernate. The command used is platform-dependent: `shutdown /h /f` on Windows, `systemctl hibernate` on Linux, and `pmset sleepnow` on macOS.
- Pushover tokens optional, though recommended. If they are ommited then the notification failure will be logged.
- Keep Pushover tokens and Kasa credentials private and out of version control (the default `.gitignore` excludes `config.py`).

License

- MIT-style (add or adapt as you prefer).

Questions or changes

- Open an issue or modify the README for improvements.
