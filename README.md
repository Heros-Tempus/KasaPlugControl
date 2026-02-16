# Kasa Plug Battery Charge Controller

A small Windows utility to control a Kasa smart plug for safe laptop battery charging.

Features
- Normal operation mode: battery monitoring via periodic polling.
- Vigilance mode when battery is in a risky window; can trigger hibernation on emergency.
- Optional multi-cycle calibration routine to exercise full charge/discharge cycles.
- Pushover notifications for critical alerts.

Prerequisites
- Python 3.8+
- Kasa-compatible smart plug reachable on the LAN (IP or MAC)

Python dependencies
Run:

```bash
pip install kasa psutil requests
```

Configuration
- Copy the example config and edit the values:

```bash
cp config.example.py config.py
# then edit config.py to set PLUG_IP, PLUG_MAC, PUSHOVER_*, and thresholds
```

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
- The software will call Windows `shutdown /h /f` on severe battery emergencies. Use with care.
- Pushover tokens optional, though recommended. If they are ommited then the notification failure will be logged.
- Keep Pushover tokens private and secure.

License
- MIT-style (add or adapt as you prefer).

Questions or changes
- Open an issue or modify the README for improvements.
