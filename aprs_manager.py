#!/usr/bin/env python3
import os
import sys
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

# --- Security & Auth Configurations ---
CURRENT_USER = getpass.getuser()
IS_BYPASS = (CURRENT_USER == 'turan')

def get_admin_pin_hash():
    pin_file = os.path.join(BASE_DIR, '.admin_pin')
    if not os.path.exists(pin_file):
        # varsayılan PIN: "7373"
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
    print("\033[93m[!] Bu işlem için Yönetici PIN kodu gereklidir.\033[0m")
    for _ in range(3):
        pin = getpass.getpass("Yönetici PIN: ").strip()
        if verify_pin(pin):
            return True
        print("\033[91mHata: Geçersiz PIN kodu!\033[0m")
    return False

def gui_require_auth(parent=None):
    if IS_BYPASS:
        return True
    pin = simpledialog.askstring("Yetkilendirme", "Lütfen Yönetici PIN kodunu girin:", show="*", parent=parent)
    if pin is None:
        return False
    if verify_pin(pin):
        return True
    messagebox.showerror("Hata", "Geçersiz PIN kodu!", parent=parent)
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

def self_update():
    repo_path_file = os.path.join(BASE_DIR, '.repo_path')
    if not os.path.exists(repo_path_file):
        return False, "Hata: Kurulum kaynak dizini (.repo_path) bulunamadı. Lütfen kurulum sihirbazını elle çalıştırın."
        
    try:
        with open(repo_path_file, 'r', encoding='utf-8') as f:
            repo_path = f.read().strip()
            
        if not os.path.exists(repo_path):
            return False, f"Hata: Kaynak dizin ({repo_path}) mevcut değil."
            
        # Run git pull in the repository path
        if not IS_WINDOWS:
            res = subprocess.run(['git', 'pull'], cwd=repo_path, capture_output=True, text=True)
            if res.returncode != 0:
                return False, f"Git Pull Hatası:\n{res.stderr}"
        else:
            res = subprocess.run(['powershell', '-Command', 'git pull'], cwd=repo_path, capture_output=True, text=True)
            if res.returncode != 0:
                return False, f"Git Pull Hatası:\n{res.stderr}"
                
        # Copy files
        import shutil
        shutil.copy2(os.path.join(repo_path, 'aprs_beacon.py'), os.path.join(BASE_DIR, 'aprs_beacon.py'))
        shutil.copy2(os.path.join(repo_path, 'aprs_manager.py'), os.path.join(BASE_DIR, 'aprs_manager.py'))
        
        return True, "Uygulama başarıyla güncellendi! Yeni özellikleri görmek için lütfen uygulamayı kapatıp yeniden açın."
    except Exception as e:
        return False, f"Güncelleme Hatası: {e}"

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
        return True, f"Ayarlar başarıyla dışa aktarıldı: {export_file_path}"
    except Exception as e:
        return False, f"Dışa aktarma hatası: {e}"

