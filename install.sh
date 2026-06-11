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
echo -e "       Linux/Android APRS Beacon İnteraktif Kurulum Sihirbazı${C_RESET}\n"
echo "----------------------------------------------------------------"
echo "Bu sihirbaz, APRS beacon'ınızı arka planda otomatik"
echo "çalışacak bir servis olarak kuracaktır."
echo "----------------------------------------------------------------\n"

# Python3 kontrolü ve kurulumu
if ! command -v python3 &> /dev/null; then
    echo -e "${C_YELLOW}[!] Sistemde Python3 bulunamadı. Kuruluyor...${C_RESET}"
    if command -v apt-get &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y python3
    elif [ -d "/data/data/com.termux" ]; then
        pkg update && pkg install -y python python-apt
    else
        echo -e "${C_RED}[!] Hata: Python3 otomatik kurulamadı. Lütfen manuel kurun.${C_RESET}"
        exit 1
    fi
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
echo -e "\n3. Durum Mesajı Ayarı:"
echo -e "  ${C_YELLOW}İpucu: Frekans ve ton bilgisi eklemek için mesajın başına ekleyin (Örn: 145.550MHz T088)${C_RESET}"
echo -e "  ${C_YELLOW}İpucu: Haritada tıklanabilir link göstermek için 'https://' ekleyin (Örn: https://example.com | ARC)${C_RESET}"
read -p "Durum Mesajınız [Varsayılan: APRS Background Beacon]: " COMMENT
COMMENT=$(echo "$COMMENT" | xargs)
if [ -z "$COMMENT" ]; then
    COMMENT="APRS Background Beacon"
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

# Android / Termux Tespiti
IS_ANDROID=false
if [ -d "/data/data/com.termux" ] || [ -n "$TERMUX_VERSION" ]; then
    IS_ANDROID=true
fi

USE_TERMUX_GPS="false"
LATITUDE=""
LONGITUDE=""

if [ "$IS_ANDROID" = true ]; then
    echo -e "\n5. Konum Ayarı (Android):"
    echo -e "  ${C_YELLOW}İpucu: Telefonun GPS alıcısını kullanmak için Termux:API uygulaması kurulu ve konum izni verilmiş olmalıdır.${C_RESET}"
    read -p "Telefonunuzun dahili GPS/Konum verisini otomatik çekmek ister misiniz? [Y/n]: " OPT_GPS
    OPT_GPS=$(echo "$OPT_GPS" | tr 'A-Z' 'a-z' | xargs)
    if [ "$OPT_GPS" != "n" ]; then
        USE_TERMUX_GPS="true"
        LATITUDE="0.0"
        LONGITUDE="0.0"
        echo -e "${C_GREEN}[+] Dahili GPS aktif edildi. Manuel koordinat girişi atlanıyor.${C_RESET}"
    fi
fi

if [ "$USE_TERMUX_GPS" = "false" ]; then
    # 5. Konum
    read -p "5. Sistem konumunuzu internet üzerinden otomatik tespit etsin mi? [Y/n]: " AUTO_LOC
    AUTO_LOC=$(echo "$AUTO_LOC" | tr 'A-Z' 'a-z' | xargs)

    if [ "$AUTO_LOC" != "n" ]; then
        echo -e "${C_BLUE}[i] Konumunuz internet üzerinden otomatik tespit ediliyor...${C_RESET}"
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
            echo -e "${C_GREEN}[+] Otomatik Konum Tespit Edildi: $CITY, $COUNTRY ($LAT, $LON)${C_RESET}"
            LATITUDE="$LAT"
            LONGITUDE="$LON"
        else
            echo -e "${C_RED}[!] Otomatik konum tespiti başarısız oldu.${C_RESET}"
        fi
    fi

    if [ -z "$LATITUDE" ] || [ -z "$LONGITUDE" ]; then
        echo -e "${C_BLUE}[i] Koordinatlarınızı kolayca bulabilmeniz için tarayıcıda OpenStreetMap açılıyor...${C_RESET}"
        python3 -m webbrowser "https://www.openstreetmap.org" &>/dev/null &
        
        echo -e "${C_YELLOW}[!] Lütfen koordinatlarınızı manuel girin (Açılan haritadan Taksim Meydanı gibi konumunuzu bulun):${C_RESET}"
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
fi

