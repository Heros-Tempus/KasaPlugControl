# Kasa Plug Battery Charge Controller

A cross-platform utility to control a Kasa smart plug for safe laptop battery charging.

## Features

* **Normal operation mode:** Battery monitoring via periodic polling.
* **Vigilance mode:** Engages when the battery is in a risky window; can trigger system hibernation on emergency to protect remaining charge.
* **Calibration routine:** Optional multi-cycle calibration routine to exercise full charge/discharge cycles.
* **Emergency alerts:** Pushover notifications for critical charging failures.
* **System tray icon:** For at-a-glance status and manual mode control (Windows, macOS, and Linux desktop environments).

---

## Prerequisites

* Python 3.8+
* A Kasa-compatible smart plug reachable on your local network (IP or MAC address).

---

## Installation

**1. Clone or download the repository:**
Navigate to the project folder in your terminal.

**2. Create a virtual environment:**
Isolating dependencies ensures this app doesn't interfere with other Python projects on your system.

* **Windows:**

    ```powershell
    python -m venv venv
    ```

* **macOS / Linux:**

    ```bash
    python3 -m venv venv
    ```

**3. Activate the virtual environment:**

* **Windows:**

    ```powershell
    venv\Scripts\activate
    ```

* **macOS / Linux:**

    ```bash
    source venv/bin/activate
    ```

**4. Install Python dependencies:**
With the virtual environment activated, install the required packages:

```bash
pip install -r requirements.txt
```

*(Note: Linux desktop users will also need system dependencies for the tray icon: ```sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-appindicator3-0.1```. GNOME users will need the AppIndicator and KStatusNotifierItem Support extension. On headless systems, the tray is skipped automatically and the program runs without it.)*

---

## Configuration

Before running the application, you must create a local configuration file.

1. Locate the ```config.example.py``` file in the project directory.
2. Make a copy of it and name the new file ```config.py```.
    * **Windows:** ```copy config.example.py config.py```
    * **macOS / Linux:** ```cp config.example.py config.py```
3. Open ```config.py``` in a text editor and fill in your specific details (e.g., ```PLUG_IP```, ```PLUG_MAC```, ```KASA_USERNAME```, ```KASA_PASSWORD```, and ```PUSHOVER``` tokens).

**Privacy Note:** The ```config.py``` file is strictly required for the app to function, but it is explicitly ignored by version control (via ```.gitignore```) to ensure your sensitive network data, passwords, and API tokens are never accidentally uploaded to a public repository. Never commit your ```config.py``` file!

---

## Quick Usage

Once installed and configured, you do not need to manually activate the virtual environment every time. You can use the provided launch scripts to start the background process and system tray icon:

* **Windows:** Double-click ```start.bat```
* **macOS / Linux:** Run ```./start.sh``` (you may need to run ```chmod +x start.sh``` first to make it executable).

Alternatively, if you are running it manually from an active virtual environment terminal:

```bash
python main.pyw
```

---

## Behavior Summary

* **Charging Bounds:** When the battery falls below ```NORMAL_CHARGE_ON_BELOW```, the plug is turned ON. When it rises above ```NORMAL_CHARGE_OFF_ABOVE```, the plug is turned OFF.
* **Vigilance Mode:** If the battery drops into a critically low threshold (```VIGILANCE_MIN_PERCENT``` to ```VIGILANCE_MAX_PERCENT```), the app monitors it closely. If the battery continues to drop despite the plug being on, the system will hibernate after a short grace period.
* **Charge Verification:** If the plug is commanded ON but the laptop does not register as charging within a set timeout, the app will power-cycle the plug. After 3 failed attempts, it sends an emergency notification.
* **Calibration:** If ```DO_CALIBRATION_CYCLES``` is enabled, on startup the app will override normal operation to perform full deep-discharge and 100% charge cycles to exercise the battery.

---

## Security & Safety

* **Failsafe Hibernation:** Battery emergencies trigger an immediate system hibernate. The command used is platform-dependent: ```shutdown /h /f``` on Windows, ```systemctl hibernate``` on Linux, and ```pmset sleepnow``` on macOS.
* **Notifications:** Pushover tokens are optional but highly recommended. If they are omitted, notification failures are simply logged locally.
* **Logging:** Events and errors are written locally to the file defined by ```LOG_FILE``` (default: ```battery_charge_controller.log```).

---

### License

MIT License
