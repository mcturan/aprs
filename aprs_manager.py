#!/usr/bin/env python3
import os
import sys
import json
import socket
import argparse
import subprocess
import threading
import time
from datetime import datetime

# Base Directory Configurations
BASE_DIR = os.path.expanduser('~/.aprs-beacon')
PROFILES_DIR = os.path.join(BASE_DIR, 'profiles')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Detect OS/Environment
IS_ANDROID = os.path.exists('/data/data/com.termux') or 'TERMUX_VERSION' in os.environ
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = not IS_ANDROID and (sys.platform.startswith('linux') or sys.platform.startswith('freebsd'))

# Check GUI Libraries
GUI_AVAILABLE = True
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, simpledialog
    from PIL import Image, ImageDraw
    import pystray
except ImportError:
    GUI_AVAILABLE = False

# --- Passcode Generator ---
def generate_aprs_passcode(callsign):
    callsign = callsign.upper().split('-')[0]
    hash_val = 0x73e2
    for i in range(0, len(callsign), 2):
        char1 = ord(callsign[i]) << 8
        char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
        hash_val ^= (char1 + char2)
    return hash_val & 0x7fff

# --- Platform Dependent Service Operations ---
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
        print(f"Systemd şablon servisi oluşturulamadı: {e}", file=sys.stderr)

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

