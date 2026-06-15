#!/usr/bin/env python3
import os
import sys
import json
import socket
import subprocess
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, request, render_template

# Ensure path to local modules is set
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import configuration constants and helper functions from aprs_manager
from aprs_manager import (
    BASE_DIR, PROFILES_DIR, LOGS_DIR,
    get_profiles, save_profile, delete_profile_files,
    generate_aprs_passcode, send_aprs_message, get_packet_count,
    is_service_enabled, set_service_enabled
)

app = Flask(__name__)

# Subprocess tracking for Docker / Non-systemd environments
PIDS_FILE = os.path.join(BASE_DIR, 'pids.json')
chat_history = {}      # callsign -> list of message dicts
active_listeners = {}  # callsign -> { 'thread': t, 'socket': s, 'last_poll': timestamp }

def get_running_subprocesses():
    if not os.path.exists(PIDS_FILE):
        return {}
    try:
        with open(PIDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {}

def save_running_subprocesses(pids):
    try:
        with open(PIDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pids, f, indent=4)
    except:
        pass

def is_subprocess_running(profile_name):
    pids = get_running_subprocesses()
    pid = pids.get(profile_name)
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        if profile_name in pids:
            del pids[profile_name]
            save_running_subprocesses(pids)
        return False

def is_docker():
    return os.path.exists('/.dockerenv') or os.environ.get('DOCKER_MODE') == 'true'

def is_profile_running(profile_name):
    if is_docker():
        return is_subprocess_running(profile_name)
    try:
        res = subprocess.run(['systemctl', '--user', 'is-active', f'aprs-beacon@{profile_name}.service'], capture_output=True, text=True)
        return res.stdout.strip() == 'active'
    except:
        return is_subprocess_running(profile_name)

def start_profile_service(profile_name):
    if is_docker():
        if is_subprocess_running(profile_name):
            return True
        log_file = os.path.join(LOGS_DIR, f'{profile_name}.log')
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        beacon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'aprs_beacon.py')
        if not os.path.exists(beacon_path):
            beacon_path = os.path.join(BASE_DIR, 'aprs_beacon.py')
            
        with open(log_file, 'a') as log_out:
            proc = subprocess.Popen(
                [sys.executable, beacon_path, '--profile', profile_name],
                stdout=log_out,
                stderr=log_out,
                start_new_session=True
            )
        pids = get_running_subprocesses()
        pids[profile_name] = proc.pid
        save_running_subprocesses(pids)
        return True
    else:
        try:
            from aprs_manager import ensure_linux_systemd_template
            ensure_linux_systemd_template()
            subprocess.run(['systemctl', '--user', 'enable', f'aprs-beacon@{profile_name}.service'], check=True)
            subprocess.run(['systemctl', '--user', 'start', f'aprs-beacon@{profile_name}.service'], check=True)
            return True
        except:
            # Fallback to subprocess
            return start_profile_service(profile_name)

def stop_profile_service(profile_name):
    if is_docker():
        pids = get_running_subprocesses()
        pid = pids.get(profile_name)
        if pid:
            try:
                import signal
                os.kill(pid, signal.SIGTERM)
                time.sleep(0.5)
            except OSError:
                pass
            if profile_name in pids:
                del pids[profile_name]
                save_running_subprocesses(pids)
        return True
    else:
        try:
            subprocess.run(['systemctl', '--user', 'stop', f'aprs-beacon@{profile_name}.service'])
            subprocess.run(['systemctl', '--user', 'disable', f'aprs-beacon@{profile_name}.service'])
            return True
        except:
            return stop_profile_service(profile_name)

# --- Chat Listener Management ---
def add_chat_msg(my_callsign, sender, text):
    my_callsign = my_callsign.upper()
    if my_callsign not in chat_history:
        chat_history[my_callsign] = []
    chat_history[my_callsign].append({
        "timestamp": datetime.now().strftime('%H:%M:%S'),
        "sender": sender,
        "text": text
    })

