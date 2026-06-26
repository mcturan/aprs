#!/usr/bin/env python3
import os
import sys
import socket
import time
import json
import argparse
import subprocess
import threading
from datetime import datetime, timedelta


# Path configuration
BASE_DIR = os.path.expanduser('~/.aprs-beacon')
PROFILES_DIR = os.path.join(BASE_DIR, 'profiles')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

os.makedirs(PROFILES_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Migration for older configuration
old_config = os.path.join(BASE_DIR, 'config.json')
old_log = os.path.join(BASE_DIR, 'aprs_beacon.log')
if os.path.exists(old_config):
    try:
        import shutil
        shutil.move(old_config, os.path.join(PROFILES_DIR, 'default.json'))
        if os.path.exists(old_log):
            shutil.move(old_log, os.path.join(LOGS_DIR, 'default.log'))
    except Exception as e:
        print(f"Migration error: {e}", file=sys.stderr)

# Parse profile name
PROFILE_NAME = 'default'
for idx, arg in enumerate(sys.argv):
    if arg == '--profile' and idx + 1 < len(sys.argv):
        PROFILE_NAME = sys.argv[idx + 1]

CONFIG_FILE = os.path.join(PROFILES_DIR, f"{PROFILE_NAME}.json")
LOG_FILE = os.path.join(LOGS_DIR, f"{PROFILE_NAME}.log")

def clean_old_logs(log_file):
    if not os.path.exists(log_file):
        return
    try:
        thirty_days_ago = datetime.now() - timedelta(days=30)
        new_lines = []
        changed = False
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                if line_stripped.startswith('[') and ']' in line_stripped:
                    try:
                        end_idx = line_stripped.index(']')
                        date_str = line_stripped[1:end_idx]
                        line_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        if line_date < thirty_days_ago:
                            changed = True
                            continue
                    except Exception:
                        pass
                new_lines.append(line)
        if changed:
            with open(log_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
    except Exception as e:
        print(f"Error cleaning old logs: {e}", file=sys.stderr)

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

def send_aprs_raw_packet(config, packet):
    callsign = config['callsign'].upper()
    passcode = config.get('passcode')
    if not passcode:
        passcode = generate_aprs_passcode(callsign)
    
    primary_server = config.get('server', 'rotate.aprs2.net')
    port = int(config.get('port', 14580))
    
    servers_to_try = [primary_server]
    backup_servers = ['euro.aprs2.net', 'noam.aprs2.net', 'asia.aprs2.net']
    for b_srv in backup_servers:
        if b_srv != primary_server:
            servers_to_try.append(b_srv)
            
    for server in servers_to_try:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(10)
            s.connect((server, port))
            
            greeting = s.recv(1024).decode('utf-8', errors='ignore').strip()
            
            login_str = f"user {callsign} pass {passcode} vers PyAPRSBeacon 1.0 filter b/{callsign}\r\n"
            s.sendall(login_str.encode('utf-8'))
            
            response = s.recv(1024).decode('utf-8', errors='ignore').strip()
            
            if "verified" not in response.lower() and "unverified" in response.lower():
                log_message("WARNING: Authentication unverified! Please double-check your passcode and callsign.")
                
            log_message(f"Sending APRS Packet: {packet} via {server}")
            s.sendall(f"{packet}\r\n".encode('utf-8'))
            
            time.sleep(2)
            s.close()
            return True
        except Exception as e:
            log_message(f"ERROR: Failed to send packet via {server}: {e}. Trying backup server if available...")
            
    log_message("ERROR: All APRS servers are unreachable.")
    return False

def send_aprs_thursday_sequence(config, today_str):
    callsign = config['callsign'].upper()
    log_message("[APRS Thursday] Starting. Subscribing to ANSRVR group...")
    
    thursday_msg = config.get('aprs_thursday_msg', 'CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY').strip()
    if not thursday_msg:
        thursday_msg = 'CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY'
        
    # Message packet format: SENDER>APRS,TCPIP*::RECIPIENT:MESSAGE
    msg_packet1 = f"{callsign}>APRS,TCPIP*::ANSRVR   :{thursday_msg}"
    
    success = send_aprs_raw_packet(config, msg_packet1)
    if success:
        log_message(f"[APRS Thursday] Join message sent: {thursday_msg}")
        log_message("[APRS Thursday] Waiting 5 minutes (300 seconds)...")
        time.sleep(300)
        
        msg_packet2 = f"{callsign}>APRS,TCPIP*::ANSRVR   :U HOTG"
        success2 = send_aprs_raw_packet(config, msg_packet2)
        if success2:
            log_message("[APRS Thursday] Leave message sent: U HOTG")
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    current_config = json.load(f)
                current_config['last_aprs_thursday_sent'] = today_str
                with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                    json.dump(current_config, f, indent=4)
                log_message(f"[APRS Thursday] State saved successfully: {today_str}")
            except Exception as e:
                log_message(f"[APRS Thursday] ERROR: Failed to save state: {e}")
        else:
            log_message("[APRS Thursday] ERROR: Failed to send leave message.")
    else:
        log_message("[APRS Thursday] ERROR: Failed to send join message. Retrying in next cycle.")
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
            current_config['last_aprs_thursday_sent'] = ""
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(current_config, f, indent=4)
        except:
            pass

def send_beacon(config):
    callsign = config['callsign'].upper()
    
    lat = float(config.get('latitude', 0.0))
    lon = float(config.get('longitude', 0.0))
        
    log_message(f"Beacon Location Info: Latitude={lat}, Longitude={lon}")
    
    symbol_table = config.get('symbol_table', '/')
    symbol_code = config.get('symbol_code', '-')
    comment = config.get('comment', 'APRS Background Beacon')
    
    lat_str = dec2deg_lat(lat)
    lon_str = dec2deg_lon(lon)
    
    packet = f"{callsign}>APRS,TCPIP*:!{lat_str}{symbol_table}{lon_str}{symbol_code}{comment}"
    
    log_message("Sending location beacon...")
    success = send_aprs_raw_packet(config, packet)
    if success:
        log_message("Packet successfully sent. Connection closed.")
        return True
    return False

def main():
    parser = argparse.ArgumentParser(description="APRS Background Beacon Daemon")
    parser.add_argument('--once', action='store_true', help="Send a single beacon and exit")
    parser.add_argument('--profile', type=str, default='default', help="Profile name to run")
    args = parser.parse_args()
    
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: Configuration file ({CONFIG_FILE}) not found.", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Error: Failed to read configuration file: {e}", file=sys.stderr)
        sys.exit(1)
    if args.once:
        success = send_beacon(config)
        sys.exit(0 if success else 1)
        
    clean_old_logs(LOG_FILE)
    interval = int(config.get('interval_minutes', 5)) * 60
    log_message("APRS Beacon Daemon started.")
    last_cleanup_time = time.time()
    
    while True:
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass
            
        now_ts = time.time()
        if now_ts - last_cleanup_time > 86400:
            clean_old_logs(LOG_FILE)
            last_cleanup_time = now_ts
            
        if config.get('aprs_thursday', False):
            now = datetime.now()
            if now.weekday() == 3: # Thursday
                today_str = now.strftime('%Y-%m-%d')
                if config.get('last_aprs_thursday_sent', '') != today_str:
                    sched_time = config.get('aprs_thursday_time', '20:00')
                    try:
                        sched_hour, sched_min = map(int, sched_time.split(':'))
                    except Exception:
                        sched_hour, sched_min = 20, 0
                        
                    if now.hour > sched_hour or (now.hour == sched_hour and now.minute >= sched_min):
                        try:
                            config['last_aprs_thursday_sent'] = today_str
                            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                                json.dump(config, f, indent=4)
                            
                            threading.Thread(target=send_aprs_thursday_sequence, args=(config, today_str), daemon=True).start()
                        except Exception as e:
                            log_message(f"Thursday check error: {e}")
            
        send_beacon(config)
        log_message(f"Waiting for {config.get('interval_minutes')} minute(s)...")
        time.sleep(interval)

if __name__ == '__main__':
    main()