def import_settings(import_file_path):
    try:
        with open(import_file_path, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
            
        profiles = backup_data.get("profiles", {})
        if not profiles:
            return False, "Hata: Seçilen dosyada profil kaydı bulunamadı."
            
        if not IS_BYPASS:
            current_profiles = get_profiles()
            union_profiles = set(current_profiles.keys()) | set(profiles.keys())
            if len(union_profiles) > 2:
                return False, f"Hata: İçe aktarma sonrasında profil sayısı ({len(union_profiles)}) sınırını aşacaktır (En fazla 2 profile izin verilir)."
            
        for name, data in profiles.items():
            save_profile(name, data)
            
        return True, f"{len(profiles)} adet profil başarıyla içe aktarıldı."
    except Exception as e:
        return False, f"İçe aktarma hatası: {e}"

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
    print(f"{'Profil Adı':<15} | {'Çağrı İşareti':<12} | {'Sıklık':<7} | {'Perşembe':<9} | {'Durum':<10}")
    print("-" * 65)
    for name, data in profiles.items():
        running = is_profile_running(name)
        status_str = "\033[92mAktif\033[0m" if running else "\033[91mKapalı\033[0m"
        thursday_str = "Aktif" if data.get('aprs_thursday', False) else "Pasif"
        print(f"{name:<15} | {data.get('callsign', 'N0CALL'):<12} | {data.get('interval_minutes', 5):<7} | {thursday_str:<9} | {status_str:<10}")
    print()

def cli_create():
    if not IS_BYPASS and len(get_profiles()) >= 2:
        print("\033[91mHata: En fazla 2 profil ekleyebilirsiniz. Daha fazlası için yetkili olmanız gerekir.\033[0m")
        return
        
    if not cli_require_auth():
        return

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

    thursday_input = input("APRS Perşembe etkinliğine katılsın mı? (ANSRVR) [y/N]: ").strip().lower()
    aprs_thursday = thursday_input == 'y'
    aprs_thursday_time = "20:00"
    if aprs_thursday:
        aprs_thursday_time = input("APRS Perşembe saati (Örn: 20:00) [Varsayılan: 20:00]: ").strip() or "20:00"

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
    if not cli_require_auth():
        return
        
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

def cli_edit():
    if not cli_require_auth():
        return

    print("\n=== Profil Bilgilerini Güncelle ===")
    profiles = get_profiles()
    if not profiles:
        print("Güncellenebilecek herhangi bir profil bulunamadı.")
        return
        
    name = input("Güncellemek istediğiniz profil adı: ").strip().lower()
    if name not in profiles:
        print(f"Hata: '{name}' adında bir profil bulunamadı.")
        return
        
    data = profiles[name]
    print(f"\nGüncelleniyor: {name.upper()}")
    print("İpucu: Mevcut değeri korumak için boş bırakıp Enter'a basın.")
    
    callsign = input(f"Çağrı İşareti ({data.get('callsign')}): ").strip().upper() or data.get('callsign')
    
    passcode_in = input(f"Passcode ({data.get('passcode')}): ").strip()
    passcode = int(passcode_in) if passcode_in else data.get('passcode')
    
    try:
        lat_in = input(f"Enlem ({data.get('latitude')}): ").strip()
        lat = float(lat_in) if lat_in else data.get('latitude')
        
        lon_in = input(f"Boylam ({data.get('longitude')}): ").strip()
        lon = float(lon_in) if lon_in else data.get('longitude')
    except ValueError:
        print("Hata: Koordinatlar sayısal olmalıdır. İşlem iptal edildi.")
        return
        
    comment = input(f"Durum Mesajı ({data.get('comment')}): ").strip() or data.get('comment')
    symbol = input(f"Simge Karakteri ({data.get('symbol_code')}): ").strip() or data.get('symbol_code')
    
    try:
        interval_in = input(f"Sıklık ({data.get('interval_minutes')} dk): ").strip()
        interval = int(interval_in) if interval_in else data.get('interval_minutes')
    except ValueError:
        interval = data.get('interval_minutes')
        
    thursday_in = input(f"APRS Perşembe ({'Etkin' if data.get('aprs_thursday', False) else 'Pasif'}) [y/N]: ").strip().lower()
    aprs_thursday = data.get('aprs_thursday', False)
    if thursday_in:
        aprs_thursday = thursday_in == 'y'
        
    aprs_thursday_time = data.get('aprs_thursday_time', '20:00')
    if aprs_thursday:
        thursday_time_in = input(f"APRS Perşembe saati ({aprs_thursday_time}): ").strip()
        if thursday_time_in:
            aprs_thursday_time = thursday_time_in
        
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
        "server": "rotate.aprs2.net",
        "port": 14580
    }
    
    save_profile(name, updated_data)
    print(f"[+] '{name}' profili başarıyla güncellendi.")
    
    if is_profile_running(name):
        print("[i] Profil arka planda çalışıyor, değişikliklerin yansıması için yeniden başlatılıyor...")
        stop_profile_service(name)
        time.sleep(0.5)
        start_profile_service(name)
        print("[+] Profil başarıyla yeniden başlatıldı.")