# 6. Sıklık (Interval)
while true; do
    read -p "6. Kaç dakikada bir beacon gönderilsin? [Varsayılan: 5]: " INTERVAL_MINUTES
    INTERVAL_MINUTES=$(echo "$INTERVAL_MINUTES" | xargs)
    if [ -z "$INTERVAL_MINUTES" ]; then
        INTERVAL_MINUTES=5
        break
    fi
    if python3 -c "int('$INTERVAL_MINUTES') >= 1" &>/dev/null; then
        break
    fi
    echo -e "${C_RED}Hata: Aralık en az 1 dakika olmalıdır!${C_RESET}"
done

# Yapılandırmayı Kaydet
cat <<EOF > "$INSTALL_DIR/config.json"
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
    "server": "rotate.aprs2.net",
    "port": 14580
}
EOF

echo -e "\n${C_GREEN}[+] Yapılandırma dosyası kaydedildi: $INSTALL_DIR/config.json${C_RESET}"

# Daemon dosyasını indir veya güncelle
echo -e "${C_BLUE}[i] En güncel aprs_beacon.py dosyası indiriliyor/güncelleniyor...${C_RESET}"
if command -v curl &>/dev/null; then
    curl -sL -o "$INSTALL_DIR/aprs_beacon.py" "https://raw.githubusercontent.com/mcturan/aprs/main/aprs_beacon.py"
elif command -v wget &>/dev/null; then
    wget -q -o "$INSTALL_DIR/aprs_beacon.py" "https://raw.githubusercontent.com/mcturan/aprs/main/aprs_beacon.py"
else
    if [ -f "./aprs_beacon.py" ]; then
        cp "./aprs_beacon.py" "$INSTALL_DIR/aprs_beacon.py"
    else
        echo -e "${C_RED}[!] Hata: İnternet bağlantısı veya curl/wget bulunamadı, yerel dosya da mevcut değil!${C_RESET}"
        exit 1
    fi
fi
chmod +x "$INSTALL_DIR/aprs_beacon.py"

# Test Gönderimi
echo -e "\n${C_BLUE}[i] Ayarların doğruluğunu onaylamak için test paketi gönderiliyor...${C_RESET}"
python3 "$INSTALL_DIR/aprs_beacon.py" --once
if [ $? -eq 0 ]; then
    echo -e "${C_GREEN}[+] Test Başarılı! Konum paketi APRS-IS ağına iletildi.${C_RESET}"
else
    echo -e "${C_RED}[!] Test Başarısız! Paket sunucuya ulaştırılamadı.${C_RESET}"
    echo -e "${C_YELLOW}[i] İnternet bağlantınızı kontrol edin.${C_RESET}"
    echo -e "${C_YELLOW}[i] Detaylar için: cat $INSTALL_DIR/aprs_beacon.log${C_RESET}"
    read -p "Yine de devam etmek istiyor musunuz? [y/N]: " PROCEED
    PROCEED=$(echo "$PROCEED" | tr 'A-Z' 'a-z' | xargs)
    if [ "$PROCEED" != "y" ]; then
        echo "Kurulum iptal edildi."
        exit 1
    fi
fi

# Başlangıç Ayarı
if [ "$IS_ANDROID" = true ]; then
    # Android/Termux:Boot İşlemleri
    echo -e "\n7. Başlangıç ayarları (Android):"
    read -p "Sistem açılışında arka planda otomatik başlasın mı? [Y/n]: " AUTO_START
    AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)
    
    BOOT_DIR="$HOME/.termux/boot"
    mkdir -p "$BOOT_DIR"
    
    cat <<EOF > "$BOOT_DIR/aprs-beacon"