def start_profile_service(profile_name):
    if IS_LINUX:
        ensure_linux_systemd_template()
        subprocess.run(['systemctl', '--user', 'enable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['systemctl', '--user', 'start', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif IS_WINDOWS:
        # Register task if not exists
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
        
        # Add to boot scripts
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
        subprocess.run(['systemctl', '--user', 'disable', f'aprs-beacon@{profile_name}.service'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

# --- Profile Management Helpers ---
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

# --- CLI Mode Implementation ---
def cli_list():
    profiles = get_profiles()
    if not profiles:
        print("Kayıtlı herhangi bir APRS profili bulunamadı.")
        return
    
    print("\n=== APRS Beacon Profilleri ===")
    print(f"{'Profil Adı':<15} | {'Çağrı İşareti':<12} | {'Sıklık (Dk)':<12} | {'Durum':<10}")
    print("-" * 60)
    for name, data in profiles.items():
        running = is_profile_running(name)
        status_str = "\033[92mAktif\033[0m" if running else "\033[91mKapalı\033[0m"
        print(f"{name:<15} | {data.get('callsign', 'N0CALL'):<12} | {data.get('interval_minutes', 5):<12} | {status_str:<10}")
    print()

def cli_create():
    print("\n=== Yeni APRS Profili Oluştur ===")
    name = input("Profil Adı (Tek kelime, örn: mobil): ").strip().lower()
    if not name:
        print("Hata: Profil adı boş olamaz.")
        return
    
    profiles = get_profiles()
    if name in profiles:
        print(f"Hata: '{name}' adında bir profil zaten mevcut.")
        return
        
    callsign = input("Çağrı İşareti (Örn: TA2XYZ-9): ").strip().upper()
    if not callsign:
        print("Hata: Çağrı işareti boş olamaz.")
        return
        
    passcode_input = input("APRS-IS Passcode [Hesaplamak için Enter]: ").strip()
    if not passcode_input:
        passcode = generate_aprs_passcode(callsign)
        print(f"Otomatik hesaplanan şifre: {passcode}")
    else:
        try:
            passcode = int(passcode_input)
        except:
            print("Hata: Geçersiz şifre formatı.")
            return
            
    try:
        lat = float(input("Enlem (Latitude, Örn: 41.037): ").strip())
        lon = float(input("Boylam (Longitude, Örn: 28.985): ").strip())
    except ValueError:
        print("Hata: Koordinatlar sayı olmalıdır.")
        return
        
    comment = input("Durum Mesajı [Varsayılan: APRS Background Beacon]: ").strip()
    if not comment:
        comment = "APRS Background Beacon"
        
    symbol_code = input("Simge Karakteri [Varsayılan: X (Helikopter)]: ").strip()
    if not symbol_code:
        symbol_code = "X"
        
    try:
        interval = int(input("Gönderim Sıklığı (Dakika) [Varsayılan: 5]: ").strip() or 5)
    except ValueError:
        interval = 5

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
        "server": "rotate.aprs2.net",
        "port": 14580
    }
    
    save_profile(name, data)
    print(f"\n[+] Profil başarıyla oluşturuldu: {name}")
    
    run_now = input("Hemen başlatılsın mı? [Y/n]: ").strip().lower()
    if run_now != 'n':
        start_profile_service(name)
        print(f"[+] '{name}' profili arka planda başlatıldı.")

def cli_delete(name):
    profiles = get_profiles()
    if name not in profiles:
        print(f"Hata: '{name}' adında bir profil bulunamadı.")
        return
    delete_profile_files(name)
    print(f"[+] '{name}' profili başarıyla silindi.")

def cli_start(name):
    profiles = get_profiles()
    if name not in profiles:
        print(f"Hata: '{name}' adında bir profil bulunamadı.")
        return
    start_profile_service(name)
    print(f"[+] '{name}' profili başlatıldı.")

def cli_stop(name):
    profiles = get_profiles()
    if name not in profiles:
        print(f"Hata: '{name}' adında bir profil bulunamadı.")
        return
    stop_profile_service(name)
    print(f"[+] '{name}' profili durduruldu.")

# --- GUI Mode Implementation ---
class APRSManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("📻 APRS Beacon Yönetim Paneli")
        self.root.geometry("800x600")
        self.root.configure(bg="#1e1e2e")
        
        # Style configurations
        self.style = ttk.Style()
        self.style.theme_use('default')
        self.style.configure('.', background='#1e1e2e', foreground='#cdd6f4')
        self.style.configure('TFrame', background='#1e1e2e')
        self.style.configure('Card.TFrame', background='#252538', relief='flat')
        
        # Set window icon if possible
        self.icon_image = self.create_icon_image()
        
        # Build UI layout
        self.build_ui()
        
        # Load Profiles
        self.refresh_profiles()
        
        # System Tray Integration
        self.tray_icon = None
        self.setup_tray()
        
        # Window closing behavior -> minimize to tray
        self.root.protocol('WM_DELETE_WINDOW', self.minimize_to_tray)
        
        # Auto-refresh status thread
        self.running = True
        self.refresh_thread = threading.Thread(target=self.auto_refresh_loop, daemon=True)
        self.refresh_thread.start()

    def create_icon_image(self):
        # Create a beautiful radio beacon waves image dynamically
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        # Background circle
        draw.ellipse([4, 4, 60, 60], fill=(37, 37, 56, 255), outline=(137, 180, 250, 255), width=3)
        # Beacon waves
        draw.arc([16, 16, 48, 48], start=220, end=320, fill=(137, 180, 250, 255), width=3)
        draw.arc([24, 24, 40, 40], start=220, end=320, fill=(166, 227, 161, 255), width=3)
        # Antenna
        draw.line([32, 36, 32, 52], fill=(205, 214, 244, 255), width=3)
        draw.ellipse([29, 32, 35, 35], fill=(243, 139, 168, 255))
        return image

    def build_ui(self):
        # Top Header Frame
        header_frame = tk.Frame(self.root, bg="#11111b", height=70)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)
        
        header_label = tk.Label(header_frame, text="📻 APRS Multi-Beacon Yönetim Paneli", font=("Outfit", 16, "bold"), fg="#cdd6f4", bg="#11111b")
        header_label.pack(side="left", padx=20, pady=15)
        
        # Add Profile Button
        add_btn = tk.Button(header_frame, text="+ Yeni Profil Ekle", font=("Outfit", 10, "bold"), bg="#a6e3a1", fg="#11111b", 
                            relief="flat", activebackground="#89b4fa", command=self.open_add_profile_dialog)
        add_btn.pack(side="right", padx=20, pady=15)
        add_btn.bind("<Enter>", lambda e: add_btn.configure(bg="#89b4fa"))
        add_btn.bind("<Leave>", lambda e: add_btn.configure(bg="#a6e3a1"))
        
        # Main content area (scrollable canvas for profiles list)
        self.main_container = tk.Frame(self.root, bg="#1e1e2e")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Welcome message
        self.welcome_label = tk.Label(self.main_container, text="Henüz hiçbir profil kurulu değil. Sağ üstten yeni profil ekleyin.", 
                                      font=("Outfit", 12), fg="#7f849c", bg="#1e1e2e")
        
        # Create profile grid frame
        self.grid_frame = tk.Frame(self.main_container, bg="#1e1e2e")
        self.grid_frame.pack(fill="both", expand=True)

    def refresh_profiles(self):
        # Clear current grid widgets
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
            
        profiles = get_profiles()
        if not profiles:
            self.welcome_label.pack(pady=100)
            return
        else:
            self.welcome_label.pack_forget()
            
        # Draw Profile Cards
        row, col = 0, 0
        for name, data in profiles.items():
            self.create_profile_card(name, data, row, col)
            col += 1
            if col > 1: # 2 columns layout
                col = 0
                row += 1

    def create_profile_card(self, name, data, row, col):
        card = tk.Frame(self.grid_frame, bg="#252538", bd=0, highlightthickness=1, highlightbackground="#313244")
        card.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")
        
        # Configure columns weights so they stretch
        self.grid_frame.grid_columnconfigure(0, weight=1)
        self.grid_frame.grid_columnconfigure(1, weight=1)
        
        # Card header (Profile Name & Status indicator)
        card_header = tk.Frame(card, bg="#252538")
        card_header.pack(fill="x", padx=15, pady=(15, 5))
        
        name_label = tk.Label(card_header, text=name.upper(), font=("Outfit", 13, "bold"), fg="#89b4fa", bg="#252538")
        name_label.pack(side="left")
        
        running = is_profile_running(name)
        status_color = "#a6e3a1" if running else "#f38ba8"
        status_text = "Aktif" if running else "Kapalı"
        
        status_dot = tk.Canvas(card_header, width=12, height=12, bg="#252538", highlightthickness=0)
        status_dot.pack(side="right", padx=(5, 0))
        status_dot.create_ellipse(1, 1, 11, 11, fill=status_color, outline="")
        
        status_lbl = tk.Label(card_header, text=status_text, font=("Outfit", 10, "bold"), fg=status_color, bg="#252538")
        status_lbl.pack(side="right")
        
        # Info labels
        info_frame = tk.Frame(card, bg="#252538")
        info_frame.pack(fill="x", padx=15, pady=10)
        
        details = [
            ("Çağrı İşareti:", data.get('callsign')),
            ("Sıklık:", f"{data.get('interval_minutes')} dakika"),
            ("Koordinat:", f"{data.get('latitude')}, {data.get('longitude')}"),
            ("Simge / Mesaj:", f"[{data.get('symbol_code')}] {data.get('comment')[:30]}")
        ]
        
        for idx, (label_txt, val_txt) in enumerate(details):
            lbl = tk.Label(info_frame, text=label_txt, font=("Outfit", 9, "bold"), fg="#585b70", bg="#252538")
            lbl.grid(row=idx, column=0, sticky="w", pady=2)
            val = tk.Label(info_frame, text=val_txt, font=("Outfit", 9), fg="#cdd6f4", bg="#252538")
            val.grid(row=idx, column=1, sticky="w", padx=10, pady=2)
            
        # Action Buttons
        btn_frame = tk.Frame(card, bg="#252538")
        btn_frame.pack(fill="x", padx=15, pady=(5, 15))
        
        # Toggle Start/Stop
        toggle_txt = "Durdur" if running else "Başlat"
        toggle_color = "#f38ba8" if running else "#a6e3a1"
        toggle_fg = "#11111b"
        
        toggle_btn = tk.Button(btn_frame, text=toggle_txt, font=("Outfit", 9, "bold"), bg=toggle_color, fg=toggle_fg, 
                               relief="flat", width=9, command=lambda n=name, r=running: self.toggle_profile(n, r))
        toggle_btn.pack(side="left", padx=2)
        
        # Log Viewer
        log_btn = tk.Button(btn_frame, text="Loglar", font=("Outfit", 9, "bold"), bg="#45475a", fg="#cdd6f4", 
                             relief="flat", width=9, command=lambda n=name: self.open_log_viewer(n))
        log_btn.pack(side="left", padx=2)
        log_btn.bind("<Enter>", lambda e, b=log_btn: b.configure(bg="#585b70"))
        log_btn.bind("<Leave>", lambda e, b=log_btn: b.configure(bg="#45475a"))
        
        # Delete Profile
        del_btn = tk.Button(btn_frame, text="Sil", font=("Outfit", 9, "bold"), bg="#313244", fg="#f38ba8", 
                            relief="flat", width=9, command=lambda n=name: self.delete_profile(n))
        del_btn.pack(side="right", padx=2)
        del_btn.bind("<Enter>", lambda e, b=del_btn: b.configure(bg="#f38ba8", fg="#11111b"))
        del_btn.bind("<Leave>", lambda e, b=del_btn: b.configure(bg="#313244", fg="#f38ba8"))

    def toggle_profile(self, name, currently_running):
        if currently_running:
            stop_profile_service(name)
        else:
            start_profile_service(name)
        time.sleep(0.5) # Give service a moment to toggle
        self.refresh_profiles()
        self.update_tray_menu()

    def delete_profile(self, name):
        if messagebox.askyesno("Profili Sil", f"'{name}' profilini ve tüm verilerini silmek istediğinizden emin misiniz?"):
            delete_profile_files(name)
            self.refresh_profiles()
            self.update_tray_menu()

    def open_log_viewer(self, name):
        log_win = tk.Toplevel(self.root)
        log_win.title(f"📄 {name.upper()} - Log Ekranı")
        log_win.geometry("700x450")
        log_win.configure(bg="#181825")
        
        txt_area = tk.Text(log_win, bg="#11111b", fg="#a6e3a1", font=("Courier", 10), wrap="word", state="disabled")
        txt_area.pack(fill="both", expand=True, padx=15, pady=15)
        
        log_file = os.path.join(LOGS_DIR, f"{name}.log")
        
        def update_logs():
            if not log_win.winfo_exists():
                return
            
            lines = []
            if os.path.exists(log_file):
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()[-100:] # Show last 100 lines
                except Exception as e:
                    lines = [f"Log dosyası okunamadı: {e}"]
            else:
                lines = ["Log kaydı bulunamadı. Servis başladığında kayıtlar burada görünecektir."]
                
            txt_area.configure(state="normal")
            txt_area.delete("1.0", tk.END)
            txt_area.insert(tk.END, "".join(lines))
            txt_area.see(tk.END)
            txt_area.configure(state="disabled")
            
            # Repeat every 2 seconds
            log_win.after(2000, update_logs)
            
        update_logs()

    def open_add_profile_dialog(self):
        # Custom Form Window
        form = tk.Toplevel(self.root)
        form.title("Yeni Profil Ekle")
        form.geometry("400x520")
        form.configure(bg="#1e1e2e")
        form.resizable(False, False)
        
        # Center in parent window
        form.transient(self.root)
        form.grab_set()
        
        # Form layout
        title = tk.Label(form, text="Yeni APRS Profil Ayarları", font=("Outfit", 12, "bold"), fg="#89b4fa", bg="#1e1e2e")
        title.pack(pady=15)
        
        fields_frame = tk.Frame(form, bg="#1e1e2e")
        fields_frame.pack(fill="both", expand=True, padx=20)
        
        labels = [
            ("Profil Adı (Tek kelime):", "name"),
            ("Çağrı İşareti (SSID ile):", "callsign"),
            ("Passcode (Boşsa otomatik hesaplanır):", "passcode"),
            ("Enlem (Latitude):", "latitude"),
            ("Boylam (Longitude):", "longitude"),
            ("Durum Mesajı:", "comment"),
            ("Simge Karakteri (Örn: X, >):", "symbol"),
            ("Gönderim Sıklığı (Dk):", "interval")
        ]
        
        entries = {}
        for idx, (label_txt, name) in enumerate(labels):
            lbl = tk.Label(fields_frame, text=label_txt, font=("Outfit", 9, "bold"), fg="#a6adc8", bg="#1e1e2e")
            lbl.grid(row=idx*2, column=0, sticky="w", pady=(5, 2))
            
            ent = tk.Entry(fields_frame, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", bd=0, highlightthickness=1, highlightbackground="#45475a")
            ent.grid(row=idx*2+1, column=0, sticky="ew", pady=(0, 5))
            entries[name] = ent
            
        fields_frame.grid_columnconfigure(0, weight=1)
        
        # Set default values
        entries['comment'].insert(0, "APRS Background Beacon")
        entries['symbol'].insert(0, "X")
        entries['interval'].insert(0, "5")
        
        def save_new():
            name = entries['name'].get().strip().lower()
            callsign = entries['callsign'].get().strip().upper()
            passcode_in = entries['passcode'].get().strip()
            lat_in = entries['latitude'].get().strip()
            lon_in = entries['longitude'].get().strip()
            comment = entries['comment'].get().strip()
            symbol = entries['symbol'].get().strip()
            interval_in = entries['interval'].get().strip()
            
            if not name or not callsign or not lat_in or not lon_in:
                messagebox.showerror("Hata", "Lütfen zorunlu alanları (Profil Adı, Çağrı İşareti, Koordinatlar) doldurun.", parent=form)
                return
                
            profiles = get_profiles()
            if name in profiles:
                messagebox.showerror("Hata", f"'{name}' adında bir profil zaten mevcut.", parent=form)
                return
                
            try:
                lat = float(lat_in)
                lon = float(lon_in)
            except ValueError:
                messagebox.showerror("Hata", "Koordinatlar sayısal değerler olmalıdır.", parent=form)
                return
                
            if not passcode_in:
                passcode = generate_aprs_passcode(callsign)
            else:
                try:
                    passcode = int(passcode_in)
                except ValueError:
                    messagebox.showerror("Hata", "Geçersiz şifre formatı.", parent=form)
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
                "server": "rotate.aprs2.net",
                "port": 14580
            }
            
            save_profile(name, data)
            form.destroy()
            self.refresh_profiles()
            self.update_tray_menu()
            
            if messagebox.askyesno("Başlat", f"'{name}' profili başarıyla oluşturuldu. Hemen başlatılsın mı?"):
                start_profile_service(name)
                self.refresh_profiles()
                self.update_tray_menu()

        save_btn = tk.Button(form, text="Profili Kaydet", font=("Outfit", 10, "bold"), bg="#a6e3a1", fg="#11111b", 
                             relief="flat", command=save_new)
        save_btn.pack(pady=15, side="bottom", fill="x", padx=20)

    # --- System Tray Logic ---
    def setup_tray(self):
        # Dynamic Tray Menu
        self.update_tray_menu()

    def update_tray_menu(self):
        if not GUI_AVAILABLE:
            return
            
        profiles = get_profiles()
        menu_items = [
            pystray.MenuItem("Kontrol Panelini Göster", self.restore_from_tray, default=True),
            pystray.Menu.SEPARATOR
        ]
        
        # Dynamic profiles submenus
        if profiles:
            def toggle_wrapper(name, running):
                return lambda: self.root.after(0, lambda: self.toggle_profile(name, running))
                
            for name in profiles.keys():
                running = is_profile_running(name)
                icon_prefix = "🟢 " if running else "🔴 "
                toggle_txt = f"{icon_prefix}{name.upper()} ({'Durdur' if running else 'Başlat'})"
                menu_items.append(pystray.MenuItem(toggle_txt, toggle_wrapper(name, running)))
                
            menu_items.append(pystray.Menu.SEPARATOR)
            
        menu_items.append(pystray.MenuItem("Tümünü Başlat", self.start_all_profiles))
        menu_items.append(pystray.MenuItem("Tümünü Durdur", self.stop_all_profiles))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Çıkış", self.quit_application))
        
        menu = pystray.Menu(*menu_items)
        
        if self.tray_icon:
            self.tray_icon.menu = menu
        else:
            self.tray_icon = pystray.Icon("aprs_manager", self.icon_image, "APRS Manager", menu)
            # Run tray loop in background thread
            tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
            tray_thread.start()

    def start_all_profiles(self):
        profiles = get_profiles()
        for name in profiles.keys():
            start_profile_service(name)
        time.sleep(0.5)
        self.root.after(0, self.refresh_profiles)
        self.root.after(0, self.update_tray_menu)

    def stop_all_profiles(self):
        profiles = get_profiles()
        for name in profiles.keys():
            stop_profile_service(name)
        time.sleep(0.5)
        self.root.after(0, self.refresh_profiles)
        self.root.after(0, self.update_tray_menu)

    def minimize_to_tray(self):
        self.root.withdraw()
        if self.tray_icon:
            self.tray_icon.notify("APRS Manager arka planda çalışmaya devam ediyor.", "Arka Planda Çalışma")

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
        # Refresh the UI grid status every 10 seconds silently
        while self.running:
            time.sleep(10)
            if self.running and self.root.winfo_exists():
                try:
                    self.root.after(0, self.refresh_profiles)
                except:
                    pass

# --- Entry Point / Argument Parsing ---
def main():
    parser = argparse.ArgumentParser(description="APRS Multi-Beacon Management Utility")
    parser.add_argument('command', nargs='?', choices=['list', 'start', 'stop', 'create', 'delete', 'gui'], default='gui',
                        help="Command to run (list, start, stop, create, delete, gui)")
    parser.add_argument('profile_name', nargs='?', help="Target profile name for start/stop/delete commands")
    args = parser.parse_args()
    
    if args.command == 'list':
        cli_list()
    elif args.command == 'create':
        cli_create()
    elif args.command == 'delete':
        if not args.profile_name:
            print("Hata: Hangi profili silmek istediğinizi belirtmelisiniz. (Örn: aprs_manager delete profil_adi)")
        else:
            cli_delete(args.profile_name)
    elif args.command == 'start':
        if not args.profile_name:
            print("Hata: Hangi profili başlatmak istediğinizi belirtmelisiniz.")
        else:
            cli_start(args.profile_name)
    elif args.command == 'stop':
        if not args.profile_name:
            print("Hata: Hangi profili durdurmak istediğinizi belirtmelisiniz.")
        else:
            cli_stop(args.profile_name)
    elif args.command == 'gui':
        if not GUI_AVAILABLE:
            print("\033[91mHata: GUI kütüphaneleri (tkinter, pystray, pillow) kurulu değil.\033[0m")
            print("Lütfen aşağıdaki komutları kullanarak gereksinimleri kurun:\n")
            if IS_LINUX:
                print("  sudo apt update && sudo apt install python3-tk python3-pystray -y")
            elif IS_WINDOWS:
                print("  pip install pystray Pillow")
            print("\nYöneticiyi terminal üzerinden (CLI) kullanmaya devam edebilirsiniz. Kullanılabilir komutlar:")
            print("  aprs_manager list")
            print("  aprs_manager create")
            print("  aprs_manager start <profil>")
            print("  aprs_manager stop <profil>")
            print("  aprs_manager delete <profil>")
            sys.exit(1)
            
        root = tk.Tk()
        app = APRSManagerGUI(root)
        root.mainloop()

if __name__ == '__main__':
    main()
