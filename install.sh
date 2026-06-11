#!/usr/bin/env bash

# Terminal Renkleri
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
echo -e "       Linux APRS Beacon İnteraktif Kurulum Sihirbazı${C_RESET}\n"
echo "----------------------------------------------------------------"
echo "Bu sihirbaz, APRS beacon'ınızı yapılandıracak ve isteğe bağlı"
echo "olarak sistem açılışında arka planda çalışması için ayarlayacaktır."
echo "----------------------------------------------------------------\n"

# Python3 kontrolü
if ! command -v python3 &> /dev/null; then
    echo -e "${C_RED}[!] Hata: Sistemde Python3 bulunamadı. Lütfen yükleyin.${C_RESET}"
    exit 1
fi

INSTALL_DIR="$HOME/.aprs-beacon"
mkdir -p "$INSTALL_DIR"

# 1. Çağrı İşareti
while true; do
    read -p "1. Çağrı İşaretiniz (Örn: N0CALL-9): " CALLSIGN
    CALLSIGN=$(echo "$CALLSIGN" | tr 'a-z' 'A-Z' | xargs)
    if [ -n "$CALLSIGN" ]; then
        break
    fi
    echo -e "${C_RED}Hata: Çağrı işareti boş olamaz!${C_RESET}"
done

# 2. Şifre (Passcode)
read -p "2. Şifreniz (APRS-IS Passcode) [Otomatik hesaplamak için Enter]: " PASSCODE
PASSCODE=$(echo "$PASSCODE" | xargs)
if [ -z "$PASSCODE" ]; then
    echo -e "${C_BLUE}[i] Çağrı işaretinizden şifre otomatik hesaplanıyor...${C_RESET}"
    PASSCODE=$(python3 -c "
callsign = '${CALLSIGN}'.split('-')[0]
hash_val = 0x73e2
for i in range(0, len(callsign), 2):
    char1 = ord(callsign[i]) << 8
    char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
    hash_val ^= (char1 + char2)
print(hash_val & 0x7fff)
")
    echo -e "${C_GREEN}[+] Hesaplanan Şifre: $PASSCODE${C_RESET}"
fi

# 3. Mesaj (Comment)
read -p "3. Durum Mesajınız [Varsayılan: Linux APRS Beacon]: " COMMENT
COMMENT=$(echo "$COMMENT" | xargs)
if [ -z "$COMMENT" ]; then
    COMMENT="Linux APRS Beacon"
fi

# 4. Simge (Symbol)
echo -e "\n4. Haritada görünecek Simgeyi seçin:"
echo "  1) Helikopter (X) [Varsayılan]"
echo "  2) Otomobil / Araba (>)"
echo "  3) Yaya / Yürüyüşçü ([)"
echo "  4) Ev / QTH İstasyonu (-)"
echo "  5) Sabit Telsiz / Cihaz (#)"
echo "  6) Diğer (Kendi karakterinizi girin)"
read -p "Seçiminiz [1-6]: " SYM_CHOICE
SYM_CHOICE=$(echo "$SYM_CHOICE" | xargs)

SYMBOL_TABLE="/"
SYMBOL_CODE="X"

case "$SYM_CHOICE" in
    2) SYMBOL_CODE=">" ;;
    3) SYMBOL_CODE="[" ;;
    4) SYMBOL_CODE="-" ;;
    5) SYMBOL_CODE="#" ;;
    6) 
        read -p "Simge Karakterini girin (Örn: > veya [ veya X): " CUSTOM_SYM
        SYMBOL_CODE=$(echo "$CUSTOM_SYM" | xargs)
        if [ -z "$SYMBOL_CODE" ]; then
            SYMBOL_CODE="X"
        fi
        ;;
    *) SYMBOL_CODE="X" ;;
esac

# 5. Konum (Location)
echo -e "\n5. Konum ayarları:"
read -p "Sistem konumunuzu internet üzerinden otomatik tespit etsin mi? [Y/n]: " AUTO_LOC
AUTO_LOC=$(echo "$AUTO_LOC" | tr 'A-Z' 'a-z' | xargs)

LATITUDE=""
LONGITUDE=""

