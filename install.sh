#!/usr/bin/env bash

# Terminal Colors
C_GREEN='\033[92m'
C_YELLOW='\033[93m'
C_BLUE='\033[94m'
C_CYAN='\033[96m'
C_RED='\033[91m'
C_BOLD='\033[1m'
C_RESET='\033[0m'

clear
echo -e "${C_CYAN}${C_BOLD}"
echo "   _   ___  ___  ___   ___                             "
echo "  /_\ | _ \| _ \/ __| | _ ) ___ __ _ __ ___ _ _        "
echo " / _ \|  _/|   /\__ \ | _ \/ -_) _\` / _/ _ \ ' \       "
echo "/_/ \_\_|  |_|_\|___/ |___/\___\__,_\__\___/_||_|      "
echo -e "       Linux/Android APRS Multi-Profile Beacon Setup Wizard${C_RESET}\n"
echo "----------------------------------------------------------------"
echo "This wizard will help you configure your APRS beacon as a"
echo "background service and manage it via the control panel."
echo "----------------------------------------------------------------\n"

# Check and install Python3
if ! command -v python3 &> /dev/null; then
    echo -e "${C_YELLOW}[!] Python3 not found on the system. Installing...${C_RESET}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y python3
    elif [ -d "/data/data/com.termux" ]; then
        pkg update && pkg install -y python python-apt
    else
        echo -e "${C_RED}[!] Error: Python3 could not be installed automatically. Please install it manually.${C_RESET}"
        exit 1
    fi
fi

INSTALL_DIR="$HOME/.aprs-beacon"
PROFILES_DIR="$INSTALL_DIR/profiles"
LOGS_DIR="$INSTALL_DIR/logs"
mkdir -p "$PROFILES_DIR" "$LOGS_DIR"
echo "$(pwd)" > "$INSTALL_DIR/.repo_path"

# Android / Termux Detection
IS_ANDROID=false
if [ -d "/data/data/com.termux" ] || [ -n "$TERMUX_VERSION" ]; then
    IS_ANDROID=true
fi

# GUI Dependencies Installation (for Linux)
HAS_GUI=true
if [ "$IS_ANDROID" = false ]; then
    # Graphic environment check
    if [ -z "$DISPLAY" ]; then
        HAS_GUI=false
        echo -e "${C_YELLOW}[!] Display environment (DISPLAY) not detected. Performing headless install.${C_RESET}"
    fi

    if [ "$HAS_GUI" = true ]; then
        echo -e "${C_BLUE}[i] Checking GUI, System Tray, and Image libraries (pystray, tkinter, pillow)...${C_RESET}"
        if ! python3 -c "import tkinter; import pystray; import PIL" &>/dev/null; then
            echo -e "${C_YELLOW}[!] Required GUI packages are missing. Installing...${C_RESET}"
            if command -v apt-get &> /dev/null; then
                echo -e "${C_BLUE}[i] Administrative privileges (sudo) may be requested:${C_RESET}"
                sudo apt-get update && sudo apt-get install -y python3-tk python3-pystray python3-pil
            else
                echo -e "${C_RED}[!] Error: Package manager (apt-get) not found. Please install python3-tk, python3-pystray, and python3-pil manually.${C_RESET}"
            fi
        else
            echo -e "${C_GREEN}[+] Required GUI packages are ready.${C_RESET}"
        fi
    fi
fi

# 0. Profile Name
echo -e "\n=== 0. Profile Configuration ==="
while true; do
    read -p "Profile Name to Install (e.g. mobile, qth, default) [Default: default]: " PROFILE_NAME
    PROFILE_NAME=$(echo "$PROFILE_NAME" | tr 'A-Z' 'a-z' | xargs)
    if [ -z "$PROFILE_NAME" ]; then
        PROFILE_NAME="default"
    fi
    if [[ "$PROFILE_NAME" =~ ^[a-z0-9_-]+$ ]]; then
        break
    fi
    echo -e "${C_RED}Error: Profile name can only contain lowercase letters, numbers, hyphens, or underscores!${C_RESET}"