def parse_incoming_line(my_callsign, line):
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
                if recipient.upper() == my_callsign.upper():
                    add_chat_msg(my_callsign, sender, msg_text)
        except:
            pass

def chat_listener_worker(callsign, passcode):
    callsign = callsign.upper()
    server = "rotate.aprs2.net"
    port = 14580
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10.0)
        sock.connect((server, port))
        
        if callsign in active_listeners:
            active_listeners[callsign]['socket'] = sock
            
        sock.recv(1024)
        login_str = f"user {callsign} pass {passcode} vers PyAPRSWeb 1.0 filter b/{callsign}\r\n"
        sock.sendall(login_str.encode('utf-8'))
        sock.recv(1024)
        
        add_chat_msg(callsign, "SYSTEM", f"Connected as {callsign}. Real-time chat active.")
        
        sock.settimeout(None)
        buffer = ""
        while callsign in active_listeners:
            # Garbage collect if client hasn't polled in 30 seconds
            if time.time() - active_listeners[callsign]['last_poll'] > 30.0:
                add_chat_msg(callsign, "SYSTEM", "Chat connection closed due to inactivity.")
                break
                
            data = sock.recv(4096)
            if not data:
                break
            buffer += data.decode('utf-8', errors='ignore')
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                parse_incoming_line(callsign, line)
    except Exception as e:
        add_chat_msg(callsign, "SYSTEM", f"Connection closed: {e}")
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass
        if callsign in active_listeners:
            del active_listeners[callsign]

def manage_chat_listener(callsign, passcode):
    callsign = callsign.upper()
    if callsign in active_listeners:
        active_listeners[callsign]['last_poll'] = time.time()
        return
        
    t = threading.Thread(target=chat_listener_worker, args=(callsign, passcode), daemon=True)
    active_listeners[callsign] = {
        'thread': t,
        'socket': None,
        'last_poll': time.time()
    }
    t.start()

# --- Flask Endpoints ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_global_status():
    profiles = get_profiles()
    active_count = sum(1 for name in profiles.keys() if is_profile_running(name))
    
    # Check APRS server latency
    latency = "Offline"
    try:
        start = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(("rotate.aprs2.net", 14580))
        sock.close()
        latency = f"{int((time.time() - start) * 1000)}ms"
    except:
        pass
        
    return jsonify({
        "total_profiles": len(profiles),
        "active_beacons": active_count,
        "latency": latency
    })

@app.route('/api/profiles')
def api_profiles():
    profiles = get_profiles()
    result = []
    for name, data in profiles.items():
        running = is_profile_running(name)
        enabled = is_service_enabled(name)
        packets = get_packet_count(name)
        
        result.append({
            "name": name,
            "callsign": data.get("callsign", ""),
            "passcode": data.get("passcode", ""),
            "latitude": data.get("latitude", 0),
            "longitude": data.get("longitude", 0),
            "symbol": data.get("symbol_code", "X"),
            "comment": data.get("comment", ""),
            "interval": data.get("interval_minutes", 5),
            "aprs_thursday": data.get("aprs_thursday", False),
            "aprs_thursday_time": data.get("aprs_thursday_time", "20:00"),
            "aprs_thursday_msg": data.get("aprs_thursday_msg", "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY"),
            "running": running,
            "autostart": enabled,
            "packets_sent": packets
        })
    return jsonify(result)

