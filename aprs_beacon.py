#!/usr/bin/env python3
import os
import sys
import socket
import time
import json
import argparse
import subprocess
import shutil
from datetime import datetime

# Path configuration
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'aprs_beacon.log')

def log_message(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')
    except Exception as e:
        print(f"Error writing to log: {e}", file=sys.stderr)

def dec2deg_lat(lat):
    direction = 'N' if lat >= 0 else 'S'
    lat = abs(lat)
    degrees = int(lat)
    minutes = (lat - degrees) * 60.0
    return f"{degrees:02d}{minutes:05.2f}{direction}"

def dec2deg_lon(lon):
    direction = 'E' if lon >= 0 else 'W'
    lon = abs(lon)
    degrees = int(lon)
    minutes = (lon - degrees) * 60.0
    return f"{degrees:03d}{minutes:05.2f}{direction}"

def generate_aprs_passcode(callsign):
    callsign = callsign.upper().split('-')[0]
    hash_val = 0x73e2
    for i in range(0, len(callsign), 2):
        char1 = ord(callsign[i]) << 8
        char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
        hash_val ^= (char1 + char2)
    return hash_val & 0x7fff

def get_termux_gps():
    # Check if termux-location command is available
    if not shutil.which('termux-location'):
        log_message("HATA: 'termux-location' komutu bulunamadı. Lütfen Termux:API uygulamasını telefona kurun ve Termux içinde 'pkg install termux-api' komutunu çalıştırın.")
        return None
    
    log_message("Termux:API kullanılarak GPS uydularından canlı konum alınıyor...")
    try:
        # Run termux-location command with 10 second timeout
        result = subprocess.run(['termux-location', '-p', 'gps'], capture_output=True, text=True, timeout=12)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if 'latitude' in data and 'longitude' in data:
                return float(data['latitude']), float(data['longitude'])
    except subprocess.TimeoutExpired:
        log_message("HATA: GPS konumu alma zaman aşımına uğradı (GPS uydusu aranıyor veya konum kapalı olabilir).")
    except Exception as e:
        log_message(f"HATA: Termux GPS konumu okunamadı: {e}")
    return None

def get_coordinates(config):
    # If Termux live GPS is requested and we are on Android
    if config.get('use_termux_gps', False):
        gps = get_termux_gps()
        if gps:
            return gps
        else:
            log_message("UYARI: Canlı GPS alınamadı. config.json içerisindeki statik konum kullanılacak.")
            
    return float(config['latitude']), float(config['longitude'])

def send_beacon(config):
    callsign = config['callsign'].upper()
    passcode = config.get('passcode')
    if not passcode:
        passcode = generate_aprs_passcode(callsign)
    
    server = config.get('server', 'rotate.aprs2.net')
    port = int(config.get('port', 14580))
    
    # Get coordinates (static or live Termux GPS)
    coords = get_coordinates(config)
    if not coords:
        log_message("HATA: Geçerli koordinat bulunamadı. Gönderim iptal edildi.")
        return False
        
    lat, lon = coords
    symbol_table = config.get('symbol_table', '/')
    symbol_code = config.get('symbol_code', '-')
    comment = config.get('comment', 'Linux Background APRS Beacon')
    
    lat_str = dec2deg_lat(lat)
    lon_str = dec2deg_lon(lon)
    
    packet = f"{callsign}>APRS,TCPIP*:!{lat_str}{symbol_table}{lon_str}{symbol_code}{comment}"
    
    log_message(f"APRS-IS sunucusuna bağlanılıyor ({server}:{port})...")
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect((server, port))
        
        greeting = s.recv(1024).decode('utf-8', errors='ignore').strip()
        log_message(f"Sunucu Karşılama Mesajı: {greeting}")
        
        login_str = f"user {callsign} pass {passcode} vers PyAPRSBeacon 1.0 filter b/{callsign}\r\n"
        s.sendall(login_str.encode('utf-8'))
        
        response = s.recv(1024).decode('utf-8', errors='ignore').strip()
        log_message(f"Sunucu Yanıtı: {response}")
        
        if "verified" not in response.lower() and "unverified" in response.lower():
            log_message("UYARI: Yetkilendirme doğrulanamadı! Lütfen çağrı işaretinizi kontrol edin.")
        
        log_message(f"Paket Gönderiliyor: {packet}")
        s.sendall(f"{packet}\r\n".encode('utf-8'))
        
        time.sleep(2)
        s.close()
        log_message("Paket başarıyla gönderildi ve bağlantı sonlandırıldı.")
        return True
    except Exception as e:
        log_message(f"HATA: Paket gönderilemedi: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="APRS Background Beacon Daemon")
    parser.add_argument('--once', action='store_true', help="Send a single beacon and exit")
    args = parser.parse_args()
    
    if not os.path.exists(CONFIG_FILE):
        print(f"Hata: Yapılandırma dosyası ({CONFIG_FILE}) bulunamadı.", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Hata: Yapılandırma dosyası okunamadı: {e}", file=sys.stderr)
        sys.exit(1)
        
    if args.once:
        success = send_beacon(config)
        sys.exit(0 if success else 1)
        
    interval = int(config.get('interval_minutes', 5)) * 60
    log_message("APRS Beacon Servisi başlatıldı.")
    
    while True:
        # Reload configuration on each interval so changes are picked up without restarting
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass # Keep previous config if read fails
            
        send_beacon(config)
        log_message(f"{config.get('interval_minutes')} dakika boyunca bekleniyor...")
        time.sleep(interval)

if __name__ == '__main__':
    main()