done

# 1. Callsign
while true; do
    read -p "1. Callsign (e.g. N0CALL-9): " CALLSIGN
    CALLSIGN=$(echo "$CALLSIGN" | tr 'a-z' 'A-Z' | xargs)
    if [ -n "$CALLSIGN" ]; then
        break
    fi
    echo -e "${C_RED}Error: Callsign cannot be empty!${C_RESET}"
done

# 2. APRS-IS Passcode
read -p "2. Password (APRS-IS Passcode) [Press Enter to calculate automatically]: " PASSCODE
PASSCODE=$(echo "$PASSCODE" | xargs)
if [ -z "$PASSCODE" ]; then
    echo -e "${C_BLUE}[i] Calculating passcode automatically from callsign...${C_RESET}"
    PASSCODE=$(python3 -c "
callsign = '${CALLSIGN}'.split('-')[0]
hash_val = 0x73e2
for i in range(0, len(callsign), 2):
    char1 = ord(callsign[i]) << 8
    char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
    hash_val ^= (char1 + char2)
print(hash_val & 0x7fff)
")
    echo -e "${C_GREEN}[+] Calculated Passcode: $PASSCODE${C_RESET}"
fi

# 3. Status Comment
echo -e "\n3. Status Comment Setting:"
echo -e "  ${C_YELLOW}Tip: Add frequency and tone info at start of message (e.g. 145.550MHz T088)${C_RESET}"
echo -e "  ${C_YELLOW}Tip: Add 'https://' to show a clickable link on the map (e.g. https://example.com)${C_RESET}"
read -p "Status Comment [Default: APRS Background Beacon]: " COMMENT
COMMENT=$(echo "$COMMENT" | xargs)
if [ -z "$COMMENT" ]; then
    COMMENT="APRS Background Beacon"
fi

# 4. Symbol
echo -e "\n4. Select Symbol to Display on Map:"
echo "  1) Helicopter (X) [Default]"
echo "  2) Car / Vehicle (>)"
echo "  3) Pedestrian / Hiker ([)"
echo "  4) House / QTH Station (-)"
echo "  5) Fixed Radio / Station (#)"
echo "  6) Other (Enter your own character)"
read -p "Choice [1-6]: " SYM_CHOICE
SYM_CHOICE=$(echo "$SYM_CHOICE" | xargs)

SYMBOL_TABLE="/"
SYMBOL_CODE="X"

case "$SYM_CHOICE" in
    2) SYMBOL_CODE=">" ;;
    3) SYMBOL_CODE="[" ;;
    4) SYMBOL_CODE="-" ;;
    5) SYMBOL_CODE="#" ;;
    6) 
        read -p "Enter Symbol Character (e.g. > or [ or X): " CUSTOM_SYM
        SYMBOL_CODE=$(echo "$CUSTOM_SYM" | xargs)
        if [ -z "$SYMBOL_CODE" ]; then
            SYMBOL_CODE="X"
        fi
        ;;
    *) SYMBOL_CODE="X" ;;
esac

USE_TERMUX_GPS="false"
LATITUDE=""
LONGITUDE=""

if [ "$IS_ANDROID" = true ]; then
    echo -e "\n5. Location Setting (Android):"
    echo -e "  ${C_YELLOW}Tip: To use the phone's internal GPS, Termux:API app must be installed and location permission granted.${C_RESET}"
    read -p "Do you want to fetch phone GPS location automatically? [Y/n]: " OPT_GPS
    OPT_GPS=$(echo "$OPT_GPS" | tr 'A-Z' 'a-z' | xargs)
    if [ "$OPT_GPS" != "n" ]; then
        USE_TERMUX_GPS="true"
        LATITUDE="0.0"
        LONGITUDE="0.0"
        echo -e "${C_GREEN}[+] Internal GPS enabled. Skipping manual coordinates.${C_RESET}"
    fi