@app.route('/api/profiles/save', methods=['POST'])
def api_save_profile():
    req = request.json
    name = req.get("name", "").strip().lower()
    callsign = req.get("callsign", "").strip().upper()
    passcode_in = req.get("passcode", "")
    lat = float(req.get("latitude", 0))
    lon = float(req.get("longitude", 0))
    comment = req.get("comment", "").strip() or "APRS Background Beacon"
    symbol = req.get("symbol", "X").strip() or "X"
    interval = int(req.get("interval", 5))
    aprs_thursday = bool(req.get("aprs_thursday", False))
    aprs_thursday_time = req.get("aprs_thursday_time", "20:00").strip()
    aprs_thursday_msg = req.get("aprs_thursday_msg", "").strip() or "CQ HOTG 73 FROM TURKIYE #APRSTHURSDAY"
    
    if not name or not callsign:
        return jsonify({"success": False, "message": "Profile name and callsign are required."}), 400
        
    if not passcode_in:
        passcode = generate_aprs_passcode(callsign)
    else:
        try:
            passcode = int(passcode_in)
        except:
            return jsonify({"success": False, "message": "Invalid passcode format."}), 400

    data = {
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
    
    was_running = is_profile_running(name)
    save_profile(name, data)
    
    # Apply autostart configurations
    autostart = bool(req.get("autostart", False))
    set_service_enabled(name, autostart)
    
    if was_running:
        stop_profile_service(name)
        time.sleep(0.5)
        start_profile_service(name)
        
    return jsonify({"success": True, "message": f"Profile '{name}' saved successfully."})

@app.route('/api/profiles/<name>/delete', methods=['POST'])
def api_delete_profile(name):
    stop_profile_service(name)
    delete_profile_files(name)
    return jsonify({"success": True, "message": f"Profile '{name}' deleted."})

@app.route('/api/profiles/<name>/toggle', methods=['POST'])
def api_toggle_profile(name):
    running = is_profile_running(name)
    if running:
        success = stop_profile_service(name)
        msg = f"Profile '{name}' stopped."
    else:
        success = start_profile_service(name)
        msg = f"Profile '{name}' started."
    return jsonify({"success": success, "message": msg})

@app.route('/api/profiles/<name>/autostart', methods=['POST'])
def api_autostart_profile(name):
    req = request.json
    enable = bool(req.get("enable", False))
    set_service_enabled(name, enable)
    return jsonify({"success": True, "message": f"Autostart {'enabled' if enable else 'disabled'} for '{name}'."})

@app.route('/api/profiles/<name>/logs')
def api_profile_logs(name):
    log_file = os.path.join(LOGS_DIR, f'{name}.log')
    if not os.path.exists(log_file):
        return jsonify({"logs": "No logs found for this profile yet."})
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[-100:]
        return jsonify({"logs": "".join(lines)})
    except Exception as e:
        return jsonify({"logs": f"Error reading logs: {e}"})

@app.route('/api/chat/messages')
def api_chat_messages():
    profile = request.args.get("profile", "").strip().lower()
    profiles = get_profiles()
    if profile not in profiles:
        return jsonify({"success": False, "message": "Profile not found."}), 404
        
    data = profiles[profile]
    callsign = data.get("callsign", "").upper()
    passcode = data.get("passcode")
    if not passcode:
        passcode = generate_aprs_passcode(callsign)
        
    manage_chat_listener(callsign, passcode)
    
    msgs = chat_history.get(callsign, [])
    return jsonify(msgs)

@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    req = request.json
    profile = req.get("profile", "").strip().lower()
    to_callsign = req.get("to_callsign", "").strip().upper()
    message = req.get("message", "").strip()
    
    profiles = get_profiles()
    if profile not in profiles:
        return jsonify({"success": False, "message": "Profile not found."}), 404
        
    data = profiles[profile]
    from_callsign = data.get("callsign", "").upper()
    passcode = data.get("passcode")
    if not passcode:
        passcode = generate_aprs_passcode(from_callsign)
        
    if not to_callsign or not message:
        return jsonify({"success": False, "message": "Recipient and message text are required."}), 400
        
    success, res_msg = send_aprs_message(from_callsign, passcode, to_callsign, message)
    if success:
        add_chat_msg(from_callsign, "YOU", f"To {to_callsign}: {message}")
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "message": res_msg})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
