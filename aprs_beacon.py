#!/usr/bin/env python3
import os
import sys
import socket
import time
import json
import argparse
import platform
import select
import math
from datetime import datetime

# Path configuration
CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
LOG_FILE = os.path.join(CONFIG_DIR, 'aprs_beacon.log')
STATE_FILE = os.path.join(CONFIG_DIR, '.aprs_beacon_state')

# Telemetry state
telemetry_seq = 0
telemetry_defs_sent = False

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

def get_cpu_temp():
    try:
        if platform.system() == 'Linux':
            if os.path.exists('/sys/class/thermal/thermal_zone0/temp'):
                with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
                    return int(float(f.read().strip()) / 1000.0)
    except Exception:
        pass
    return 0

def get_system_load():
    try:
        if hasattr(os, 'getloadavg'):
            return int(os.getloadavg()[0] * 10)
    except Exception:
        pass
    return 0

def get_free_mem():
    try:
        if platform.system() == 'Linux' and os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if 'MemAvailable' in line or 'MemFree' in line:
                        return int(int(line.split()[1]) / 1024)
    except Exception:
        pass
    return 0

def get_free_disk():
    try:
        if hasattr(os, 'statvfs'):
            stat = os.statvfs('/')
            return int((stat.f_bavail * stat.f_frsize) / (1024 * 1024 * 1024))
    except Exception:
        pass
    return 0

def send_telemetry_defs(s, callsign):
    dest_call = callsign.upper().ljust(9, ' ')
    
    # 1. Parameter Names (PARM)
    parm_pkt = f"{callsign.upper()}>APRS,TCPIP*::{dest_call}:PARM.CpuTemp,Load,FreeMem,FreeDisk,Null"
    s.sendall(f"{parm_pkt}\r\n".encode('utf-8'))
    time.sleep(0.5)
    
    # 2. Units (UNIT)
    unit_pkt = f"{callsign.upper()}>APRS,TCPIP*::{dest_call}:UNIT.C,x0.1,MB,GB,Null"
    s.sendall(f"{unit_pkt}\r\n".encode('utf-8'))
    time.sleep(0.5)
    
    # 3. Equations (EQNS) - Using linear scaling: raw value equals output value
    eqns_pkt = f"{callsign.upper()}>APRS,TCPIP*::{dest_call}:EQNS.0,1,0,0,1,0,0,1,0,0,1,0,0,1,0"
    s.sendall(f"{eqns_pkt}\r\n".encode('utf-8'))
    time.sleep(0.5)
    
    log_message("Telemetri tanımlama paketleri (PARM, UNIT, EQNS) gönderildi.")

def send_telemetry_data(s, callsign):
    global telemetry_seq
    cpu = get_cpu_temp()
    load = get_system_load()
    mem = get_free_mem()
    disk = get_free_disk()
    
    seq_str = f"{telemetry_seq:03d}"
    cpu_str = f"{min(999, max(0, cpu)):03d}"
    load_str = f"{min(999, max(0, load)):03d}"
    mem_str = f"{min(999, max(0, mem)):03d}"
    disk_str = f"{min(999, max(0, disk)):03d}"
    
    pkt = f"{callsign.upper()}>APRS,TCPIP*:T#{seq_str},{cpu_str},{load_str},{mem_str},{disk_str},000,00000000"
    log_message(f"Telemetri paketi gönderiliyor: {pkt}")
    s.sendall(f"{pkt}\r\n".encode('utf-8'))
    
    telemetry_seq = (telemetry_seq + 1) % 1000

def get_next_orbit_step():
    step = 0
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                state = json.load(f)
                step = state.get('orbit_step', 0)
        except Exception:
            pass
    
    next_step = (step + 1) % 12
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump({'orbit_step': next_step}, f)
    except Exception:
        pass
    return step

def get_orbit_coordinates(center_lat, center_lon, step, total_steps=12, radius_km=0.6):
    angle = (2 * math.pi * step) / total_steps
    lat_offset = (radius_km / 111.0) * math.cos(angle)
    lon_offset = (radius_km / (111.0 * math.cos(math.radians(center_lat)))) * math.sin(angle)
    return center_lat + lat_offset, center_lon + lon_offset

def make_object_packet(callsign, obj_name, lat, lon, symbol_table, symbol_code, comment):
    obj_name_padded = obj_name.upper()[:9].ljust(9, ' ')
    lat_str = dec2deg_lat(lat)
    lon_str = dec2deg_lon(lon)
    packet = f"{callsign.upper()}>APRS,TCPIP*:;{obj_name_padded}*{lat_str}{symbol_table}{lon_str}{symbol_code}{comment}"
    return packet