fi

if [ "$USE_TERMUX_GPS" = "false" ]; then
    # 5. Coordinates
    read -p "5. Do you want to automatically detect your coordinates via IP? [Y/n]: " AUTO_LOC
    AUTO_LOC=$(echo "$AUTO_LOC" | tr 'A-Z' 'a-z' | xargs)

    if [ "$AUTO_LOC" != "n" ]; then
        echo -e "${C_BLUE}[i] Detecting coordinates via IP...${C_RESET}"
        IP_LOC=$(python3 -c "
import urllib.request, json
urls = ['http://ip-api.com/json', 'https://ipapi.co/json/']
for url in urls:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as r:
            d = json.loads(r.read().decode('utf-8'))
            if d.get('status') == 'success' or 'latitude' in d:
                lat = d.get('lat') or d.get('latitude')
                lon = d.get('lon') or d.get('longitude')
                city = d.get('city') or 'Unknown'
                country = d.get('country_name') or d.get('country') or 'Unknown'
                print(f'{lat},{lon},{city},{country}')
                break
    except:
        continue
")
        if [ -n "$IP_LOC" ]; then
            IFS=',' read -r LAT LON CITY COUNTRY <<< "$IP_LOC"
            echo -e "${C_GREEN}[+] Automatically Detected Location: $CITY, $COUNTRY ($LAT, $LON)${C_RESET}"
            LATITUDE="$LAT"
            LONGITUDE="$LON"
        else
            echo -e "${C_RED}[!] IP location detection failed.${C_RESET}"
        fi
    fi

    if [ -z "$LATITUDE" ] || [ -z "$LONGITUDE" ]; then
        echo -e "${C_BLUE}[i] Opening OpenStreetMap in browser to help find coordinates...${C_RESET}"
        python3 -m webbrowser "https://www.openstreetmap.org" &>/dev/null &
        
        echo -e "${C_YELLOW}[!] Please enter coordinates manually (copy latitude/longitude from map):${C_RESET}"
        while true; do
            read -p "  Latitude (e.g. 41.037002): " LATITUDE
            LATITUDE=$(echo "$LATITUDE" | xargs)
            if python3 -c "float('$LATITUDE')" &>/dev/null; then
                break
            fi
            echo -e "${C_RED}Error: Invalid latitude value!${C_RESET}"
        done
        while true; do
            read -p "  Longitude (e.g. 28.985012): " LONGITUDE
            LONGITUDE=$(echo "$LONGITUDE" | xargs)
            if python3 -c "float('$LONGITUDE')" &>/dev/null; then
                break
            fi
            echo -e "${C_RED}Error: Invalid longitude value!${C_RESET}"
        done
    fi
fi

# 6. Interval
while true; do
    read -p "6. How often should beacons be sent (minutes)? [Default: 5]: " INTERVAL_MINUTES
    INTERVAL_MINUTES=$(echo "$INTERVAL_MINUTES" | xargs)
    if [ -z "$INTERVAL_MINUTES" ]; then
        INTERVAL_MINUTES=5
        break
    fi
    if python3 -c "int('$INTERVAL_MINUTES') >= 1" &>/dev/null; then
        break
    fi
    echo -e "${C_RED}Error: Interval must be at least 1 minute!${C_RESET}"
done

# 6.5 APRS Thursday
read -p "6.5 Join APRS Thursday event? (ANSRVR) [y/N]: " OPT_THURSDAY
OPT_THURSDAY=$(echo "$OPT_THURSDAY" | tr 'A-Z' 'a-z' | xargs)
APRS_THURSDAY="false"
if [ "$OPT_THURSDAY" = "y" ]; then
    APRS_THURSDAY="true"
fi

# Save Configuration
cat <<EOF > "$PROFILES_DIR/$PROFILE_NAME.json"
{
    "callsign": "$CALLSIGN",
    "passcode": $PASSCODE,
    "latitude": $LATITUDE,
    "longitude": $LONGITUDE,
    "use_termux_gps": $USE_TERMUX_GPS,
    "symbol_table": "$SYMBOL_TABLE",
    "symbol_code": "$SYMBOL_CODE",
    "comment": "$COMMENT",
    "interval_minutes": $INTERVAL_MINUTES,
    "aprs_thursday": $APRS_THURSDAY,
    "server": "rotate.aprs2.net",
    "port": 14580
}
EOF

echo -e "\n${C_GREEN}[+] Configuration file saved: $PROFILES_DIR/$PROFILE_NAME.json${C_RESET}"

# Copy / Download files
echo -e "${C_BLUE}[i] Installing application scripts...${C_RESET}"
if [ -f "./aprs_beacon.py" ]; then
    cp "./aprs_beacon.py" "$INSTALL_DIR/aprs_beacon.py"
else
    curl -sL -o "$INSTALL_DIR/aprs_beacon.py" "https://raw.githubusercontent.com/mcturan/aprs/main/aprs_beacon.py"
fi
chmod +x "$INSTALL_DIR/aprs_beacon.py"

if [ -f "./aprs_manager.py" ]; then
    cp "./aprs_manager.py" "$INSTALL_DIR/aprs_manager.py"
else
    curl -sL -o "$INSTALL_DIR/aprs_manager.py" "https://raw.githubusercontent.com/mcturan/aprs/main/aprs_manager.py"
fi
chmod +x "$INSTALL_DIR/aprs_manager.py"

# Backward compatibility (migration of old single config)
if [ -f "$INSTALL_DIR/config.json" ]; then
    mv "$INSTALL_DIR/config.json" "$PROFILES_DIR/default.json" 2>/dev/null
    mv "$INSTALL_DIR/aprs_beacon.log" "$LOGS_DIR/default.log" 2>/dev/null
fi

# Send Test Beacon
echo -e "\n${C_BLUE}[i] Sending test beacon to verify settings...${C_RESET}"
python3 "$INSTALL_DIR/aprs_beacon.py" --profile "$PROFILE_NAME" --once
if [ $? -eq 0 ]; then
    echo -e "${C_GREEN}[+] Test Successful! Position packet transmitted to APRS-IS.${C_RESET}"
else
    echo -e "${C_RED}[!] Test Failed! Could not transmit packet to server.${C_RESET}"
    echo -e "${C_YELLOW}[i] For details: cat $LOGS_DIR/$PROFILE_NAME.log${C_RESET}"
    read -p "Do you want to proceed anyway? [y/N]: " PROCEED
    PROCEED=$(echo "$PROCEED" | tr 'A-Z' 'a-z' | xargs)
    if [ "$PROCEED" != "y" ]; then
        echo "Setup cancelled."
        exit 1
    fi
fi

# Service setup and startup
if [ "$IS_ANDROID" = true ]; then
    # Android/Termux startup
    echo -e "\n7. Startup Settings (Android):"
    read -p "Start automatically in background on boot? [Y/n]: " AUTO_START
    AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)
    
    BOOT_DIR="$HOME/.termux/boot"
    mkdir -p "$BOOT_DIR"
    
    cat <<EOF > "$BOOT_DIR/aprs-beacon-$PROFILE_NAME"
