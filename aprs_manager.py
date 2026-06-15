#!/usr/bin/env python3
import os
import sys
import webbrowser
import json
import socket
import argparse
import subprocess
import threading
import time
import getpass
import hashlib
from datetime import datetime

# Base Directory Configurations
BASE_DIR = os.path.expanduser('~/.aprs-beacon')
PROFILES_DIR = os.path.join(BASE_DIR, 'profiles')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Security & Auth Configurations
CURRENT_USER = getpass.getuser()
IS_BYPASS = (CURRENT_USER == 'turan')

def get_admin_pin_hash():
    pin_file = os.path.join(BASE_DIR, '.admin_pin')
    if not os.path.exists(pin_file):
        # Default PIN: "7373"
        default_hash = hashlib.sha256("7373".encode()).hexdigest()
        try:
            with open(pin_file, 'w') as f:
                f.write(default_hash)
        except:
            pass
        return default_hash
    try:
        with open(pin_file, 'r') as f:
            return f.read().strip()
    except:
        return ""

def verify_pin(input_pin):
    stored_hash = get_admin_pin_hash()
    input_hash = hashlib.sha256(input_pin.encode()).hexdigest()
    return stored_hash == input_hash

def cli_require_auth():
    if IS_BYPASS:
        return True
    print("\033[93m[!] Admin PIN is required for this operation.\033[0m")
    for _ in range(3):
        pin = getpass.getpass("Admin PIN: ").strip()
        if verify_pin(pin):
            return True
        print("\033[91mError: Invalid PIN code!\033[0m")
    return False

def gui_require_auth(parent=None):
    if IS_BYPASS:
        return True
    pin = simpledialog.askstring("Authorization", "Please enter the Admin PIN:", show="*", parent=parent)
    if pin is None:
        return False
    if verify_pin(pin):
        return True
    messagebox.showerror("Error", "Invalid PIN code!", parent=parent)
    return False

# Detect OS/Environment
IS_ANDROID = os.path.exists('/data/data/com.termux') or 'TERMUX_VERSION' in os.environ
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = not IS_ANDROID and (sys.platform.startswith('linux') or sys.platform.startswith('freebsd'))

# Check GUI Libraries
GUI_AVAILABLE = True
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog, filedialog
    from PIL import Image, ImageDraw
    import pystray
except ImportError:
    GUI_AVAILABLE = False

# Passcode Generator
def generate_aprs_passcode(callsign):
    callsign = callsign.upper().split('-')[0]
    hash_val = 0x73e2
    for i in range(0, len(callsign), 2):
        char1 = ord(callsign[i]) << 8
        char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
        hash_val ^= (char1 + char2)
    return hash_val & 0x7fff