#!/usr/bin/env bash
termux-wake-lock
python3 $INSTALL_DIR/aprs_beacon.py &
EOF
    chmod +x "$BOOT_DIR/aprs-beacon"
    
    echo -e "${C_GREEN}[+] Termux:Boot scripti oluşturuldu: $BOOT_DIR/aprs-beacon${C_RESET}"
    
    if [ "$AUTO_START" != "n" ]; then
        echo -e "${C_BLUE}[i] Servis arka planda başlatılıyor...${C_RESET}"
        termux-wake-lock
        python3 $INSTALL_DIR/aprs_beacon.py &
        
        echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}           APRS ARKA PLAN SERVİSİ BAŞARIYLA AKTİF EDİLDİ!${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
        echo -e "${C_BOLD}Çağrı İşareti  :${C_RESET} $CALLSIGN"
        echo -e "${C_BOLD}Dahili GPS     :${C_RESET} $([ "$USE_TERMUX_GPS" = "true" ] && echo "Aktif (Otomatik)" || echo "Pasif (Sabit)")"
        echo -e "${C_BOLD}Simge          :${C_RESET} $SYMBOL_TABLE$SYMBOL_CODE"
        echo -e "${C_BOLD}Mesaj          :${C_RESET} $COMMENT"
        echo -e "${C_BOLD}Sıklık         :${C_RESET} $INTERVAL_MINUTES dakikada bir"
        echo -e "${C_BOLD}Durum          :${C_RESET} Arka planda çalışıyor"
        echo -e "${C_BOLD}Otomatik Başlama:${C_RESET} Telefon açıldığında otomatik başlayacak (Termux:Boot kurulu olmalıdır)"
        echo -e "----------------------------------------------------------------"
        echo -e "${C_CYAN}Canlı log takibi:${C_RESET}  tail -f $INSTALL_DIR/aprs_beacon.log"
        echo -e "${C_CYAN}Servisi durdur:${C_RESET}   pkill -f aprs_beacon.py"
        echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
    else
        echo -e "${C_YELLOW}[!] Servis otomatik başlatılmadı.${C_RESET}"
    fi
else
    # Linux systemd işlemleri
    echo -e "\n7. Başlangıç ayarları (Linux):"
    read -p "Sistem açılışında otomatik başlasın mı? [Y/n]: " AUTO_START
    AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)

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

    if [ "$AUTO_START" != "n" ]; then
        echo -e "${C_BLUE}[i] Servis otomatik başlatılacak şekilde yapılandırılıyor...${C_RESET}"
        systemctl --user daemon-reload
        systemctl --user enable aprs-beacon.service
        systemctl --user restart aprs-beacon.service
        loginctl enable-linger "$USER" 2>/dev/null
        
        echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}           APRS ARKA PLAN SERVİSİ BAŞARIYLA AKTİF EDİLDİ!${C_RESET}"
        echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
        echo -e "${C_BOLD}Çağrı İşareti  :${C_RESET} $CALLSIGN"
        echo -e "${C_BOLD}Konum          :${C_RESET} Enlem=$LATITUDE, Boylam=$LONGITUDE"
        echo -e "${C_BOLD}Simge          :${C_RESET} $SYMBOL_TABLE$SYMBOL_CODE"
        echo -e "${C_BOLD}Mesaj          :${C_RESET} $COMMENT"
        echo -e "${C_BOLD}Sıklık         :${C_RESET} $INTERVAL_MINUTES dakikada bir"
        echo -e "${C_BOLD}Durum          :${C_RESET} Arka planda çalışıyor (Systemd)"
        echo -e "${C_BOLD}Otomatik Başlama:${C_RESET} Bilgisayar açılışında otomatik başlayacak (Linger: Aktif)"
        echo -e "----------------------------------------------------------------"
        echo -e "${C_CYAN}Canlı log takibi (systemd):${C_RESET}  journalctl --user -u aprs-beacon -f"
        echo -e "${C_CYAN}Canlı log takibi (evrensel):${C_RESET} tail -f $INSTALL_DIR/aprs_beacon.log"
        echo -e "${C_CYAN}Servisi durdur:${C_RESET}              systemctl --user stop aprs-beacon"
        echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
    else
        echo -e "${C_YELLOW}[!] Servis otomatik başlatılmadı.${C_RESET}"
        echo -e "Dilediğiniz zaman manuel başlatmak için:"
        echo -e "  systemctl --user start aprs-beacon.service"
    fi
fi