#!/usr/bin/env bash
termux-wake-lock
nohup python3 $INSTALL_DIR/aprs_beacon.py --profile $PROFILE_NAME >/dev/null 2>&1 &
EOF
    chmod +x "$BOOT_DIR/aprs-beacon-$PROFILE_NAME"
    
    if [ "$AUTO_START" != "n" ]; then
        echo -e "${C_BLUE}[i] Starting daemon service in background (nohup)...${C_RESET}"
        termux-wake-lock
        pkill -f "aprs_beacon.py --profile $PROFILE_NAME" 2>/dev/null
        nohup python3 $INSTALL_DIR/aprs_beacon.py --profile $PROFILE_NAME >/dev/null 2>&1 &
    fi
else
    # Linux systemd startup
    echo -e "\n7. Startup Settings (Linux):"
    read -p "Start this profile automatically on system boot? [Y/n]: " AUTO_START
    AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)

    # Generate systemd user service template
    SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
    mkdir -p "$SYSTEMD_USER_DIR"

    cat <<EOF > "$SYSTEMD_USER_DIR/aprs-beacon@.service"
[Unit]
Description=APRS Background Beacon Service (%i)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$(which python3) $INSTALL_DIR/aprs_beacon.py --profile %i
Restart=always
RestartSec=30
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=default.target
EOF

    systemctl --user daemon-reload

    if [ "$AUTO_START" != "n" ]; then
        echo -e "${C_BLUE}[i] Enabling and starting daemon service...${C_RESET}"
        systemctl --user enable aprs-beacon@$PROFILE_NAME.service
        systemctl --user restart aprs-beacon@$PROFILE_NAME.service
        loginctl enable-linger "$USER" 2>/dev/null
    fi

    # Create desktop shortcut launcher (if GUI available)
    if [ "$HAS_GUI" = true ]; then
        DESKTOP_DIR="$HOME/.local/share/applications"
        mkdir -p "$DESKTOP_DIR"
        cat <<EOF > "$DESKTOP_DIR/aprs-manager.desktop"