# Platform Dependent Service Operations
def ensure_linux_systemd_template():
    if not IS_LINUX:
        return
    systemd_dir = os.path.expanduser('~/.config/systemd/user')
    os.makedirs(systemd_dir, exist_ok=True)
    template_path = os.path.join(systemd_dir, 'aprs-beacon@.service')
    
    python_path = sys.executable or '/usr/bin/python3'
    script_path = os.path.join(BASE_DIR, 'aprs_beacon.py')
    
    service_content = f"""[Unit]
Description=APRS Background Beacon Service (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={python_path} {script_path} --profile %i
Restart=always
RestartSec=30
WorkingDirectory={BASE_DIR}

[Install]
WantedBy=default.target
"""
    try:
        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(service_content)
        subprocess.run(['systemctl', '--user', 'daemon-reload'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Failed to create systemd template service: {e}", file=sys.stderr)

def is_profile_running(profile_name):
    if IS_LINUX:
        ensure_linux_systemd_template()
        res = subprocess.run(['systemctl', '--user', 'is-active', f'aprs-beacon@{profile_name}.service'], capture_output=True, text=True)
        return res.stdout.strip() == 'active'
    elif IS_WINDOWS:
        cmd = f'Get-ScheduledTask -TaskName "APRSBeacon-{profile_name}" | Select-Object -ExpandProperty State'
        res = subprocess.run(['powershell', '-Command', cmd], capture_output=True, text=True)
        return res.stdout.strip() == 'Running'
    elif IS_ANDROID:
        try:
            res = subprocess.run(['pgrep', '-f', f'aprs_beacon.py --profile {profile_name}'], capture_output=True, text=True)
            return bool(res.stdout.strip())
        except:
            return False
    return False

def is_service_enabled(profile_name):
    if IS_LINUX:
        try:
            res = subprocess.run(['systemctl', '--user', 'is-enabled', f'aprs-beacon@{profile_name}.service'], capture_output=True, text=True)
            return res.stdout.strip() == 'enabled'
        except:
            return False
    elif IS_WINDOWS:
        try:
            check_cmd = f'Get-ScheduledTask -TaskName "APRSBeacon-{profile_name}"'
            res = subprocess.run(['powershell', '-Command', check_cmd], capture_output=True, text=True)
            return "Ready" in res.stdout or "Running" in res.stdout
        except:
            return False
    return False

def set_service_enabled(profile_name, enable):
    if IS_LINUX:
        ensure_linux_systemd_template()
        if enable:
            subprocess.run(['systemctl', '--user', 'enable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                subprocess.run(['loginctl', 'enable-linger', CURRENT_USER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except:
                pass
        else:
            subprocess.run(['systemctl', '--user', 'disable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_WINDOWS:
        if enable:
            register_windows_task(profile_name)
        else:
            remove_profile_service(profile_name)

def start_profile_service(profile_name):
    if IS_LINUX:
        ensure_linux_systemd_template()
        subprocess.run(['systemctl', '--user', 'enable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl', '--user', 'start', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_WINDOWS:
        check_cmd = f'Get-ScheduledTask -TaskName "APRSBeacon-{profile_name}"'
        res = subprocess.run(['powershell', '-Command', check_cmd], capture_output=True, text=True)
        if "ObjectNotFound" in res.stderr or res.returncode != 0:
            register_windows_task(profile_name)
        cmd = f'Start-ScheduledTask -TaskName "APRSBeacon-{profile_name}"'
        subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_ANDROID:
        script_path = os.path.join(BASE_DIR, 'aprs_beacon.py')
        cmd = f'termux-wake-lock; nohup {sys.executable or "python3"} {script_path} --profile {profile_name} >/dev/null 2>&1 &'
        subprocess.run(cmd, shell=True)
        boot_dir = os.path.expanduser('~/.termux/boot')
        os.makedirs(boot_dir, exist_ok=True)
        boot_script = os.path.join(boot_dir, f'aprs-beacon-{profile_name}')
        with open(boot_script, 'w', encoding='utf-8') as f:
            f.write(f'''#!/usr/bin/env bash
termux-wake-lock
nohup {sys.executable or "python3"} {script_path} --profile {profile_name} >/dev/null 2>&1 &
''')
        os.chmod(boot_script, 0o755)

def stop_profile_service(profile_name):
    if IS_LINUX:
        subprocess.run(['systemctl', '--user', 'stop', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_WINDOWS:
        cmd = f'Stop-ScheduledTask -TaskName "APRSBeacon-{profile_name}"'
        subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_ANDROID:
        subprocess.run(f'pkill -f "aprs_beacon.py --profile {profile_name}"', shell=True)
        boot_script = os.path.expanduser(f'~/.termux/boot/aprs-beacon-{profile_name}')
        if os.path.exists(boot_script):
            try:
                os.remove(boot_script)
            except:
                pass

def register_windows_task(profile_name):
    python_path = sys.executable or 'python'
    script_path = os.path.join(BASE_DIR, 'aprs_beacon.py')
    cmd = f'''
    $action = New-ScheduledTaskAction -Execute "{python_path}" -Argument '"{script_path}" --profile {profile_name}'
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    Register-ScheduledTask -TaskName "APRSBeacon-{profile_name}" -Action $action -Trigger $trigger -Settings $settings -Force
    '''
    subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def remove_profile_service(profile_name):
    stop_profile_service(profile_name)
    if IS_WINDOWS:
        cmd = f'Unregister-ScheduledTask -TaskName "APRSBeacon-{profile_name}" -Confirm:$false'
        subprocess.run(['powershell', '-Command', cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_LINUX:
        subprocess.run(['systemctl', '--user', 'disable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def self_update():
    repo_path_file = os.path.join(BASE_DIR, '.repo_path')
    if not os.path.exists(repo_path_file):
        return False, "Error: Installation source directory (.repo_path) not found. Please run the setup script manually."
    try:
        with open(repo_path_file, 'r', encoding='utf-8') as f:
            repo_path = f.read().strip()
        if not os.path.exists(repo_path):
            return False, f"Error: Source directory ({repo_path}) does not exist."
        if not IS_WINDOWS:
            res = subprocess.run(['git', 'pull'], cwd=repo_path, capture_output=True, text=True)
            if res.returncode != 0:
                return False, f"Git Pull Error:\n{res.stderr}"
        else:
            res = subprocess.run(['powershell', '-Command', 'git pull'], cwd=repo_path, capture_output=True, text=True)
            if res.returncode != 0:
                return False, f"Git Pull Error:\n{res.stderr}"
        
        stdout_lower = res.stdout.lower()
        if "already up to date" in stdout_lower or "already up-to-date" in stdout_lower or "zaten güncel" in stdout_lower:
            return True, "Already up-to-date."
            
        import shutil
        shutil.copy2(os.path.join(repo_path, 'aprs_beacon.py'), os.path.join(BASE_DIR, 'aprs_beacon.py'))
        shutil.copy2(os.path.join(repo_path, 'aprs_manager.py'), os.path.join(BASE_DIR, 'aprs_manager.py'))
        return True, "Application updated successfully! Please close and reopen the app to apply changes."
    except Exception as e:
        return False, f"Update Error: {e}"

def export_settings(export_file_path):
    try:
        profiles = get_profiles()
        backup_data = {
            "version": "1.0",
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "profiles": profiles
        }
        with open(export_file_path, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, indent=4)
        return True, f"Settings exported successfully: {export_file_path}"
    except Exception as e:
        return False, f"Export error: {e}"

def import_settings(import_file_path):
    try:
        with open(import_file_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        profiles = backup_data.get("profiles", {})
        if not profiles:
            return False, "Error: No profile records found in the selected file."
        if not IS_BYPASS:
            current_profiles = get_profiles()
            union_profiles = set(current_profiles.keys()) | set(profiles.keys())
            if len(union_profiles) > 2:
                return False, f"Error: Importing will exceed the limit of 2 profiles (currently {len(union_profiles)} profiles total)."
        for name, data in profiles.items():
            save_profile(name, data)
        return True, f"Successfully imported {len(profiles)} profiles."
    except Exception as e:
        return False, f"Import error: {e}"

def get_profiles():
    profiles = {}
    if os.path.exists(PROFILES_DIR):
        for f in os.listdir(PROFILES_DIR):
            if f.endswith('.json'):
                name = f[:-5]
                try:
                    with open(os.path.join(PROFILES_DIR, f), 'r', encoding='utf-8') as file:
                        profiles[name] = json.load(file)
                except:
                    pass
    return profiles

def save_profile(name, data):
    profile_path = os.path.join(PROFILES_DIR, f"{name}.json")
    with open(profile_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def delete_profile_files(name):
    remove_profile_service(name)
    profile_path = os.path.join(PROFILES_DIR, f"{name}.json")
    if os.path.exists(profile_path):
        os.remove(profile_path)
    log_path = os.path.join(LOGS_DIR, f"{name}.log")
    if os.path.exists(log_path):
        try:
            os.remove(log_path)
        except:
            pass

def get_packet_count(profile_name):
    log_file = os.path.join(LOGS_DIR, f"{profile_name}.log")
    if not os.path.exists(log_file):
        return 0
    count = 0
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "Packet successfully sent" in line or "Paket basariyla gonderildi" in line or "Paket başarıyla gönderildi" in line:
                    count += 1
    except:
        pass
    return count

# APRS-IS Messaging Helper Function
def send_aprs_message(from_callsign, passcode, to_callsign, message_text):
    server = "rotate.aprs2.net"
    port = 14580
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((server, port))
        
        # Receive greeting
        s.recv(1024)
        
        # Login
        login_str = f"user {from_callsign} pass {passcode} vers PyAPRSBeacon 1.0\r\n"
        s.sendall(login_str.encode('utf-8'))
        s.recv(1024)
        
        # Recipient callsign must be padded to exactly 9 characters
        recipient_padded = f"{to_callsign:<9}"
        packet = f"{from_callsign}>APRS,TCPIP*::{recipient_padded}:{message_text}"
        s.sendall(f"{packet}\r\n".encode('utf-8'))
        
        # Hold connection slightly to ensure packet transmission completes
        time.sleep(1.0)
        s.close()
        return True, "Message sent successfully."
    except Exception as e:
        return False, f"Failed to send message: {e}"

# CLI Mode Implementation
def cli_list():
    profiles = get_profiles()
    if not profiles:
        print("No registered APRS profiles found.")
        return
    print("\n=== APRS Beacon Profiles ===")
    print(f"{'Profile Name':<15} | {'Callsign':<12} | {'Interval':<8} | {'Thursday':<9} | {'Status':<10} | {'Autostart':<9}")
    print("-" * 78)
    for name, data in profiles.items():
        running = is_profile_running(name)
        enabled = is_service_enabled(name)
        status_str = "\033[92mActive\033[0m" if running else "\033[91mStopped\033[0m"
        autostart_str = "Enabled" if enabled else "Disabled"
        thursday_str = "Active" if data.get('aprs_thursday', False) else "Disabled"
        print(f"{name:<15} | {data.get('callsign', 'N0CALL'):<12} | {data.get('interval_minutes', 5):<8} | {thursday_str:<9} | {status_str:<10} | {autostart_str:<9}")
    print()

def cli_create():
    if not IS_BYPASS and len(get_profiles()) >= 2:
        print("\033[91mError: You can add at most 2 profiles. Elevation required for more.\033[0m")
        return
    if not cli_require_auth():
        return
    print("\n=== Create New APRS Profile ===")
    name = input("Profile Name (Single word, e.g. mobile): ").strip().lower()
    if not name:
        print("Error: Profile name cannot be empty.")
        return
    profiles = get_profiles()
    if name in profiles:
        print(f"Error: Profile '{name}' already exists.")
        return
    callsign = input("Callsign (e.g. TA2XYZ-9): ").strip().upper()
    if not callsign:
        print("Error: Callsign cannot be empty.")
        return
    passcode_input = input("APRS-IS Passcode [Enter to calculate]: ").strip()
    if not passcode_input:
        passcode = generate_aprs_passcode(callsign)
        print(f"Auto-calculated passcode: {passcode}")
    else:
        try:
            passcode = int(passcode_input)
        except:
            print("Error: Invalid passcode format.")
            return
    try:
        lat = float(input("Latitude (e.g. 41.037): ").strip())
        lon = float(input("Longitude (e.g. 28.985): ").strip())
    except ValueError:
        print("Error: Coordinates must be numeric.")
        return
    comment = input("Status Comment [Default: APRS Background Beacon]: ").strip()
    if not comment:
        comment = "APRS Background Beacon"
    symbol_code = input("Symbol Character [Default: X (Helicopter)]: ").strip()
    if not symbol_code:
        symbol_code = "X"
    try:
        interval = int(input("Interval (Minutes) [Default: 5]: ").strip() or 5)
    except ValueError:
        interval = 5
    thursday_input = input("Participate in APRS Thursday? (ANSRVR) [y/N]: ").strip().lower()
    aprs_thursday = thursday_input == 'y'
    aprs_thursday_time = "20:00"
    aprs_thursday_msg = "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY"
    if aprs_thursday:
        aprs_thursday_time = input("APRS Thursday time (e.g. 20:00) [Default: 20:00]: ").strip() or "20:00"
        aprs_thursday_msg = input("APRS Thursday message [Default: CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY]: ").strip() or "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY"
    data = {
        "callsign": callsign,
        "passcode": passcode,
        "latitude": lat,
        "longitude": lon,
        "use_termux_gps": False,
        "symbol_table": "/",
        "symbol_code": symbol_code,
        "comment": comment,
        "interval_minutes": interval,
        "aprs_thursday": aprs_thursday,
        "aprs_thursday_time": aprs_thursday_time,
        "aprs_thursday_msg": aprs_thursday_msg,
        "server": "rotate.aprs2.net",
        "port": 14580
    }
    save_profile(name, data)
    print(f"\n[+] Profile created successfully: {name}")
    run_now = input("Start service now? [Y/n]: ").strip().lower()
    if run_now != 'n':
        start_profile_service(name)
        print(f"[+] Profile '{name}' started in background.")

def cli_delete(name):
    if not cli_require_auth():
        return
    profiles = get_profiles()
    if name not in profiles:
        print(f"Error: Profile '{name}' not found.")
        return
    delete_profile_files(name)
    print(f"[+] Profile '{name}' deleted successfully.")

def cli_start(name):
    profiles = get_profiles()
    if name not in profiles:
        print(f"Error: Profile '{name}' not found.")
        return
    start_profile_service(name)
    print(f"[+] Profile '{name}' started.")

def cli_stop(name):
    profiles = get_profiles()
    if name not in profiles:
        print(f"Error: Profile '{name}' not found.")
        return
    stop_profile_service(name)
    print(f"[+] Profile '{name}' stopped.")

def cli_edit():
    if not cli_require_auth():
        return
    print("\n=== Update Profile Settings ===")
    profiles = get_profiles()
    if not profiles:
        print("No profiles found to update.")
        return
    name = input("Enter profile name to update: ").strip().lower()
    if name not in profiles:
        print(f"Error: Profile '{name}' not found.")
        return
    data = profiles[name]
    print(f"\nUpdating: {name.upper()}")
    print("Tip: Leave empty and press Enter to keep current value.")
    callsign = input(f"Callsign ({data.get('callsign')}): ").strip().upper() or data.get('callsign')
    passcode_in = input(f"Passcode ({data.get('passcode')}): ").strip()
    passcode = int(passcode_in) if passcode_in else data.get('passcode')
    try:
        lat_in = input(f"Latitude ({data.get('latitude')}): ").strip()
        lat = float(lat_in) if lat_in else data.get('latitude')
        lon_in = input(f"Longitude ({data.get('longitude')}): ").strip()
        lon = float(lon_in) if lon_in else data.get('longitude')
    except ValueError:
        print("Error: Coordinates must be numeric. Canceled.")
        return
    comment = input(f"Status Comment ({data.get('comment')}): ").strip() or data.get('comment')
    symbol = input(f"Symbol Character ({data.get('symbol_code')}): ").strip() or data.get('symbol_code')
    try:
        interval_in = input(f"Interval ({data.get('interval_minutes')} min): ").strip()
        interval = int(interval_in) if interval_in else data.get('interval_minutes')
    except ValueError:
        interval = data.get('interval_minutes')
    thursday_in = input(f"APRS Thursday ({'Active' if data.get('aprs_thursday', False) else 'Disabled'}) [y/N]: ").strip().lower()
    aprs_thursday = data.get('aprs_thursday', False)
    if thursday_in:
        aprs_thursday = thursday_in == 'y'
    aprs_thursday_time = data.get('aprs_thursday_time', '20:00')
    aprs_thursday_msg = data.get('aprs_thursday_msg', 'CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY')
    if aprs_thursday:
        thursday_time_in = input(f"APRS Thursday time ({aprs_thursday_time}): ").strip()
        if thursday_time_in:
            aprs_thursday_time = thursday_time_in
        thursday_msg_in = input(f"APRS Thursday message ({aprs_thursday_msg}): ").strip()
        if thursday_msg_in:
            aprs_thursday_msg = thursday_msg_in
    updated_data = {
        "callsign": callsign,
        "passcode": passcode,
        "latitude": lat,
        "longitude": lon,
        "use_termux_gps": False,
        "symbol_table": "/",
        "symbol_code": symbol,
        "comment": comment,
        "interval_minutes": interval,
        "aprs_thursday": aprs_thursday,
        "aprs_thursday_time": aprs_thursday_time,
        "aprs_thursday_msg": aprs_thursday_msg,
        "server": "rotate.aprs2.net",
        "port": 14580
    }
    save_profile(name, updated_data)
    print(f"[+] Profile '{name}' updated successfully.")
    if is_profile_running(name):
        print("[i] Profile is running in background, restarting to apply changes...")
        stop_profile_service(name)
        time.sleep(0.5)
        start_profile_service(name)
        print("[+] Profile restarted successfully.")

# APRS-IS Messenger Window Class
class APRSChatWindow(tk.Toplevel):
    def __init__(self, parent, default_profile_name=None):
        super().__init__(parent)
        self.parent = parent
        self.title("APRS Messenger")
        self.geometry("560x540")
        self.configure(bg="#090a0f")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        
        self.c_bg = "#f1f5f9"
        self.c_card = "#ffffff"
        self.c_border = "#cbd5e1"
        self.c_text_main = "#0f172a"
        self.c_text_muted = "#475569"
        self.c_accent = "#2563eb"
        self.c_green = "#047857"
        self.c_red = "#b91c1c"
        
        self.profiles = get_profiles()
        if not self.profiles:
            messagebox.showerror("Error", "You must configure at least one profile to use APRS Chat.")
            self.destroy()
            return
            
        self.active_profile = default_profile_name or list(self.profiles.keys())[0]
        
        self.socket_listener = None
        self.listener_running = False
        self.socket_thread = None
        
        self.build_ui()
        self.start_listener()
        
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def build_ui(self):
        # Header / Profile Info Frame
        top_frame = tk.Frame(self, bg=self.c_card, bd=0, highlightthickness=1, highlightbackground=self.c_border, padx=15, pady=12)
        top_frame.pack(fill="x", side="top")
        
        # Dropdown grid
        tk.Label(top_frame, text="From Profile:", font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_card).grid(row=0, column=0, sticky="w", pady=5)
        
        profile_names = list(self.profiles.keys())
        self.profile_var = tk.StringVar(value=self.active_profile)
        
        # Option menu
        self.profile_menu = ttk.OptionMenu(
            top_frame, self.profile_var, self.active_profile, *profile_names, command=self.on_profile_change
        )
        self.profile_menu.grid(row=0, column=1, sticky="w", padx=10, pady=5)
        self.profile_menu.configure(width=12)
        
        tk.Label(top_frame, text="To Callsign:", font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_card).grid(row=0, column=2, sticky="w", padx=(25, 0), pady=5)
        
        self.to_entry = tk.Entry(top_frame, bg=self.c_bg, fg=self.c_text_main, insertbackground=self.c_text_main, 
                                 bd=0, highlightthickness=1, highlightbackground=self.c_border, font=("Helvetica", 10), width=12)
        self.to_entry.grid(row=0, column=3, sticky="w", padx=10, pady=5)
        self.to_entry.insert(0, "SMSGTE") # Default to SMS gateway
        
        def to_focus_in(e): self.to_entry.configure(highlightbackground=self.c_accent)
        def to_focus_out(e): self.to_entry.configure(highlightbackground=self.c_border)
        self.to_entry.bind("<FocusIn>", to_focus_in)
        self.to_entry.bind("<FocusOut>", to_focus_out)
        
        # Chat History Panel
        chat_frame = tk.Frame(self, bg=self.c_bg)
        chat_frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        self.chat_area = tk.Text(chat_frame, bg="#ffffff", fg=self.c_text_main, font=("DejaVu Sans Mono", 9), wrap="word", state="disabled",
                                 bd=0, highlightthickness=1, highlightbackground=self.c_border)
        self.chat_area.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(chat_frame, orient="vertical", command=self.chat_area.yview)
        scrollbar.pack(side="right", fill="y")
        self.chat_area.configure(yscrollcommand=scrollbar.set)
        
        self.chat_area.tag_config("system", foreground=self.c_text_muted, font=("Helvetica", 9, "italic"))
        self.chat_area.tag_config("sent", foreground=self.c_green, font=("Helvetica", 9, "bold"))
        self.chat_area.tag_config("received", foreground=self.c_accent, font=("Helvetica", 9, "bold"))
        
        # Bottom Input Frame
        input_frame = tk.Frame(self, bg=self.c_card, bd=0, highlightthickness=1, highlightbackground=self.c_border, padx=15, pady=10)
        input_frame.pack(fill="x", side="bottom")
        
        self.msg_entry = tk.Entry(input_frame, bg=self.c_bg, fg=self.c_text_main, insertbackground=self.c_text_main, 
                                  bd=0, highlightthickness=1, highlightbackground=self.c_border, font=("Helvetica", 10))
        self.msg_entry.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 10))
        self.msg_entry.bind("<FocusIn>", lambda e: self.msg_entry.configure(highlightbackground=self.c_accent))
        self.msg_entry.bind("<FocusOut>", lambda e: self.msg_entry.configure(highlightbackground=self.c_border))
        
        self.msg_entry.bind("<Return>", lambda e: self.send_message_action())
        
        self.char_lbl = tk.Label(input_frame, text="0/67", font=("Helvetica", 8), fg=self.c_text_muted, bg=self.c_card)
        self.char_lbl.pack(side="left", padx=(0, 10))
        
        def validate_msg(event):
            val = self.msg_entry.get()
            if len(val) > 67:
                self.msg_entry.delete(67, tk.END)
            self.char_lbl.configure(text=f"{min(len(val), 67)}/67")
        self.msg_entry.bind("<KeyRelease>", validate_msg)
        
        self.send_btn = tk.Button(input_frame, text="Send", bg=self.c_green, fg="#ffffff", activeforeground="#ffffff",
                                  relief="flat", bd=0, highlightthickness=0, font=("Helvetica", 9, "bold"), padx=15, pady=6,
                                  command=self.send_message_action)
        self.send_btn.pack(side="right")
        self.send_btn.bind("<Enter>", lambda e: self.send_btn.configure(bg="#059669"))
        self.send_btn.bind("<Leave>", lambda e: self.send_btn.configure(bg=self.c_green))

    def on_profile_change(self, profile_name):
        self.active_profile = profile_name
        self.start_listener()
        
    def start_listener(self):
        self.stop_listener()
        if not self.active_profile or self.active_profile not in self.profiles:
            return
            
        data = self.profiles[self.active_profile]
        callsign = data.get('callsign', '').upper()
        passcode = data.get('passcode')
        if not passcode:
            passcode = generate_aprs_passcode(callsign)
            
        self.listener_running = True
        self.socket_thread = threading.Thread(
            target=self.listener_worker,
            args=(callsign, passcode),
            daemon=True
        )
        self.socket_thread.start()
        
    def stop_listener(self):
        self.listener_running = False
        if self.socket_listener:
            try:
                self.socket_listener.close()
            except:
                pass
            self.socket_listener = None

    def listener_worker(self, callsign, passcode):
        server = "rotate.aprs2.net"
        port = 14580
        try:
            self.socket_listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket_listener.settimeout(8.0)
            self.socket_listener.connect((server, port))
            
            # Read greeting
            self.socket_listener.recv(1024)
            
            # Login
            login_str = f"user {callsign} pass {passcode} vers PyAPRSBeacon 1.0 filter b/{callsign}\r\n"
            self.socket_listener.sendall(login_str.encode('utf-8'))
            self.socket_listener.recv(1024)
            
            self.append_message("SYSTEM", f"Connected as {callsign}. Real-time chat enabled.")
            
            self.socket_listener.settimeout(None)
            buffer = ""
            while self.listener_running:
                data = self.socket_listener.recv(4096)
                if not data:
                    break
                buffer += data.decode('utf-8', errors='ignore')
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    self.parse_and_display_packet(line, callsign)
        except Exception as e:
            if self.listener_running:
                self.append_message("SYSTEM", f"Connection lost: {e}")
                
    def parse_and_display_packet(self, line, my_callsign):
        if "::" in line:
            try:
                parts = line.split("::", 1)
                header = parts[0]
                payload = parts[1]
                
                sender = header.split(">", 1)[0].strip()
                if ":" in payload:
                    recipient_part, msg_text = payload.split(":", 1)
                    recipient = recipient_part.strip()
                    msg_text = msg_text.strip()
                    
                    if recipient == my_callsign:
                        self.append_message(sender, msg_text)
            except:
                pass
                
    def append_message(self, sender, text):
        if not self.winfo_exists():
            return
        self.chat_area.configure(state="normal")
        timestamp = datetime.now().strftime('%H:%M:%S')
        if sender == "SYSTEM":
            self.chat_area.insert(tk.END, f"[{timestamp}] SYSTEM: {text}\n", "system")
        elif sender == "YOU":
            self.chat_area.insert(tk.END, f"[{timestamp}] YOU: {text}\n", "sent")
        else:
            self.chat_area.insert(tk.END, f"[{timestamp}] <{sender}> {text}\n", "received")
        self.chat_area.see(tk.END)
        self.chat_area.configure(state="disabled")

    def send_message_action(self):
        to_callsign = self.to_entry.get().strip().upper()
        msg_text = self.msg_entry.get().strip()
        if not to_callsign or not msg_text:
            return
        if not self.active_profile or self.active_profile not in self.profiles:
            return
        data = self.profiles[self.active_profile]
        from_callsign = data.get('callsign', '').upper()
        passcode = data.get('passcode')
        if not passcode:
            passcode = generate_aprs_passcode(from_callsign)
            
        self.send_btn.configure(state="disabled")
        
        def send_worker():
            success, res_msg = send_aprs_message(from_callsign, passcode, to_callsign, msg_text)
            if self.winfo_exists():
                self.parent.after(0, lambda: self.on_send_complete(success, to_callsign, msg_text, res_msg))
                
        threading.Thread(target=send_worker, daemon=True).start()
        
    def on_send_complete(self, success, to_callsign, msg_text, res_msg):
        self.send_btn.configure(state="normal")
        if success:
            self.append_message("YOU", f"To {to_callsign}: {msg_text}")
            self.msg_entry.delete(0, tk.END)
            self.char_lbl.configure(text="0/67")
        else:
            messagebox.showerror("Error", res_msg, parent=self)
            
    def on_close(self):
        self.stop_listener()
        self.grab_release()
        self.destroy()

# GUI Mode Implementation - Modernized Obsidian Theme
class APRSManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("APRS Multi-Beacon Control Center")
        self.root.geometry("960x680")
        self.root.configure(bg="#090a0f")
        self.root.resizable(False, False)
        
        # Color Palettes
        self.c_bg = "#f1f5f9"         # Soft slate/gray background
        self.c_card = "#ffffff"       # White card
        self.c_border = "#cbd5e1"     # Slate border
        self.c_text_main = "#0f172a"  # Slate dark charcoal main text
        self.c_text_muted = "#475569" # Slate gray muted text
        self.c_accent_cyan = "#2563eb"# Premium Royal Blue/Indigo accent
        self.c_green = "#047857"      # Dark emerald active text
        self.c_green_bg = "#d1fae5"   # Light emerald bg for active pill
        self.c_red = "#b91c1c"        # Dark red stopped text
        self.c_red_bg = "#fee2e2"     # Light red bg for stopped pill
        self.c_btn_gray = "#e2e8f0"   # Light gray button
        
        # Dictionary of references to profile card widgets to update dynamically (flicker-free)
        self.profile_cards = {}
        
        # Initialize connection status variable
        self.server_status = "Checking connection..."
        self.server_status_color = self.c_text_muted
        
        # Set styling config
        self.style = ttk.Style()
        self.style.theme_use('default')
        self.style.configure('.', background=self.c_bg, foreground=self.c_text_main)
        self.style.configure('TFrame', background=self.c_bg)
        self.style.configure('Vertical.TScrollbar', background=self.c_card, bordercolor=self.c_border, arrowcolor=self.c_text_main)
        
        # Set window icon
        self.icon_image = self.create_icon_image()
        
        # Build UI layout
        self.build_ui()
        
        # Load Profiles
        self.refresh_profiles(force_rebuild=True)
        
        # System Tray Integration
        self.tray_icon = None
        self.setup_tray()
        
        # Window minimize to tray
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
        
        # Auto-refresh and Connection status check threads
        self.running = True
        self.refresh_thread = threading.Thread(target=self.auto_refresh_loop, daemon=True)
        self.refresh_thread.start()
        self.ping_thread = threading.Thread(target=self.gateway_ping_loop, daemon=True)
        self.ping_thread.start()
        
        self.check_daily_update()

    def check_daily_update(self):
        update_flag_file = os.path.join(BASE_DIR, '.last_update_check')
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        if os.path.exists(update_flag_file):
            try:
                with open(update_flag_file, 'r', encoding='utf-8') as f:
                    last_check = f.read().strip()
                if last_check == today_str:
                    return
            except:
                pass
                
        def update_worker():
            try:
                success, msg = self_update()
                with open(update_flag_file, 'w', encoding='utf-8') as f:
                    f.write(today_str)
                if success and "already" not in msg.lower():
                    self.root.after(0, lambda: messagebox.showinfo("Auto Update", "A new update has been downloaded and installed! Please restart the application."))
            except:
                pass
                
        threading.Thread(target=update_worker, daemon=True).start()

    def create_icon_image(self):
        try:
            image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.ellipse([4, 4, 60, 60], fill=(255, 255, 255, 255), outline=(37, 99, 235, 255), width=3)
            draw.arc([16, 16, 48, 48], start=220, end=320, fill=(37, 99, 235, 255), width=3)
            draw.arc([24, 24, 40, 40], start=220, end=320, fill=(4, 120, 87, 255), width=3)
            draw.point([32, 32], fill=(4, 120, 87, 255))
            draw.ellipse([29, 32, 35, 35], fill=(244, 63, 94, 255))
            return image
        except:
            return Image.new('RGBA', (64, 64), (0, 0, 0, 0))

    def build_ui(self):
        # Top Header Frame
        header_frame = tk.Frame(self.root, bg=self.c_card, height=80, bd=0, highlightthickness=1, highlightbackground=self.c_border)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)
        
        # Title Container
        title_container = tk.Frame(header_frame, bg=self.c_card)
        title_container.pack(side="left", padx=25, pady=15)
        
        title_lbl = tk.Label(title_container, text="APRS BEACON CONTROL CENTER", font=("Helvetica", 14, "bold"), fg=self.c_text_main, bg=self.c_card)
        title_lbl.pack(anchor="w")
        
        subtitle_lbl = tk.Label(title_container, text="Real-Time Profile & Daemon Management", font=("Helvetica", 9), fg=self.c_text_muted, bg=self.c_card)
        subtitle_lbl.pack(anchor="w", pady=(2, 0))
        
        # Action Buttons Container in Header
        btn_container = tk.Frame(header_frame, bg=self.c_card)
        btn_container.pack(side="right", padx=25, pady=15)
        
        # Header Button Style config helper
        def style_header_btn(btn, color_main, color_hover, text_fg="#ffffff"):
            btn.configure(relief="flat", bd=0, highlightthickness=0, fg=text_fg, activeforeground=text_fg, font=("Helvetica", 9, "bold"), padx=12, pady=6)
            btn.bind("<Enter>", lambda e: btn.configure(bg=color_hover))
            btn.bind("<Leave>", lambda e: btn.configure(bg=color_main))
            
        # Add Profile Button
        add_btn = tk.Button(btn_container, text="+ Add Profile", bg=self.c_green, command=self.open_add_profile_dialog)
        add_btn.pack(side="left", padx=4)
        style_header_btn(add_btn, self.c_green, "#059669")
        
        # Test Server Button
        test_btn = tk.Button(btn_container, text="Test server", bg="#3b82f6", command=self.trigger_server_test)
        test_btn.pack(side="left", padx=4)
        style_header_btn(test_btn, "#3b82f6", "#2563eb")
        
        # Import settings Button
        import_btn = tk.Button(btn_container, text="Import Settings", bg=self.c_btn_gray, command=self.trigger_import)
        import_btn.pack(side="left", padx=4)
        style_header_btn(import_btn, self.c_btn_gray, "#cbd5e1", "#334155")
        
        # Export settings Button
        export_btn = tk.Button(btn_container, text="Export Settings", bg=self.c_btn_gray, command=self.trigger_export)
        export_btn.pack(side="left", padx=4)
        style_header_btn(export_btn, self.c_btn_gray, "#cbd5e1", "#334155")
        
        # Update App Button
        update_btn = tk.Button(btn_container, text="Update App", bg="#ea580c", command=self.trigger_self_update)
        update_btn.pack(side="left", padx=4)
        style_header_btn(update_btn, "#ea580c", "#c2410c")
        
        # Stats Dashboard Banner
        self.stats_frame = tk.Frame(self.root, bg=self.c_bg, height=45)
        self.stats_frame.pack(fill="x", side="top", padx=25, pady=(15, 0))
        self.stats_frame.pack_propagate(False)
        
        self.total_profiles_lbl = tk.Label(self.stats_frame, text="Profiles: 0", font=("Helvetica", 10, "bold"), fg=self.c_text_main, bg=self.c_bg)
        self.total_profiles_lbl.pack(side="left", padx=(5, 25))
        
        self.active_beacons_lbl = tk.Label(self.stats_frame, text="Active Beacons: 0", font=("Helvetica", 10, "bold"), fg=self.c_green, bg=self.c_bg)
        self.active_beacons_lbl.pack(side="left", padx=25)
        
        self.gateway_status_lbl = tk.Label(self.stats_frame, text="APRS Gateway Link: Checking...", font=("Helvetica", 10, "bold"), fg=self.c_text_muted, bg=self.c_bg)
        self.gateway_status_lbl.pack(side="left", padx=25)
        
        # Main content area frame
        self.main_container = tk.Frame(self.root, bg=self.c_bg)
        self.main_container.pack(fill="both", expand=True, padx=25, pady=(10, 20))
        
        # Welcome message (if no profiles)
        self.welcome_label = tk.Label(self.main_container, text="No APRS profiles configured.\nClick '+ Add Profile' to create one.", 
                                      font=("Helvetica", 11), fg=self.c_text_muted, bg=self.c_bg)
        
        # Scrollable Canvas container for Profiles list
        self.canvas = tk.Canvas(self.main_container, bg=self.c_bg, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.main_container, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg=self.c_bg)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )
        
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # Bind canvas resize event to automatically resize internal width
        def _on_canvas_configure(event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        self.canvas.bind('<Configure>', _on_canvas_configure)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Footer Frame
        footer_frame = tk.Frame(self.root, bg=self.c_bg)
        footer_frame.pack(side="bottom", fill="x", pady=(5, 10))
        footer_lbl = tk.Label(footer_frame, text="APRS Multi-Beacon Control Center  |  by TA1XTA", font=("Helvetica", 8), fg=self.c_text_muted, bg=self.c_bg)
        footer_lbl.pack(anchor="center")

    def refresh_profiles(self, force_rebuild=False):
        profiles = get_profiles()
        
        # Update Stats Panel
        self.total_profiles_lbl.configure(text=f"Profiles: {len(profiles)}")
        active_count = sum(1 for name in profiles.keys() if is_profile_running(name))
        self.active_beacons_lbl.configure(text=f"Active Beacons: {active_count}")
        
        # Check if the profiles set changed to decide on rebuilding
        current_names = set(profiles.keys())
        existing_names = set(self.profile_cards.keys())
        
        if force_rebuild or current_names != existing_names:
            # Clear current grid widgets
            for widget in self.scrollable_frame.winfo_children():
                widget.destroy()
            self.profile_cards.clear()
            
            if not profiles:
                self.welcome_label.pack(pady=100)
                self.canvas.pack_forget()
                self.scrollbar.pack_forget()
                return
            else:
                self.welcome_label.pack_forget()
                self.canvas.pack(side="left", fill="both", expand=True)
                self.scrollbar.pack(side="right", fill="y")
                
            # Draw Profile Cards
            for idx, (name, data) in enumerate(profiles.items()):
                self.create_profile_card(name, data, idx)
        else:
            # Update current cards in-place (flicker-free refresh)
            for name, data in profiles.items():
                if name in self.profile_cards:
                    card_data = self.profile_cards[name]
                    running = is_profile_running(name)
                    
                    status_color = self.c_green if running else self.c_red
                    status_bg = self.c_green_bg if running else self.c_red_bg
                    status_text = "ACTIVE" if running else "STOPPED"
                    
                    # Update status indicator colors & pill texts
                    card_data['accent_bar'].configure(bg=status_color)
                    card_data['pill_frame'].configure(bg=status_bg)
                    card_data['pill_lbl'].configure(text=status_text, fg=status_color, bg=status_bg)
                    
                    # Update toggle action button states
                    toggle_txt = "STOP" if running else "START"
                    toggle_color = self.c_red if running else self.c_green
                    toggle_hover = "#be123c" if running else "#047857"
                    
                    card_data['toggle_btn'].configure(text=toggle_txt, bg=toggle_color)
                    card_data['toggle_btn'].configure(command=lambda n=name, r=running: self.toggle_profile(n, r))
                    
                    btn = card_data['toggle_btn']
                    btn.bind("<Enter>", lambda e, b=btn, h=toggle_hover: b.configure(bg=h))
                    btn.bind("<Leave>", lambda e, b=btn, c=toggle_color: b.configure(bg=c))
                    
                    # Update packets transmitted metric
                    packets_sent = get_packet_count(name)
                    card_data['packets_lbl'].configure(
                        text=f"Packets Sent: {packets_sent}",
                        fg=self.c_green if packets_sent > 0 else self.c_text_muted
                    )
                    
                    # Update autostart checkbox
                    card_data['autostart_var'].set(is_service_enabled(name))

    def create_profile_card(self, name, data, idx):
        running = is_profile_running(name)
        status_color = self.c_green if running else self.c_red
        status_bg = self.c_green_bg if running else self.c_red_bg
        status_text = "ACTIVE" if running else "STOPPED"
        
        # Card Main Frame
        card = tk.Frame(self.scrollable_frame, bg=self.c_card, bd=0, highlightthickness=1, highlightbackground=self.c_border, padx=18, pady=15)
        card.pack(fill="x", pady=8, padx=5)
        
        # 1. Left Accent Status Indicator Bar
        accent_bar = tk.Frame(card, bg=status_color, width=5)
        accent_bar.pack(side="left", fill="y", padx=(0, 15))
        
        # 2. Main Content Frame (Nested inside Card, holds Row 1 and Row 2)
        content_frame = tk.Frame(card, bg=self.c_card)
        content_frame.pack(side="left", fill="both", expand=True)
        
        # --- Row 1: Profile Details Grid ---
        row1 = tk.Frame(content_frame, bg=self.c_card)
        row1.pack(side="top", fill="x")
        
        # Left Block: Name & Status Pill
        info_block = tk.Frame(row1, bg=self.c_card)
        info_block.pack(side="left", anchor="nw")
        
        name_lbl = tk.Label(info_block, text=name.upper(), font=("Helvetica", 12, "bold"), fg=self.c_accent_cyan, bg=self.c_card)
        name_lbl.pack(anchor="w")
        
        call_lbl = tk.Label(info_block, text=data.get('callsign', 'N0CALL'), font=("Helvetica", 10, "bold"), fg=self.c_text_main, bg=self.c_card)
        call_lbl.pack(anchor="w", pady=(1, 3))
        
        pill_frame = tk.Frame(info_block, bg=status_bg, padx=8, pady=2)
        pill_frame.pack(anchor="w")
        
        pill_lbl = tk.Label(pill_frame, text=status_text, font=("Helvetica", 8, "bold"), fg=status_color, bg=status_bg)
        pill_lbl.pack()
        
        # Right Block: Grid parameters
        details_block = tk.Frame(row1, bg=self.c_card)
        details_block.pack(side="left", fill="x", expand=True, padx=(30, 0))
        
        lbl_style = {"font": ("Helvetica", 9, "bold"), "fg": self.c_text_muted, "bg": self.c_card}
        val_style = {"font": ("Helvetica", 9), "fg": self.c_text_main, "bg": self.c_card}
        
        comment_val = data.get('comment', 'APRS Background Beacon')
        if len(comment_val) > 42:
            comment_val = comment_val[:39] + "..."
            
        tk.Label(details_block, text="Interval:", **lbl_style).grid(row=0, column=0, sticky="w", pady=1)
        tk.Label(details_block, text=f"{data.get('interval_minutes')} minutes", **val_style).grid(row=0, column=1, sticky="w", padx=10, pady=1)
        
        tk.Label(details_block, text="Location:", **lbl_style).grid(row=1, column=0, sticky="w", pady=1)
        location_val_lbl = tk.Label(details_block, text=f"{data.get('latitude')}, {data.get('longitude')} ({data.get('symbol_code', 'X')})", **val_style)
        location_val_lbl.grid(row=1, column=1, sticky="w", padx=10, pady=1)
        
        tk.Label(details_block, text="Comment:", **lbl_style).grid(row=2, column=0, sticky="w", pady=1)
        tk.Label(details_block, text=comment_val, **val_style).grid(row=2, column=1, sticky="w", padx=10, pady=1)
        
        # --- Row 2: Metrics & Actions (Prevents Horizontal Button Overflow) ---
        row2 = tk.Frame(content_frame, bg=self.c_card)
        row2.pack(side="top", fill="x", pady=(12, 0))
        
        # Metrics block (left align)
        metrics_block = tk.Frame(row2, bg=self.c_card)
        metrics_block.pack(side="left", fill="y", anchor="center")
        
        packets_sent = get_packet_count(name)
        packets_lbl = tk.Label(metrics_block, text=f"Packets Sent: {packets_sent}", font=("Helvetica", 9, "bold"), fg=self.c_green if packets_sent > 0 else self.c_text_muted, bg=self.c_card)
        packets_lbl.pack(side="left", padx=(0, 20))
        
        # Autostart checkbox
        autostart_var = tk.BooleanVar(value=is_service_enabled(name))
        autostart_cb = tk.Checkbutton(metrics_block, text="Start on Boot", variable=autostart_var, 
                                     font=("Helvetica", 9), fg=self.c_text_main, bg=self.c_card, 
                                     activebackground=self.c_card, activeforeground=self.c_text_main, 
                                     selectcolor=self.c_bg, command=lambda n=name, v=autostart_var: set_service_enabled(n, v.get()))
        autostart_cb.pack(side="left")
        
        # Actions block (right align)
        actions_block = tk.Frame(row2, bg=self.c_card)
        actions_block.pack(side="right", fill="y")
        
        toggle_txt = "STOP" if running else "START"
        toggle_color = self.c_red if running else self.c_green
        toggle_hover = "#be123c" if running else "#047857"
        
        # Action Button layout helper
        def style_action_btn(btn, color_main, color_hover, text_fg="#ffffff"):
            btn.configure(relief="flat", bd=0, highlightthickness=0, fg=text_fg, font=("Helvetica", 8, "bold"), width=8, pady=4)
            btn.bind("<Enter>", lambda e: btn.configure(bg=color_hover))
            btn.bind("<Leave>", lambda e: btn.configure(bg=color_main))
            
        toggle_btn = tk.Button(actions_block, text=toggle_txt, bg=toggle_color, command=lambda n=name, r=running: self.toggle_profile(n, r))
        toggle_btn.pack(side="left", padx=2)
        style_action_btn(toggle_btn, toggle_color, toggle_hover, text_fg="#ffffff")
        
        log_btn = tk.Button(actions_block, text="Logs", bg=self.c_btn_gray, command=lambda n=name: self.open_log_viewer(n))
        log_btn.pack(side="left", padx=2)
        style_action_btn(log_btn, self.c_btn_gray, "#475569")
        
        # APRS Messenger button
        chat_btn = tk.Button(actions_block, text="Chat", bg="#8b5cf6", command=lambda n=name: self.open_chat_window(n))
        chat_btn.pack(side="left", padx=2)
        style_action_btn(chat_btn, "#8b5cf6", "#7c3aed")
        
        map_btn = tk.Button(actions_block, text="Map", bg="#1e3a8a", command=lambda c=data.get('callsign'): self.open_map_link(c))
        map_btn.pack(side="left", padx=2)
        style_action_btn(map_btn, "#1e3a8a", "#1d4ed8")
        
        edit_btn = tk.Button(actions_block, text="Edit", bg="#4f46e5", command=lambda n=name: self.open_add_profile_dialog(n))
        edit_btn.pack(side="left", padx=2)
        style_action_btn(edit_btn, "#4f46e5", "#4338ca")
        
        del_btn = tk.Button(actions_block, text="Delete", bg="#7c2d12", command=lambda n=name: self.delete_profile(n))
        del_btn.pack(side="left", padx=2)
        style_action_btn(del_btn, "#7c2d12", "#9a3412")
        
        # Save references for dynamic updating
        self.profile_cards[name] = {
            'card': card,
            'accent_bar': accent_bar,
            'pill_frame': pill_frame,
            'pill_lbl': pill_lbl,
            'location_val_lbl': location_val_lbl,
            'toggle_btn': toggle_btn,
            'packets_lbl': packets_lbl,
            'autostart_var': autostart_var
        }

    def toggle_profile(self, name, currently_running):
        if currently_running:
            stop_profile_service(name)
        else:
            start_profile_service(name)
        time.sleep(0.5)
        self.refresh_profiles()
        self.update_tray_menu()

    def open_map_link(self, callsign):
        if callsign:
            webbrowser.open(f"https://aprs.fi/#!call=a%2F{callsign}")

    def trigger_server_test(self):
        def test_runner():
            start_time = time.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3.0)
                sock.connect(("rotate.aprs2.net", 14580))
                sock.close()
                latency = int((time.time() - start_time) * 1000)
                messagebox.showinfo("Connection Test Passed", f"APRS-IS server (rotate.aprs2.net:14580) is online.\nLatency: {latency}ms")
            except Exception as e:
                messagebox.showerror("Connection Test Failed", f"Could not connect to APRS-IS server:\n{e}")
        threading.Thread(target=test_runner, daemon=True).start()

    def delete_profile(self, name):
        if not gui_require_auth(self.root):
            return
        if messagebox.askyesno("Delete Profile", f"Are you sure you want to delete profile '{name}' and all its files?"):
            delete_profile_files(name)
            self.refresh_profiles(force_rebuild=True)
            self.update_tray_menu()

    def open_log_viewer(self, name):
        log_win = tk.Toplevel(self.root)
        log_win.title(f"{name.upper()} - Live Log Monitor")
        log_win.geometry("760x520")
        log_win.configure(bg=self.c_bg)
        
        header_lbl = tk.Label(log_win, text=f"{name.upper()} Profile Log Output", font=("Helvetica", 11, "bold"), fg=self.c_accent_cyan, bg=self.c_bg)
        header_lbl.pack(pady=(15, 5))
        
        info_lbl = tk.Label(log_win, text="Real-time console updates (last 100 entries).", font=("Helvetica", 9), fg=self.c_text_muted, bg=self.c_bg)
        info_lbl.pack(pady=(0, 10))
        
        txt_area = tk.Text(log_win, bg="#ffffff", fg=self.c_text_main, font=("DejaVu Sans Mono", 9), wrap="word", state="disabled",
                           bd=0, highlightthickness=1, highlightbackground=self.c_border)
        txt_area.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        log_file = os.path.join(LOGS_DIR, f"{name}.log")
        
        def update_logs():
            if not log_win.winfo_exists():
                return
            lines = []
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()[-100:]
                except Exception as e:
                    lines = [f"Log file read error: {e}"]
            else:
                lines = ["No log records found yet. Log output will appear once the beacon sends packets."]
            txt_area.configure(state="normal")
            txt_area.delete("1.0", tk.END)
            txt_area.insert(tk.END, "".join(lines))
            txt_area.see(tk.END)
            txt_area.configure(state="disabled")
            log_win.after(2000, update_logs)
            
        update_logs()

    def open_chat_window(self, default_profile_name=None):
        APRSChatWindow(self.root, default_profile_name)

    def open_add_profile_dialog(self, edit_profile_name=None):
        if not edit_profile_name and not IS_BYPASS and len(get_profiles()) >= 2:
            messagebox.showerror("Limit Exceeded", "You can add at most 2 profiles. Elevation required for more.")
            return
        if not gui_require_auth(self.root):
            return

        form = tk.Toplevel(self.root)
        form.title("Add Profile" if not edit_profile_name else f"Edit Profile: {edit_profile_name}")
        form.geometry("540x510")
        form.configure(bg=self.c_bg)
        form.resizable(False, False)
        form.transient(self.root)
        form.grab_set()
        
        title_lbl_text = "APRS Beacon Settings" if not edit_profile_name else "Edit APRS Configuration"
        title = tk.Label(form, text=title_lbl_text, font=("Helvetica", 13, "bold"), fg=self.c_accent_cyan, bg=self.c_bg)
        title.pack(pady=(20, 15))
        
        fields_frame = tk.Frame(form, bg=self.c_bg)
        fields_frame.pack(fill="both", expand=True, padx=25)
        
        fields_config = [
            ("Profile Name (Single word)", "name", 0, 0),
            ("Callsign (with SSID)", "callsign", 0, 1),
            ("APRS-IS Passcode (Auto-calculated if empty)", "passcode", 1, 0),
            ("Interval (Minutes)", "interval", 1, 1),
            ("Latitude (e.g. 41.032633)", "latitude", 2, 0),
            ("Longitude (e.g. 28.987083)", "longitude", 2, 1),
            ("Symbol (e.g. >, X, [)", "symbol", 3, 0),
        ]
        
        entries = {}
        for label_txt, name, row, col in fields_config:
            cell_frame = tk.Frame(fields_frame, bg=self.c_bg)
            cell_frame.grid(row=row, column=col, sticky="ew", padx=10, pady=8)
            
            lbl = tk.Label(cell_frame, text=label_txt, font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_bg)
            lbl.pack(anchor="w", pady=(0, 3))
            
            ent = tk.Entry(cell_frame, bg=self.c_card, fg=self.c_text_main, insertbackground=self.c_text_main, 
                           bd=0, highlightthickness=1, highlightbackground=self.c_border, font=("Helvetica", 10),
                           relief="flat")
            ent.pack(fill="x", ipady=4)
            
            # Add subtle focus highlight effect
            def on_focus_in(e, entry=ent):
                entry.configure(highlightbackground=self.c_accent_cyan)
            def on_focus_out(e, entry=ent):
                entry.configure(highlightbackground=self.c_border)
            ent.bind("<FocusIn>", on_focus_in)
            ent.bind("<FocusOut>", on_focus_out)
            
            entries[name] = ent
            
        fields_frame.columnconfigure(0, weight=1)
        fields_frame.columnconfigure(1, weight=1)
        
        # Comment field: spans column 1 at row 3
        comment_frame = tk.Frame(fields_frame, bg=self.c_bg)
        comment_frame.grid(row=3, column=1, sticky="ew", padx=10, pady=8)
        
        comment_lbl = tk.Label(comment_frame, text="Status Comment", font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_bg)
        comment_lbl.pack(anchor="w", pady=(0, 3))
        
        comment_ent = tk.Entry(comment_frame, bg=self.c_card, fg=self.c_text_main, insertbackground=self.c_text_main, 
                               bd=0, highlightthickness=1, highlightbackground=self.c_border, font=("Helvetica", 10),
                               relief="flat")
        comment_ent.pack(fill="x", ipady=4)
        comment_ent.bind("<FocusIn>", lambda e: comment_ent.configure(highlightbackground=self.c_accent_cyan))
        comment_ent.bind("<FocusOut>", lambda e: comment_ent.configure(highlightbackground=self.c_border))
        entries['comment'] = comment_ent

        # APRS Thursday & Time Frame: spans full width
        thurs_frame = tk.Frame(fields_frame, bg=self.c_card, padx=12, pady=10, highlightthickness=1, highlightbackground=self.c_border)
        thurs_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=15)
        
        # Row 1 of thurs_frame: Checkbutton and Time
        thurs_row1 = tk.Frame(thurs_frame, bg=self.c_card)
        thurs_row1.pack(fill="x")
        
        thursday_var = tk.BooleanVar(value=False)
        thursday_cb = tk.Checkbutton(thurs_row1, text="Join APRS Thursday Event (ANSRVR)", variable=thursday_var, 
                                     font=("Helvetica", 9, "bold"), fg=self.c_text_main, bg=self.c_card, activebackground=self.c_card, 
                                     activeforeground=self.c_text_main, selectcolor=self.c_bg)
        thursday_cb.pack(side="left")
        
        time_ent = tk.Entry(thurs_row1, bg=self.c_bg, fg=self.c_text_main, insertbackground=self.c_text_main, 
                            bd=0, highlightthickness=1, highlightbackground=self.c_border, width=6, font=("Helvetica", 10))
        time_ent.pack(side="right", padx=(5, 0))
        time_ent.insert(0, "20:00")
        
        time_lbl = tk.Label(thurs_row1, text="Time (HH:MM):", font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_card)
        time_lbl.pack(side="right")
        
        # Row 2 of thurs_frame: Custom Message
        thurs_row2 = tk.Frame(thurs_frame, bg=self.c_card)
        thurs_row2.pack(fill="x", pady=(8, 0))
        
        msg_lbl = tk.Label(thurs_row2, text="Thursday Message:", font=("Helvetica", 9, "bold"), fg=self.c_text_muted, bg=self.c_card)
        msg_lbl.pack(side="left")
        
        thurs_msg_ent = tk.Entry(thurs_row2, bg=self.c_bg, fg=self.c_text_main, insertbackground=self.c_text_main, 
                                 bd=0, highlightthickness=1, highlightbackground=self.c_border, font=("Helvetica", 10))
        thurs_msg_ent.pack(side="left", fill="x", expand=True, padx=(10, 0))
        thurs_msg_ent.insert(0, "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY")
        thurs_msg_ent.bind("<FocusIn>", lambda e: thurs_msg_ent.configure(highlightbackground=self.c_accent_cyan))
        thurs_msg_ent.bind("<FocusOut>", lambda e: thurs_msg_ent.configure(highlightbackground=self.c_border))
        
        # Populate Default / Edit values
        if edit_profile_name:
            profiles = get_profiles()
            data = profiles[edit_profile_name]
            entries['name'].insert(0, edit_profile_name)
            entries['name'].configure(state='disabled')
            entries['callsign'].insert(0, data.get('callsign', ''))
            entries['passcode'].insert(0, str(data.get('passcode', '')))
            entries['latitude'].insert(0, str(data.get('latitude', '')))
            entries['longitude'].insert(0, str(data.get('longitude', '')))
            entries['comment'].insert(0, data.get('comment', ''))
            entries['symbol'].insert(0, data.get('symbol_code', 'X'))
            entries['interval'].insert(0, str(data.get('interval_minutes', '5')))
            thursday_var.set(data.get('aprs_thursday', False))
            time_ent.delete(0, tk.END)
            time_ent.insert(0, data.get('aprs_thursday_time', '20:00'))
            thurs_msg_ent.delete(0, tk.END)
            thurs_msg_ent.insert(0, data.get('aprs_thursday_msg', 'CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY'))
        else:
            entries['comment'].insert(0, "APRS Background Beacon")
            entries['symbol'].insert(0, "X")
            entries['interval'].insert(0, "5")
            thurs_msg_ent.delete(0, tk.END)
            thurs_msg_ent.insert(0, "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY")
        
        def save_new():
            name = edit_profile_name if edit_profile_name else entries['name'].get().strip().lower()
            callsign = entries['callsign'].get().strip().upper()
            passcode_in = entries['passcode'].get().strip()
            lat_in = entries['latitude'].get().strip()
            lon_in = entries['longitude'].get().strip()
            comment = entries['comment'].get().strip()
            symbol = entries['symbol'].get().strip()
            interval_in = entries['interval'].get().strip()
            aprs_thursday_time = time_ent.get().strip() or "20:00"
            aprs_thursday_msg = thurs_msg_ent.get().strip() or "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY"
            
            if not name or not callsign or not lat_in or not lon_in:
                messagebox.showerror("Error", "All configuration parameters (Name, Callsign, Coordinates) are required.", parent=form)
                return
            if not edit_profile_name:
                profiles = get_profiles()
                if name in profiles:
                    messagebox.showerror("Error", f"Profile '{name}' already exists.", parent=form)
                    return
            try:
                lat = float(lat_in)
                lon = float(lon_in)
            except ValueError:
                messagebox.showerror("Error", "Coordinates must be numerical coordinate values.", parent=form)
                return
            if not passcode_in:
                passcode = generate_aprs_passcode(callsign)
            else:
                try:
                    passcode = int(passcode_in)
                except ValueError:
                    messagebox.showerror("Error", "Invalid passcode entry.", parent=form)
                    return
            try:
                interval = int(interval_in)
            except ValueError:
                interval = 5
                
            data = {
                "callsign": callsign,
                "passcode": passcode,
                "latitude": lat,
                "longitude": lon,
                "use_termux_gps": False,
                "symbol_table": "/",
                "symbol_code": symbol if symbol else "X",
                "comment": comment if comment else "APRS Background Beacon",
                "interval_minutes": interval,
                "aprs_thursday": thursday_var.get(),
                "aprs_thursday_time": aprs_thursday_time,
                "aprs_thursday_msg": aprs_thursday_msg,
                "server": "rotate.aprs2.net",
                "port": 14580
            }
            save_profile(name, data)
            form.destroy()
            self.refresh_profiles(force_rebuild=True)
            self.update_tray_menu()
            
            if edit_profile_name:
                if is_profile_running(name):
                    stop_profile_service(name)
                    time.sleep(0.5)
                    start_profile_service(name)
                    self.refresh_profiles(force_rebuild=True)
                    self.update_tray_menu()
                messagebox.showinfo("Success", f"Profile '{name}' updated successfully.")
            else:
                if messagebox.askyesno("Start Service", f"Profile '{name}' configured. Run background daemon now?"):
                    start_profile_service(name)
                    self.refresh_profiles(force_rebuild=True)
                    self.update_tray_menu()
                    
        save_btn = tk.Button(form, text="Save Settings", bg=self.c_green, command=save_new)
        save_btn.pack(pady=(0, 20), side="bottom", fill="x", padx=35)
        save_btn.configure(relief="flat", bd=0, highlightthickness=0, fg="#ffffff", activeforeground="#ffffff", font=("Helvetica", 10, "bold"), pady=8)
        save_btn.bind("<Enter>", lambda e: save_btn.configure(bg="#059669"))
        save_btn.bind("<Leave>", lambda e: save_btn.configure(bg=self.c_green))

    # System Tray Integration
    def setup_tray(self):
        self.update_tray_menu()

    def update_tray_menu(self):
        if not GUI_AVAILABLE:
            return
        profiles = get_profiles()
        menu_items = [
            pystray.MenuItem("Show Panel", self.restore_from_tray, default=True),
            pystray.Menu.SEPARATOR
        ]
        if profiles:
            def toggle_wrapper(name, running):
                return lambda: self.root.after(0, lambda: self.toggle_profile(name, running))
            for name in profiles.keys():
                running = is_profile_running(name)
                icon_prefix = "RUN - " if running else "STOP - "
                toggle_txt = f"{icon_prefix}{name.upper()}"
                menu_items.append(pystray.MenuItem(toggle_txt, toggle_wrapper(name, running)))
            menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Start All", self.start_all_profiles))
        menu_items.append(pystray.MenuItem("Stop All", self.stop_all_profiles))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Exit", self.quit_application))
        
        menu = pystray.Menu(*menu_items)
        if self.tray_icon:
            self.tray_icon.menu = menu
        else:
            self.tray_icon = pystray.Icon("aprs_manager", self.icon_image, "APRS Manager", menu)
            tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            tray_thread.start()

    def start_all_profiles(self):
        profiles = get_profiles()
        for name in profiles.keys():
            start_profile_service(name)
        time.sleep(0.5)
        self.root.after(0, lambda: self.refresh_profiles(force_rebuild=False))
        self.root.after(0, self.update_tray_menu)

    def stop_all_profiles(self):
        profiles = get_profiles()
        for name in profiles.keys():
            stop_profile_service(name)
        time.sleep(0.5)
        self.root.after(0, lambda: self.refresh_profiles(force_rebuild=False))
        self.root.after(0, self.update_tray_menu)

    def minimize_to_tray(self):
        self.root.withdraw()
        if self.tray_icon:
            self.tray_icon.notify("APRS Manager minimised. Daemon processes remain running in the background.", "Running in Background")

    def restore_from_tray(self):
        self.root.after(0, self.root.deiconify)
        self.root.after(0, self.root.focus_force)

    def quit_application(self):
        self.running = False
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        sys.exit(0)

    def auto_refresh_loop(self):
        while self.running:
            time.sleep(10)
            if self.running and self.root.winfo_exists():
                try:
                    self.root.after(0, lambda: self.refresh_profiles(force_rebuild=False))
                except:
                    pass

    def gateway_ping_loop(self):
        while self.running:
            start_time = time.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2.0)
                sock.connect(("rotate.aprs2.net", 14580))
                sock.close()
                latency = int((time.time() - start_time) * 1000)
                self.server_status = f"Gateway Status: Online ({latency}ms)"
                self.server_status_color = self.c_green
            except:
                self.server_status = "Gateway Status: Offline"
                self.server_status_color = self.c_red
                
            if self.running and self.root.winfo_exists():
                try:
                    self.root.after(0, self.update_server_status_ui)
                except:
                    pass
            # Update connection every 20 seconds
            for _ in range(20):
                if not self.running:
                    break
                time.sleep(1)

    def update_server_status_ui(self):
        self.gateway_status_lbl.configure(text=self.server_status, fg=self.server_status_color)

    def trigger_self_update(self):
        if not gui_require_auth(self.root):
            return
        if messagebox.askyesno("Update App", "Would you like to fetch updates and update the software from GitHub?"):
            success, msg = self_update()
            if success:
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Error", msg)

    def trigger_export(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Backup Files", "*.json")],
            title="Export Backup Settings",
            initialfile=f"aprs_config_backup_{datetime.now().strftime('%Y%m%d')}.json"
        )
        if file_path:
            success, msg = export_settings(file_path)
            if success:
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Error", msg)

    def trigger_import(self):
        if not gui_require_auth(self.root):
            return
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Backup Files", "*.json")],
            title="Import Settings Backup"
        )
        if file_path:
            success, msg = import_settings(file_path)
            if success:
                messagebox.showinfo("Success", msg)
                self.refresh_profiles(force_rebuild=True)
                self.update_tray_menu()
            else:
                messagebox.showerror("Error", msg)

# CLI Interactive Mode & Helper
def cli_show_logs_interactive(profile_name):
    profiles = get_profiles()
    if profile_name not in profiles:
        print(f"Error: Profile '{profile_name}' not found.")
        return
    log_path = os.path.join(LOGS_DIR, f"{profile_name}.log")
    if not os.path.exists(log_path):
        print("Log file not found. Daemon has not generated log events yet.")
        return
    print(f"\n--- {profile_name.upper()} LIVE LOG OUTPUT (Ctrl+C to stop) ---")
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(line, end='')
            while True:
                line = f.readline()
                if not line:
                    time.sleep(1)
                    continue
                print(line, end='')
    except KeyboardInterrupt:
        print("\nClosed live log monitor.")

def cli_interactive_menu():
    while True:
        print("\n=== APRS Multi-Beacon Manager (CLI) ===")
        print("1) List Profiles")
        print("2) Create New Profile")
        print("3) Start Profile Daemon")
        print("4) Stop Profile Daemon")
        print("5) Delete Profile")
        print("6) Live Log Monitor")
        print("7) Edit Profile Settings")
        print("8) Export Settings Backup")
        print("9) Import Settings Backup")
        print("10) Fetch Updates")
        print("11) Exit")
        print("-" * 45)
        
        choice = input("Choice [1-11]: ").strip()
        if choice == '1':
            cli_list()
        elif choice == '2':
            cli_create()
        elif choice == '3':
            name = input("Profile name to start: ").strip().lower()
            if name:
                cli_start(name)
        elif choice == '4':
            name = input("Profile name to stop: ").strip().lower()
            if name:
                cli_stop(name)
        elif choice == '5':
            name = input("Profile name to delete: ").strip().lower()
            if name:
                cli_delete(name)
        elif choice == '6':
            name = input("Profile name to view: ").strip().lower()
            if name:
                cli_show_logs_interactive(name)
        elif choice == '7':
            cli_edit()
        elif choice == '8':
            export_path = input("Export location [Default: ~/aprs_backup.json]: ").strip()
            if not export_path:
                export_path = os.path.expanduser("~/aprs_backup.json")
            success, msg = export_settings(export_path)
            print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '9':
            if not cli_require_auth():
                continue
            import_path = input("Import file location: ").strip()
            if import_path:
                success, msg = import_settings(import_path)
                print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '10':
            if not cli_require_auth():
                continue
            print("[i] Checking updates...")
            success, msg = self_update()
            print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '11' or choice.lower() == 'exit':
            print("Exiting...")
            break
        else:
            print("Invalid choice! Enter a selection option from 1 to 11.")

# Entry Point / Argument Parsing
def main():
    parser = argparse.ArgumentParser(description="APRS Multi-Beacon Management Utility")
    parser.add_argument('command', nargs='?', choices=['list', 'start', 'stop', 'create', 'delete', 'edit', 'export', 'import', 'update', 'gui'], default='gui',
                        help="Command to run (list, start, stop, create, delete, edit, export, import, update, gui)")
    parser.add_argument('profile_name', nargs='?', help="Target profile name or file path for commands")
    args = parser.parse_args()
    
    if args.command == 'list':
        cli_list()
    elif args.command == 'create':
        cli_create()
    elif args.command == 'edit':
        cli_edit()
    elif args.command == 'update':
        if not cli_require_auth():
            return
        print("[i] Checking updates...")
        success, msg = self_update()
        print(f"[+] {msg}" if success else f"[-] {msg}")
    elif args.command == 'export':
        path = args.profile_name
        if not path:
            path = os.path.expanduser("~/aprs_backup.json")
        success, msg = export_settings(path)
        print(f"[+] {msg}" if success else f"[-] {msg}")
    elif args.command == 'import':
        if not cli_require_auth():
            return
        path = args.profile_name
        if not path:
            print("Error: Specify backup file directory path (e.g. aprs_manager import backup.json)")
        else:
            success, msg = import_settings(path)
            print(f"[+] {msg}" if success else f"[-] {msg}")
    elif args.command == 'delete':
        if not args.profile_name:
            print("Error: Specify profile name to delete (e.g. aprs_manager delete my_profile)")
        else:
            cli_delete(args.profile_name)
    elif args.command == 'start':
        if not args.profile_name:
            print("Error: Specify profile name to start.")
        else:
            cli_start(args.profile_name)
    elif args.command == 'stop':
        if not args.profile_name:
            print("Error: Specify profile name to stop.")
        else:
            cli_stop(args.profile_name)
    elif args.command == 'gui':
        is_headless = False
        if IS_LINUX and 'DISPLAY' not in os.environ:
            is_headless = True
            
        if not GUI_AVAILABLE or is_headless:
            if is_headless:
                print("\033[93m[!] X-server connection (DISPLAY) not detected. Defaulting to terminal mode.\033[0m")
            else:
                print("\033[91mError: GUI libraries (tkinter, pystray, pillow) not fully installed.\033[0m")
            print("Launching terminal interactive interface...\n")
            time.sleep(1)
            cli_interactive_menu()
            sys.exit(0)
            
        try:
            root = tk.Tk()
            app = APRSManagerGUI(root)
            root.mainloop()
        except Exception as e:
            print(f"\033[91mCould not launch graphical window: {e}\033[0m")
            print("Launching terminal interactive interface...\n")
            time.sleep(1)
            cli_interactive_menu()

if __name__ == '__main__':
    main()