def parse_aprs_message(line):
    if '::' not in line:
        return None
    
    parts = line.split('::', 1)
    sender = parts[0].split('>')[0].strip()
    
    msg_part = parts[1]
    if ':' not in msg_part:
        return None
        
    receiver_part, message_content = msg_part.split(':', 1)
    receiver = receiver_part.strip()
    
    ack_id = None
    if '{' in message_content:
        message_content, ack_part = message_content.rsplit('{', 1)
        ack_id = ack_part.strip()
        
    return {
        'sender': sender,
        'receiver': receiver,
        'message': message_content.strip(),
        'ack_id': ack_id
    }

def send_aprs_message(s, sender, receiver, text, ack_id=None):
    receiver_padded = receiver.upper()[:9].ljust(9, ' ')
    if ack_id:
        packet = f"{sender.upper()}>APRS,TCPIP*::{receiver_padded}:{text}{{{ack_id}"
    else:
        packet = f"{sender.upper()}>APRS,TCPIP*::{receiver_padded}:{text}"
    log_message(f"Mesaj Gönderiliyor: {packet}")
    s.sendall(f"{packet}\r\n".encode('utf-8'))

def send_aprs_ack(s, sender, receiver, ack_id):
    receiver_padded = receiver.upper()[:9].ljust(9, ' ')
    packet = f"{sender.upper()}>APRS,TCPIP*::{receiver_padded}:ack{ack_id}"
    log_message(f"ACK Gönderiliyor: {packet}")
    s.sendall(f"{packet}\r\n".encode('utf-8'))

def handle_message(s, config, msg):
    sender = msg['sender']
    text = msg['message'].lower().strip()
    ack_id = msg['ack_id']
    callsign = config['callsign'].upper()
    
    if ack_id:
        send_aprs_ack(s, callsign, sender, ack_id)
        time.sleep(0.5)
        
    log_message(f"Mesaj alındı: {sender} -> {text}")
    
    reply = None
    if text == 'ping':
        reply = "pong! [Antigravity APRS Bot Aktif]"
    elif text in ['status', 'stats']:
        cpu = get_cpu_temp()
        load = get_system_load() / 10.0
        mem = get_free_mem()
        disk = get_free_disk()
        reply = f"Sistem Durumu: CPU Temp={cpu}C, Load={load}, FreeMem={mem}MB, FreeDisk={disk}GB"
    elif text == 'uptime':
        uptime_str = "Bilinmiyor"
        if platform.system() == 'Linux':
            try:
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.readline().split()[0])
                    uptime_str = f"{int(uptime_seconds // 3600)} saat, {int((uptime_seconds % 3600) // 60)} dk"
            except Exception:
                pass
        else:
            uptime_str = f"Windows ({platform.processor()})"
        reply = f"Sistem Uptime: {uptime_str}"
    elif text in ['help', 'yardim', 'yardım']:
        reply = "Komutlar: ping, status, uptime, help"
    else:
        reply = "Bilinmeyen komut. Yardim icin 'help' yazin."
        
    if reply:
        send_aprs_message(s, callsign, sender, reply)

def send_all_packets(s, config):
    global telemetry_defs_sent
    callsign = config['callsign'].upper()
    lat = float(config['latitude'])
    lon = float(config['longitude'])
    symbol_table = config.get('symbol_table', '/')
    symbol_code = config.get('symbol_code', '-')
    comment = config.get('comment', 'Linux Background APRS Beacon')
    
    lat_str = dec2deg_lat(lat)
    lon_str = dec2deg_lon(lon)
    
    # 1. Base Station Position Beacon
    packet = f"{callsign}>APRS,TCPIP*:!{lat_str}{symbol_table}{lon_str}{symbol_code}{comment}"
    log_message(f"Konum paketi gönderiliyor: {packet}")
    s.sendall(f"{packet}\r\n".encode('utf-8'))
    time.sleep(0.5)
    
    # 2. Telemetry (if enabled)
    if config.get('send_telemetry', False):
        if not telemetry_defs_sent:
            send_telemetry_defs(s, callsign)
            telemetry_defs_sent = True
        send_telemetry_data(s, callsign)
        time.sleep(0.5)
        
    # 3. Orbiting Drone Animation (if enabled)
    if config.get('orbit_animation', False):
        step = get_next_orbit_step()
        orbit_lat, orbit_lon = get_orbit_coordinates(lat, lon, step)
        obj_name = f"DRN-{callsign.split('-')[0]}"[:9]
        obj_packet = make_object_packet(callsign, obj_name, orbit_lat, orbit_lon, "/", "'", f"Yapay Drone Yonetimi Step {step+1}/12")
        log_message(f"Drone animasyon paketi gönderiliyor: {obj_packet}")
        s.sendall(f"{obj_packet}\r\n".encode('utf-8'))
        time.sleep(0.5)