[Desktop Entry]
Type=Application
Name=APRS Multi-Beacon Manager
Comment=APRS Multi-Profile Background Beacon Manager
Exec=$INSTALL_DIR/aprs_manager.py gui
Icon=radio
Terminal=false
Categories=Utility;Network;
EOF
        chmod +x "$DESKTOP_DIR/aprs-manager.desktop"

        # Add manager to session autostart
        AUTOSTART_DIR="$HOME/.config/autostart"
        mkdir -p "$AUTOSTART_DIR"
        cp "$DESKTOP_DIR/aprs-manager.desktop" "$AUTOSTART_DIR/"
    fi
fi

# Post-install info summary
echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}        APRS PROFILE ($PROFILE_NAME) SUCCESSFULLY ACTIVATED!${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
echo -e "${C_BOLD}Profile Name     :${C_RESET} $PROFILE_NAME"
echo -e "${C_BOLD}Callsign         :${C_RESET} $CALLSIGN"
echo -e "${C_BOLD}Interval         :${C_RESET} Every $INTERVAL_MINUTES minute(s)"
echo -e "${C_BOLD}APRS Thursday    :${C_RESET} $([ "$APRS_THURSDAY" = "true" ] && echo "Enabled" || echo "Disabled")"
echo -e "${C_BOLD}Autostart on Boot:${C_RESET} Yes"
if [ "$IS_ANDROID" = false ]; then
    echo -e "----------------------------------------------------------------"
    if [ "$HAS_GUI" = true ]; then
        echo -e "${C_CYAN}Desktop Interface :${C_RESET} Launch 'APRS Multi-Beacon Manager' from application menu."
        echo -e "${C_CYAN}System Tray Icon  :${C_RESET} System tray icon will appear upon launching."
    else
        echo -e "${C_YELLOW}Note: No graphic display detected. Launch control panel from terminal.${C_RESET}"
    fi
    echo -e "${C_CYAN}CLI / Terminal Management:${C_RESET}"
    echo -e "  - Open Interactive Menu: python3 $INSTALL_DIR/aprs_manager.py"
    echo -e "  - List Beacon Profiles:  python3 $INSTALL_DIR/aprs_manager.py list"
    echo -e "  - Start Profile Daemon:  python3 $INSTALL_DIR/aprs_manager.py start $PROFILE_NAME"
    echo -e "  - Stop Profile Daemon:   python3 $INSTALL_DIR/aprs_manager.py stop $PROFILE_NAME"
fi
echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