if [ "$AUTO_LOC" != "n" ]; then
    echo -e "${C_BLUE}[i] Konumunuz internet üzerinden otomatik tespit ediliyor...${C_RESET}"
    IP_LOC=$(python3 -c "
import urllib.request, json
try:
    req = urllib.request.Request('http://ip-api.com/json', headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=4) as r:
        d = json.loads(r.read().decode('utf-8'))
        if d.get('status') == 'success':
            print(f\"{d['lat']},{d['lon']},{d['city']},{d['country']}\")
except:
    pass
")
    if [ -n "$IP_LOC" ]; then
        IFS=',' read -r LAT LON CITY COUNTRY <<< "$IP_LOC"
        echo -e "${C_GREEN}[+] Otomatik Konum Tespit Edildi: $CITY, $COUNTRY ($LAT, $LON)${C_RESET}"
        LATITUDE="$LAT"
        LONGITUDE="$LON"
    else
        echo -e "${C_RED}[!] Otomatik konum tespiti başarısız oldu. Manuel girişe geçiliyor...${C_RESET}"
    fi
fi

if [ -z "$LATITUDE" ] || [ -z "$LONGITUDE" ]; then
    echo -e "${C_YELLOW}[!] Lütfen koordinatlarınızı manuel girin:${C_RESET}"
    while true; do
        read -p "  Enlem (Latitude, Örn: 41.037002 - Taksim Meydanı): " LATITUDE
        LATITUDE=$(echo "$LATITUDE" | xargs)
        if python3 -c "float('$LATITUDE')" &>/dev/null; then
            break
        fi
        echo -e "${C_RED}Hata: Geçersiz enlem değeri!${C_RESET}"
    done
    while true; do
        read -p "  Boylam (Longitude, Örn: 28.985012 - Taksim Meydanı): " LONGITUDE
        LONGITUDE=$(echo "$LONGITUDE" | xargs)
        if python3 -c "float('$LONGITUDE')" &>/dev/null; then
            break
        fi
        echo -e "${C_RED}Hata: Geçersiz boylam değeri!${C_RESET}"
    done
fi

# 6. Başlangıç Ayarı
echo -e "\n6. Başlangıç ayarları:"
read -p "Sistem açılışında otomatik başlasın mı? [Y/n]: " AUTO_START
AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)

# Yapılandırmayı Kaydet
cat <<EOF > "$INSTALL_DIR/config.json"
{
    "callsign": "$CALLSIGN",
    "passcode": $PASSCODE,
    "latitude": $LATITUDE,
    "longitude": $LONGITUDE,
    "symbol_table": "$SYMBOL_TABLE",
    "symbol_code": "$SYMBOL_CODE",
    "comment": "$COMMENT",
    "interval_minutes": 20,
    "server": "rotate.aprs2.net",
    "port": 14580
}
EOF

echo -e "\n${C_GREEN}[+] Yapılandırma dosyası kaydedildi: $INSTALL_DIR/config.json${C_RESET}"

# Daemon dosyasını kopyala
if [ -f "./aprs_beacon.py" ]; then
    cp "./aprs_beacon.py" "$INSTALL_DIR/aprs_beacon.py"
else
    echo -e "${C_RED}[!] Hata: Kurulum dizininde aprs_beacon.py bulunamadı!${C_RESET}"
    exit 1
fi
chmod +x "$INSTALL_DIR/aprs_beacon.py"

# Systemd Servisi Oluştur
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

cat <<EOF > "$SYSTEMD_USER_DIR/aprs-beacon.service"
[Unit]
Description=APRS Background Beacon Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$(which python3) $INSTALL_DIR/aprs_beacon.py
Restart=always
RestartSec=30
WorkingDirectory=$INSTALL_DIR

[Install]
WantedBy=default.target
EOF

echo -e "${C_GREEN}[+] Systemd servis dosyası oluşturuldu: $SYSTEMD_USER_DIR/aprs-beacon.service${C_RESET}"

# Otomatik Başlatma İşlemleri
if [ "$AUTO_START" != "n" ]; then
    echo -e "${C_BLUE}[i] Servis otomatik başlatılacak şekilde yapılandırılıyor...${C_RESET}"
    systemctl --user daemon-reload
    systemctl --user enable aprs-beacon.service
    systemctl --user start aprs-beacon.service
    
    # Linger yetkisi
    loginctl enable-linger "$USER" 2>/dev/null
    
    echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}           APRS ARKA PLAN SERVİSİ BAŞARIYLA AKTİF EDİLDİ!${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
    echo -e "${C_BOLD}Çağrı İşareti  :${C_RESET} $CALLSIGN"
    echo -e "${C_BOLD}Konum          :${C_RESET} Enlem=$LATITUDE, Boylam=$LONGITUDE"
    echo -e "${C_BOLD}Simge          :${C_RESET} $SYMBOL_TABLE$SYMBOL_CODE"
    echo -e "${C_BOLD}Mesaj          :${C_RESET} $COMMENT"
    echo -e "${C_BOLD}Durum          :${C_RESET} Arka planda çalışıyor (Systemd)"
    echo -e "${C_BOLD}Otomatik Başlama:${C_RESET} Bilgisayar açılışında otomatik başlayacak (Linger: Aktif)"
    echo -e "----------------------------------------------------------------"
    echo -e "${C_CYAN}Canlı log takibi:${C_RESET}             journalctl --user -u aprs-beacon -f"
    echo -e "${C_CYAN}Servisi durdur:${C_RESET}              systemctl --user stop aprs-beacon"
    echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
else
    echo -e "${C_YELLOW}[!] Servis otomatik başlatılmadı.${C_RESET}"
    echo -e "Dilediğiniz zaman manuel başlatmak için:"
    echo -e "  systemctl --user start aprs-beacon.service"
    echo -e "Durdurmak için:"
    echo -e "  systemctl --user stop aprs-beacon.service"
fi