def send_beacon_once(config):
    callsign = config['callsign'].upper()
    passcode = config.get('passcode')
    if not passcode:
        passcode = generate_aprs_passcode(callsign)
    
    server = config.get('server', 'rotate.aprs2.net')
    port = int(config.get('port', 14580))
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(15)
        s.connect((server, port))
        
        greeting = s.recv(1024).decode('utf-8', errors='ignore').strip()
        login_str = f"user {callsign} pass {passcode} vers PyAPRSBeacon 2.0 filter b/{callsign}\r\n"
        s.sendall(login_str.encode('utf-8'))
        
        s.recv(1024) # Skip server response
        
        send_all_packets(s, config)
        
        time.sleep(2)
        s.close()
        return True
    except Exception as e:
        log_message(f"HATA: Tekil gönderim başarısız: {e}")
        return False

def run_persistent_client(config):
    callsign = config['callsign'].upper()
    passcode = config.get('passcode')
    if not passcode:
        passcode = generate_aprs_passcode(callsign)
    
    server = config.get('server', 'rotate.aprs2.net')
    port = int(config.get('port', 14580))
    interval = int(config.get('interval_minutes', 5)) * 60
    
    log_message("İnteraktif APRS Botu ve Arka Plan Servisi başlatılıyor...")
    
    buffer = ""
    last_beacon = 0
    s = None
    
    while True:
        try:
            if s is None:
                log_message(f"APRS-IS sunucusuna bağlanılıyor ({server}:{port})...")
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(15)
                s.connect((server, port))
                
                greeting = s.recv(1024).decode('utf-8', errors='ignore').strip()
                log_message(f"Sunucu Karşılama Mesajı: {greeting}")
                
                login_str = f"user {callsign} pass {passcode} vers PyAPRSBeacon 2.0 filter b/{callsign}\r\n"
                s.sendall(login_str.encode('utf-8'))
                
                response = s.recv(1024).decode('utf-8', errors='ignore').strip()
                log_message(f"Sunucu Yanıtı: {response}")
                
                s.setblocking(0) # Non-blocking mode for select
                buffer = ""
                # Send immediately upon connection
                send_all_packets(s, config)
                last_beacon = time.time()
            
            # Read / Write polling
            ready_to_read, _, _ = select.select([s], [], [], 1.0)
            
            if ready_to_read:
                data = s.recv(4096)
                if not data:
                    log_message("Bağlantı sunucu tarafından kesildi. Yeniden bağlaniliyor...")
                    s.close()
                    s = None
                    time.sleep(5)
                    continue
                
                buffer += data.decode('utf-8', errors='ignore')
                while '\r\n' in buffer:
                    line, buffer = buffer.split('\r\n', 1)
                    line = line.strip()
                    if line.startswith('#'):
                        continue
                    if line:
                        msg = parse_aprs_message(line)
                        if msg and msg['receiver'].split('-')[0] == callsign.split('-')[0]:
                            handle_message(s, config, msg)
            
            # Check if time to send beacon
            if time.time() - last_beacon >= interval:
                # Reload config in case it changed in runtime
                try:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                except Exception:
                    pass
                send_all_packets(s, config)
                last_beacon = time.time()
                
        except (socket.error, select.error) as e:
            log_message(f"Soket hatası: {e}. 10 saniye içinde yeniden bağlanılıyor...")
            if s:
                try:
                    s.close()
                except Exception:
                    pass
                s = None
            time.sleep(10)
        except Exception as e:
            log_message(f"Beklenmeyen hata: {e}")
            time.sleep(5)

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
        success = send_beacon_once(config)
        sys.exit(0 if success else 1)
        
    if config.get('interactive_bot', False):
        run_persistent_client(config)
    else:
        # Standard loop, connect and disconnect on each interval
        interval = int(config.get('interval_minutes', 5)) * 60
        log_message("APRS Beacon Servisi (Standart Döngü) başlatıldı.")
        while True:
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except Exception:
                pass
            send_beacon_once(config)
            log_message(f"{config.get('interval_minutes')} dakika boyunca bekleniyor...")
            time.sleep(interval)

if __name__ == '__main__':
    main()