# --- GUI Mode Implementation ---
class APRSManagerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("APRS Beacon Yonetim Paneli")
        self.root.geometry("900x600")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(False, False)
        
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
        header_frame = tk.Frame(self.root, bg="#11111b", height=75)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)
        
        header_label = tk.Label(header_frame, text="APRS Multi-Beacon Yonetim Paneli", font=("DejaVu Sans", 14, "bold"), fg="#cdd6f4", bg="#11111b")
        header_label.pack(side="left", padx=20, pady=20)
        
        # Buttons container in header
        btn_container = tk.Frame(header_frame, bg="#11111b")
        btn_container.pack(side="right", padx=20, pady=15)
        
        # Add Profile Button
        add_btn = tk.Button(btn_container, text="+ Yeni Profil", font=("DejaVu Sans", 9, "bold"), bg="#a6e3a1", fg="#11111b", 
                            relief="flat", padx=10, pady=5, activebackground="#89b4fa", command=self.open_add_profile_dialog)
        add_btn.pack(side="left", padx=4)
        add_btn.bind("<Enter>", lambda e: add_btn.configure(bg="#89b4fa"))
        add_btn.bind("<Leave>", lambda e: add_btn.configure(bg="#a6e3a1"))

        # Import Button
        import_btn = tk.Button(btn_container, text="Ice Aktar", font=("DejaVu Sans", 9, "bold"), bg="#89b4fa", fg="#11111b",
                              relief="flat", padx=10, pady=5, activebackground="#b4befe", command=self.trigger_import)
        import_btn.pack(side="left", padx=4)
        import_btn.bind("<Enter>", lambda e: import_btn.configure(bg="#b4befe"))
        import_btn.bind("<Leave>", lambda e: import_btn.configure(bg="#89b4fa"))

        # Export Button
        export_btn = tk.Button(btn_container, text="Disa Aktar", font=("DejaVu Sans", 9, "bold"), bg="#cba6f7", fg="#11111b",
                              relief="flat", padx=10, pady=5, activebackground="#f5c2e7", command=self.trigger_export)
        export_btn.pack(side="left", padx=4)
        export_btn.bind("<Enter>", lambda e: export_btn.configure(bg="#f5c2e7"))
        export_btn.bind("<Leave>", lambda e: export_btn.configure(bg="#cba6f7"))

        # Update Button
        update_btn = tk.Button(btn_container, text="Guncelle", font=("DejaVu Sans", 9, "bold"), bg="#f9e2af", fg="#11111b",
                              relief="flat", padx=10, pady=5, activebackground="#f38ba8", command=self.trigger_self_update)
        update_btn.pack(side="left", padx=4)
        update_btn.bind("<Enter>", lambda e: update_btn.configure(bg="#f38ba8"))
        update_btn.bind("<Leave>", lambda e: update_btn.configure(bg="#f9e2af"))
        
        # Main content area
        self.main_container = tk.Frame(self.root, bg="#1e1e2e")
        self.main_container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # Welcome message
        self.welcome_label = tk.Label(self.main_container, text="Henuz hicbir profil kurulu degil.\nSag ustten yeni bir profil ekleyerek baslayin.", 
                                      font=("DejaVu Sans", 11), fg="#7f849c", bg="#1e1e2e")
        
        # Create profile grid frame
        self.grid_frame = tk.Frame(self.main_container, bg="#1e1e2e")
        self.grid_frame.pack(fill="both", expand=True)

    def refresh_profiles(self):
        # Clear current grid widgets
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
            
        profiles = get_profiles()
        if not profiles:
            self.welcome_label.pack(pady=120)
            return
        else:
            self.welcome_label.pack_forget()
            
        # Draw Profile Cards
        self.grid_frame.grid_columnconfigure(0, weight=1)
        for idx, (name, data) in enumerate(profiles.items()):
            self.create_profile_card(name, data, idx, 0)

    def create_profile_card(self, name, data, row, col):
        card = tk.Frame(self.grid_frame, bg="#252538", bd=0, highlightthickness=1, highlightbackground="#313244", padx=15, pady=12)
        card.grid(row=row, column=0, padx=10, pady=6, sticky="ew")
        
        # Left side: Name & Status
        left_frame = tk.Frame(card, bg="#252538")
        left_frame.pack(side="left", fill="y")
        
        # Status indicator
        running = is_profile_running(name)
        status_color = "#a6e3a1" if running else "#f38ba8"
        status_text = "AKTIF" if running else "KAPALI"
        
        # Status pill
        status_frame = tk.Frame(left_frame, bg=status_color, padx=8, pady=2)
        status_frame.pack(side="left", padx=(0, 15))
        
        status_lbl = tk.Label(status_frame, text=status_text, font=("DejaVu Sans", 8, "bold"), fg="#11111b", bg=status_color)
        status_lbl.pack()
        
        name_lbl = tk.Label(left_frame, text=name.upper(), font=("DejaVu Sans", 11, "bold"), fg="#89b4fa", bg="#252538")
        name_lbl.pack(side="top", anchor="w")
        
        call_lbl = tk.Label(left_frame, text=data.get('callsign', ''), font=("DejaVu Sans", 9), fg="#a6adc8", bg="#252538")
        call_lbl.pack(side="bottom", anchor="w")
        
        # Middle side: Details
        mid_frame = tk.Frame(card, bg="#252538")
        mid_frame.pack(side="left", fill="both", expand=True, padx=30)
        
        # Details grid
        lbl_style = {"font": ("DejaVu Sans", 9, "bold"), "fg": "#b4befe", "bg": "#252538"}
        val_style = {"font": ("DejaVu Sans", 9), "fg": "#cdd6f4", "bg": "#252538"}
        
        comment_val = data.get('comment', 'APRS Background Beacon')
        if len(comment_val) > 40:
            comment_val = comment_val[:37] + "..."
            
        tk.Label(mid_frame, text="Siklik:", **lbl_style).grid(row=0, column=0, sticky="w", pady=1)
        tk.Label(mid_frame, text=f"{data.get('interval_minutes')} dakika", **val_style).grid(row=0, column=1, sticky="w", padx=10, pady=1)
        
        tk.Label(mid_frame, text="Konum:", **lbl_style).grid(row=1, column=0, sticky="w", pady=1)
        tk.Label(mid_frame, text=f"{data.get('latitude')}, {data.get('longitude')} ({data.get('symbol_code')})", **val_style).grid(row=1, column=1, sticky="w", padx=10, pady=1)

        tk.Label(mid_frame, text="Mesaj:", **lbl_style).grid(row=2, column=0, sticky="w", pady=1)
        tk.Label(mid_frame, text=comment_val, **val_style).grid(row=2, column=1, sticky="w", padx=10, pady=1)

        # Right side: Actions
        right_frame = tk.Frame(card, bg="#252538")
        right_frame.pack(side="right", fill="y")
        
        toggle_txt = "Durdur" if running else "Baslat"
        toggle_color = "#f38ba8" if running else "#a6e3a1"
        
        toggle_btn = tk.Button(right_frame, text=toggle_txt, font=("DejaVu Sans", 9, "bold"), bg=toggle_color, fg="#11111b", 
                               relief="flat", width=8, pady=3, command=lambda n=name, r=running: self.toggle_profile(n, r))
        toggle_btn.pack(side="left", padx=3)
        
        log_btn = tk.Button(right_frame, text="Loglar", font=("DejaVu Sans", 9, "bold"), bg="#45475a", fg="#cdd6f4", 
                             relief="flat", width=8, pady=3, command=lambda n=name: self.open_log_viewer(n))
        log_btn.pack(side="left", padx=3)
        log_btn.bind("<Enter>", lambda e, b=log_btn: b.configure(bg="#585b70"))
        log_btn.bind("<Leave>", lambda e, b=log_btn: b.configure(bg="#45475a"))
        
        edit_btn = tk.Button(right_frame, text="Duzenle", font=("DejaVu Sans", 9, "bold"), bg="#313244", fg="#f9e2af", 
                             relief="flat", width=8, pady=3, command=lambda n=name: self.open_add_profile_dialog(n))
        edit_btn.pack(side="left", padx=3)
        edit_btn.bind("<Enter>", lambda e, b=edit_btn: b.configure(bg="#f9e2af", fg="#11111b"))
        edit_btn.bind("<Leave>", lambda e, b=edit_btn: b.configure(bg="#313244", fg="#f9e2af"))
        
        del_btn = tk.Button(right_frame, text="Sil", font=("DejaVu Sans", 9, "bold"), bg="#313244", fg="#f38ba8", 
                            relief="flat", width=6, pady=3, command=lambda n=name: self.delete_profile(n))
        del_btn.pack(side="left", padx=3)
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
        if not gui_require_auth(self.root):
            return
        if messagebox.askyesno("Profili Sil", f"'{name}' profilini ve tum verilerini silmek istediginizden emin misiniz?"):
            delete_profile_files(name)
            self.refresh_profiles()
            self.update_tray_menu()

    def open_log_viewer(self, name):
        log_win = tk.Toplevel(self.root)
        log_win.title(f"{name.upper()} - Canli Gunluk Kayitlari")
        log_win.geometry("750x500")
        log_win.configure(bg="#1e1e2e")
        
        header_lbl = tk.Label(log_win, text=f"{name.upper()} Profili Canli Log Takibi", font=("DejaVu Sans", 11, "bold"), fg="#89b4fa", bg="#1e1e2e")
        header_lbl.pack(pady=(15, 5))
        
        info_lbl = tk.Label(log_win, text="En son 100 gunluk kaydi canli olarak asagida gosterilmektedir.", font=("DejaVu Sans", 9), fg="#a6adc8", bg="#1e1e2e")
        info_lbl.pack(pady=(0, 10))
        
        txt_area = tk.Text(log_win, bg="#11111b", fg="#a6e3a1", font=("DejaVu Sans Mono", 9), wrap="word", state="disabled",
                           bd=0, highlightthickness=1, highlightbackground="#313244")
        txt_area.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
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
                    lines = [f"Log dosyasi okunamadi: {e}"]
            else:
                lines = ["Log kaydi bulunamadi. Servis basladiginda kayitlar burada gorunecektir."]
                
            txt_area.configure(state="normal")
            txt_area.delete("1.0", tk.END)
            txt_area.insert(tk.END, "".join(lines))
            txt_area.see(tk.END)
            txt_area.configure(state="disabled")
            
            # Repeat every 2 seconds
            log_win.after(2000, update_logs)
            
        update_logs()

    def open_add_profile_dialog(self, edit_profile_name=None):
        # 2 profile limit check
        if not edit_profile_name and not IS_BYPASS and len(get_profiles()) >= 2:
            messagebox.showerror("Hata", "En fazla 2 profil ekleyebilirsiniz. Daha fazlasi icin yetkili olmaniz gerekir.")
            return

        # Auth check
        if not gui_require_auth(self.root):
            return

        # Custom Form Window
        form = tk.Toplevel(self.root)
        form.title("Yeni Profil Ekle" if not edit_profile_name else f"Profil Duzenle: {edit_profile_name}")
        form.geometry("520x490")
        form.configure(bg="#1e1e2e")
        form.resizable(False, False)
        
        # Center in parent window
        form.transient(self.root)
        form.grab_set()
        
        title_lbl_text = "Yeni APRS Profil Ayarlari" if not edit_profile_name else "APRS Profil Ayarlarini Duzenle"
        title = tk.Label(form, text=title_lbl_text, font=("DejaVu Sans", 13, "bold"), fg="#89b4fa", bg="#1e1e2e")
        title.pack(pady=(20, 15))
        
        fields_frame = tk.Frame(form, bg="#1e1e2e")
        fields_frame.pack(fill="both", expand=True, padx=25)
        
        fields_config = [
            ("Profil Adi (Tek kelime)", "name", 0, 0),
            ("Cagri Isareti (SSID'li)", "callsign", 0, 1),
            ("APRS-IS Sifresi (Passcode)", "passcode", 1, 0),
            ("Gonderim Sikligi (Dakika)", "interval", 1, 1),
            ("Enlem (Latitude)", "latitude", 2, 0),
            ("Boylam (Longitude)", "longitude", 2, 1),
            ("Simge Karakteri (Orn: X, >)", "symbol", 3, 0),
        ]
        
        entries = {}
        for label_txt, name, row, col in fields_config:
            cell_frame = tk.Frame(fields_frame, bg="#1e1e2e")
            cell_frame.grid(row=row, column=col, sticky="ew", padx=10, pady=8)
            
            lbl = tk.Label(cell_frame, text=label_txt, font=("DejaVu Sans", 9, "bold"), fg="#a6adc8", bg="#1e1e2e")
            lbl.pack(anchor="w", pady=(0, 3))
            
            ent = tk.Entry(cell_frame, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", 
                           bd=0, highlightthickness=1, highlightbackground="#45475a", font=("DejaVu Sans", 10),
                           relief="flat")
            ent.pack(fill="x", ipady=3)
            entries[name] = ent
            
        fields_frame.columnconfigure(0, weight=1)
        fields_frame.columnconfigure(1, weight=1)
        
        # Comment field: spans column 1 at row 3
        comment_frame = tk.Frame(fields_frame, bg="#1e1e2e")
        comment_frame.grid(row=3, column=1, sticky="ew", padx=10, pady=8)
        
        comment_lbl = tk.Label(comment_frame, text="Durum Mesaji (Comment)", font=("DejaVu Sans", 9, "bold"), fg="#a6adc8", bg="#1e1e2e")
        comment_lbl.pack(anchor="w", pady=(0, 3))
        
        comment_ent = tk.Entry(comment_frame, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", 
                               bd=0, highlightthickness=1, highlightbackground="#45475a", font=("DejaVu Sans", 10),
                               relief="flat")
        comment_ent.pack(fill="x", ipady=3)
        entries['comment'] = comment_ent

        # APRS Thursday & Time frame: spans full width
        thurs_frame = tk.Frame(fields_frame, bg="#252538", padx=12, pady=10, highlightthickness=1, highlightbackground="#313244")
        thurs_frame.grid(row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=15)
        
        thursday_var = tk.BooleanVar(value=False)
        thursday_cb = tk.Checkbutton(thurs_frame, text="Her Persembe APRS Etkinligine Katil (ANSRVR)", variable=thursday_var, 
                                     font=("DejaVu Sans", 9, "bold"), fg="#cdd6f4", bg="#252538", activebackground="#252538", 
                                     activeforeground="#cdd6f4", selectcolor="#313244")
        thursday_cb.pack(side="left")
        
        time_ent = tk.Entry(thurs_frame, bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4", 
                            bd=0, highlightthickness=1, highlightbackground="#45475a", width=6, font=("DejaVu Sans", 10))
        time_ent.pack(side="right", padx=(5, 0))
        time_ent.insert(0, "20:00")
        
        time_lbl = tk.Label(thurs_frame, text="Saat (SS:DD):", font=("DejaVu Sans", 9, "bold"), fg="#a6adc8", bg="#252538")
        time_lbl.pack(side="right")
        
        # Set default values or load edit values
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
        else:
            entries['comment'].insert(0, "APRS Background Beacon")
            entries['symbol'].insert(0, "X")
            entries['interval'].insert(0, "5")
        
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
            
            if not name or not callsign or not lat_in or not lon_in:
                messagebox.showerror("Hata", "Lutfen zorunlu alanlari (Profil Adi, Cagri Isareti, Koordinatlar) doldurun.", parent=form)
                return
                
            if not edit_profile_name:
                profiles = get_profiles()
                if name in profiles:
                    messagebox.showerror("Hata", f"'{name}' adinda bir profil zaten mevcut.", parent=form)
                    return
                
            try:
                lat = float(lat_in)
                lon = float(lon_in)
            except ValueError:
                messagebox.showerror("Hata", "Koordinatlar sayisal degerler olmalidir.", parent=form)
                return
                
            if not passcode_in:
                passcode = generate_aprs_passcode(callsign)
            else:
                try:
                    passcode = int(passcode_in)
                except ValueError:
                    messagebox.showerror("Hata", "Gecersiz sifre formati.", parent=form)
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
                "server": "rotate.aprs2.net",
                "port": 14580
            }
            
            save_profile(name, data)
            form.destroy()
            self.refresh_profiles()
            self.update_tray_menu()
            
            if edit_profile_name:
                if is_profile_running(name):
                    stop_profile_service(name)
                    time.sleep(0.5)
                    start_profile_service(name)
                    self.refresh_profiles()
                    self.update_tray_menu()
                messagebox.showinfo("Basarili", f"'{name}' profili basariyla guncellendi.")
            else:
                if messagebox.askyesno("Baslat", f"'{name}' profili basariyla olusturuldu. Hemen baslatilsin mi?"):
                    start_profile_service(name)
                    self.refresh_profiles()
                    self.update_tray_menu()

        save_btn = tk.Button(form, text="Ayarlari Kaydet", font=("DejaVu Sans", 10, "bold"), bg="#a6e3a1", fg="#11111b", 
                             relief="flat", pady=8, command=save_new)
        save_btn.pack(pady=(0, 20), side="bottom", fill="x", padx=35)

    # --- System Tray Logic ---
    def setup_tray(self):
        # Dynamic Tray Menu
        self.update_tray_menu()

    def update_tray_menu(self):
        if not GUI_AVAILABLE:
            return
            
        profiles = get_profiles()
        menu_items = [
            pystray.MenuItem("Kontrol Panelini Goster", self.restore_from_tray, default=True),
            pystray.Menu.SEPARATOR
        ]
        
        # Dynamic profiles submenus
        if profiles:
            def toggle_wrapper(name, running):
                return lambda: self.root.after(0, lambda: self.toggle_profile(name, running))
                
            for name in profiles.keys():
                running = is_profile_running(name)
                icon_prefix = "ON - " if running else "OFF - "
                toggle_txt = f"{icon_prefix}{name.upper()} ({'Durdur' if running else 'Baslat'})"
                menu_items.append(pystray.MenuItem(toggle_txt, toggle_wrapper(name, running)))
                
            menu_items.append(pystray.Menu.SEPARATOR)
            
        menu_items.append(pystray.MenuItem("Tumunu Baslat", self.start_all_profiles))
        menu_items.append(pystray.MenuItem("Tumunu Durdur", self.stop_all_profiles))
        menu_items.append(pystray.Menu.SEPARATOR)
        menu_items.append(pystray.MenuItem("Cikis", self.quit_application))
        
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

    def trigger_self_update(self):
        if not gui_require_auth(self.root):
            return
        if messagebox.askyesno("Güncelleme", "Uygulamayı en son GitHub sürümüne güncellemek istiyor musunuz?"):
            success, msg = self_update()
            if success:
                messagebox.showinfo("Başarılı", msg)
            else:
                messagebox.showerror("Hata", msg)

    def trigger_export(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title="APRS Ayarlarını Dışa Aktar",
            initialfile=f"aprs_backup_{datetime.now().strftime('%Y%m%d')}.json"
        )
        if file_path:
            success, msg = export_settings(file_path)
            if success:
                messagebox.showinfo("Başarılı", msg)
            else:
                messagebox.showerror("Hata", msg)

    def trigger_import(self):
        if not gui_require_auth(self.root):
            return
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON Files", "*.json")],
            title="APRS Ayarlarını İçe Aktar"
        )
        if file_path:
            success, msg = import_settings(file_path)
            if success:
                messagebox.showinfo("Başarılı", msg)
                self.refresh_profiles()
                self.update_tray_menu()
            else:
                messagebox.showerror("Hata", msg)

# --- CLI Interactive Mode & Helper ---
def cli_show_logs_interactive(profile_name):
    profiles = get_profiles()
    if profile_name not in profiles:
        print(f"Hata: '{profile_name}' adında bir profil bulunamadı.")
        return
        
    log_path = os.path.join(LOGS_DIR, f"{profile_name}.log")
    if not os.path.exists(log_path):
        print("Log kaydı henüz oluşmadı. Servis çalışmaya başladığında loglar burada görünecektir.")
        return
        
    print(f"\n--- {profile_name.upper()} LOGLARI (Çıkmak için Ctrl+C tuşlarına basın) ---")
    try:
        # Open and read last 20 lines
        with open(log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(line, end='')
                
            # Keep tailing
            while True:
                line = f.readline()
                if not line:
                    time.sleep(1)
                    continue
                print(line, end='')
    except KeyboardInterrupt:
        print("\nLog takibi sonlandırıldı.")

def cli_interactive_menu():
    while True:
        print("\n=== APRS Multi-Beacon Yönetim Paneli (Terminal Modu) ===")
        print("1) Profilleri Listele")
        print("2) Yeni Profil Ekle")
        print("3) Profil Başlat")
        print("4) Profil Durdur")
        print("5) Profil Sil")
        print("6) Canlı Log İzleyici")
        print("7) Profil Düzenle (Güncelle)")
        print("8) Ayarları Dışa Aktar (Yedekle)")
        print("9) Ayarları İçe Aktar (Geri Yükle)")
        print("10) Uygulamayı Güncelle")
        print("11) Çıkış")
        print("-" * 55)
        
        choice = input("Seçiminiz [1-11]: ").strip()
        
        if choice == '1':
            cli_list()
        elif choice == '2':
            cli_create()
        elif choice == '3':
            name = input("Başlatılacak profil adı: ").strip().lower()
            if name:
                cli_start(name)
        elif choice == '4':
            name = input("Durdurulacak profil adı: ").strip().lower()
            if name:
                cli_stop(name)
        elif choice == '5':
            name = input("Silinecek profil adı: ").strip().lower()
            if name:
                cli_delete(name)
        elif choice == '6':
            name = input("Logları izlenecek profil adı: ").strip().lower()
            if name:
                cli_show_logs_interactive(name)
        elif choice == '7':
            cli_edit()
        elif choice == '8':
            export_path = input("Dışa aktarılacak dosya yolu [Varsayılan: ~/aprs_backup.json]: ").strip()
            if not export_path:
                export_path = os.path.expanduser("~/aprs_backup.json")
            success, msg = export_settings(export_path)
            print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '9':
            if not cli_require_auth():
                continue
            import_path = input("İçe aktarılacak JSON dosya yolu: ").strip()
            if import_path:
                success, msg = import_settings(import_path)
                print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '10':
            if not cli_require_auth():
                continue
            print("[i] Güncelleme işlemi başlatılıyor...")
            success, msg = self_update()
            print(f"[+] {msg}" if success else f"[-] {msg}")
        elif choice == '11' or choice.lower() == 'exit':
            print("Çıkış yapılıyor...")
            break
        else:
            print("Geçersiz seçim. Lütfen 1-11 arasında bir değer girin.")

# --- Entry Point / Argument Parsing ---
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
        print("[i] Güncelleme işlemi başlatılıyor...")
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
            print("Hata: İçe aktarılacak dosya yolunu belirtmelisiniz. (Örn: aprs_manager import backup.json)")
        else:
            success, msg = import_settings(path)
            print(f"[+] {msg}" if success else f"[-] {msg}")
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
        # Check if running in headless environment (no display server)
        # On Linux, DISPLAY environment variable is required for X11/Tkinter.
        is_headless = False
        if IS_LINUX and 'DISPLAY' not in os.environ:
            is_headless = True
            
        if not GUI_AVAILABLE or is_headless:
            if is_headless:
                print("\033[93m[!] Grafik sunucusu (DISPLAY) bulunamadı. Headless ortamdasınız.\033[0m")
            else:
                print("\033[91mHata: GUI kütüphaneleri (tkinter, pystray, pillow) kurulu değil.\033[0m")
                
            print("Yönetici terminal üzerinden (CLI) interaktif modda başlatılıyor...\n")
            time.sleep(1)
            cli_interactive_menu()
            sys.exit(0)
            
        try:
            root = tk.Tk()
            app = APRSManagerGUI(root)
            root.mainloop()
        except Exception as e:
            print(f"\033[91mGrafik arayüzü başlatılamadı: {e}\033[0m")
            print("Yönetici terminal üzerinden (CLI) interaktif modda başlatılıyor...\n")
            time.sleep(1)
            cli_interactive_menu()

if __name__ == '__main__':
    main()
