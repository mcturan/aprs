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
echo -e "       Linux/Android APRS Multi-Profile Beacon Sihirbazı${C_RESET}\n"
echo "----------------------------------------------------------------"
echo "Bu sihirbaz, APRS beacon'ınızı arka planda otomatik çalışacak"
echo "profil(ler) olarak kurup arayüzden yönetmenizi sağlayacaktır."
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
PROFILES_DIR="$INSTALL_DIR/profiles"
LOGS_DIR="$INSTALL_DIR/logs"
mkdir -p "$PROFILES_DIR" "$LOGS_DIR"
echo "$(pwd)" > "$INSTALL_DIR/.repo_path"

# Android / Termux Tespiti
IS_ANDROID=false
if [ -d "/data/data/com.termux" ] || [ -n "$TERMUX_VERSION" ]; then
    IS_ANDROID=true
fi

# GUI Bağımlılıkları Kurulumu (Linux için)
HAS_GUI=true
if [ "$IS_ANDROID" = false ]; then
    # Grafik ortam tespiti (DISPLAY değişkeni var mı?)
    if [ -z "$DISPLAY" ]; then
        HAS_GUI=false
        echo -e "${C_YELLOW}[!] Grafik ekran (DISPLAY) ortamı bulunamadı. Headless kurulum yapılıyor.${C_RESET}"
    fi

    if [ "$HAS_GUI" = true ]; then
        echo -e "${C_BLUE}[i] Arayüz ve Sistem Tepsisi (pystray, tkinter) kütüphaneleri kontrol ediliyor...${C_RESET}"
        if ! python3 -c "import tkinter; import pystray" &>/dev/null; then
            echo -e "${C_YELLOW}[!] Gerekli arayüz kütüphaneleri eksik. Kuruluyor...${C_RESET}"
            if command -v apt-get &> /dev/null; then
                echo -e "${C_BLUE}[i] Yükleme için sudo yetkisi istenebilir:${C_RESET}"
                sudo apt-get update && sudo apt-get install -y python3-tk python3-pystray
            else
                echo -e "${C_RED}[!] Hata: Paket yöneticisi (apt-get) bulunamadı. Lütfen python3-tk ve python3-pystray paketlerini kurun.${C_RESET}"
            fi
        else
            echo -e "${C_GREEN}[+] Gerekli arayüz paketleri hazır.${C_RESET}"
        fi
    fi
fi

# 0. Profil Adı
echo -e "\n=== 0. Profil Yapılandırması ==="
while true; do
    read -p "Kurulacak Profil Adı (Örn: mobil, qth, default) [Varsayılan: default]: " PROFILE_NAME
    PROFILE_NAME=$(echo "$PROFILE_NAME" | tr 'A-Z' 'a-z' | xargs)
    if [ -z "$PROFILE_NAME" ]; then
        PROFILE_NAME="default"
    fi
    if [[ "$PROFILE_NAME" =~ ^[a-z0-9_-]+$ ]]; then
        break
    fi
    echo -e "${C_RED}Hata: Profil adı sadece küçük harf, rakam, tire veya alt çizgi içerebilir!${C_RESET}"
done

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
echo -e "  ${C_YELLOW}İpucu: Haritada tıklanabilir link göstermek için 'https://' ekleyin (Örn: https://example.com)${C_RESET}"
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
        
        echo -e "${C_YELLOW}[!] Lütfen koordinatlarınızı manuel girin (Açılan haritadan enlem/boylam kopyalayın):${C_RESET}"
        while true; do
            read -p "  Enlem (Latitude, Örn: 41.037002): " LATITUDE
            LATITUDE=$(echo "$LATITUDE" | xargs)
            if python3 -c "float('$LATITUDE')" &>/dev/null; then
                break
            fi
            echo -e "${C_RED}Hata: Geçersiz enlem değeri!${C_RESET}"
        done
        while true; do
            read -p "  Boylam (Longitude, Örn: 28.985012): " LONGITUDE
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

# 6.5 APRS Perşembe Etkinliği
read -p "6.5 Her Perşembe APRS Perşembe etkinliğine katılım sağlansın mı? (ANSRVR) [y/N]: " OPT_THURSDAY
OPT_THURSDAY=$(echo "$OPT_THURSDAY" | tr 'A-Z' 'a-z' | xargs)
APRS_THURSDAY="false"
if [ "$OPT_THURSDAY" = "y" ]; then
    APRS_THURSDAY="true"
fi

# Yapılandırmayı Kaydet
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

echo -e "\n${C_GREEN}[+] Yapılandırma dosyası kaydedildi: $PROFILES_DIR/$PROFILE_NAME.json${C_RESET}"

# Dosyaları kopyala / indir
echo -e "${C_BLUE}[i] Uygulama scriptleri kuruluyor...${C_RESET}"
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

# Geriye dönük uyumluluk (Eski tekli config varsa taşıyalım)
if [ -f "$INSTALL_DIR/config.json" ]; then
    mv "$INSTALL_DIR/config.json" "$PROFILES_DIR/default.json" 2>/dev/null
    mv "$INSTALL_DIR/aprs_beacon.log" "$LOGS_DIR/default.log" 2>/dev/null
fi

# Test Gönderimi
echo -e "\n${C_BLUE}[i] Ayarların doğruluğunu onaylamak için test paketi gönderiliyor...${C_RESET}"
python3 "$INSTALL_DIR/aprs_beacon.py" --profile "$PROFILE_NAME" --once
if [ $? -eq 0 ]; then
    echo -e "${C_GREEN}[+] Test Başarılı! Konum paketi APRS-IS ağına iletildi.${C_RESET}"
else
    echo -e "${C_RED}[!] Test Başarısız! Paket sunucuya ulaştırılamadı.${C_RESET}"
    echo -e "${C_YELLOW}[i] Detaylar için: cat $LOGS_DIR/$PROFILE_NAME.log${C_RESET}"
    read -p "Yine de devam etmek istiyor musunuz? [y/N]: " PROCEED
    PROCEED=$(echo "$PROCEED" | tr 'A-Z' 'a-z' | xargs)
    if [ "$PROCEED" != "y" ]; then
        echo "Kurulum iptal edildi."
        exit 1
    fi
fi

# Servis Kurulumu ve Başlatma
if [ "$IS_ANDROID" = true ]; then
    # Android/Termux Başlatma
    echo -e "\n7. Başlangıç ayarları (Android):"
    read -p "Sistem açılışında arka planda otomatik başlasın mı? [Y/n]: " AUTO_START
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
        echo -e "${C_BLUE}[i] Servis arka planda başlatılıyor (nohup)...${C_RESET}"
        termux-wake-lock
        pkill -f "aprs_beacon.py --profile $PROFILE_NAME" 2>/dev/null
        nohup python3 $INSTALL_DIR/aprs_beacon.py --profile $PROFILE_NAME >/dev/null 2>&1 &
    fi
else
    # Linux systemd işlemleri
    echo -e "\n7. Başlangıç ayarları (Linux):"
    read -p "Cihaz açılışında bu profil otomatik başlasın mı? [Y/n]: " AUTO_START
    AUTO_START=$(echo "$AUTO_START" | tr 'A-Z' 'a-z' | xargs)

    # Systemd Şablon Servis Dosyasını Oluştur (aprs_manager.py içindeki gibi)
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
        echo -e "${C_BLUE}[i] Servis etkinleştiriliyor...${C_RESET}"
        systemctl --user enable aprs-beacon@$PROFILE_NAME.service
        systemctl --user restart aprs-beacon@$PROFILE_NAME.service
        loginctl enable-linger "$USER" 2>/dev/null
    fi

    # Masaüstü Menü Kısayolu Oluşturma (Sadece Grafik Arayüz varsa)
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

        # Otomatik Başlangıca Yönetici Panelini Ekle
        AUTOSTART_DIR="$HOME/.config/autostart"
        mkdir -p "$AUTOSTART_DIR"
        cp "$DESKTOP_DIR/aprs-manager.desktop" "$AUTOSTART_DIR/"
    fi
fi

# Kurulum Sonu Bilgilendirmesi
echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}           APRS PROFİLİ ($PROFILE_NAME) BAŞARIYLA AKTİF EDİLDİ!${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
echo -e "${C_BOLD}Profil Adı     :${C_RESET} $PROFILE_NAME"
echo -e "${C_BOLD}Çağrı İşareti  :${C_RESET} $CALLSIGN"
echo -e "${C_BOLD}Sıklık         :${C_RESET} $INTERVAL_MINUTES dakikada bir"
echo -e "${C_BOLD}APRS Perşembe  :${C_RESET} $([ "$APRS_THURSDAY" = "true" ] && echo "Etkin" || echo "Pasif")"
echo -e "${C_BOLD}Otomatik Başlama:${C_RESET} Evet"
if [ "$IS_ANDROID" = false ]; then
    echo -e "----------------------------------------------------------------"
    if [ "$HAS_GUI" = true ]; then
        echo -e "${C_CYAN}Masaüstü Arayüzü:${C_RESET} Uygulama Menüsünden 'APRS Multi-Beacon Manager'ı açabilirsiniz."
        echo -e "${C_CYAN}Sistem Tepsisi  :${C_RESET} Uygulama açıldığında sağ üstte/sağ altta bir ikon belirecektir."
    else
        echo -e "${C_YELLOW}Not: Grafik ekran bulunamadı (Headless). Yönetim panelini terminalden açabilirsiniz.${C_RESET}"
    fi
    echo -e "${C_CYAN}Terminalden Yönetim:${C_RESET}"
    echo -e "  - Arayüzü/Menüyü Aç:   python3 $INSTALL_DIR/aprs_manager.py"
    echo -e "  - Profilleri Listele:  python3 $INSTALL_DIR/aprs_manager.py list"
    echo -e "  - Servisi Başlat:      python3 $INSTALL_DIR/aprs_manager.py start $PROFILE_NAME"
    echo -e "  - Servisi Durdur:      python3 $INSTALL_DIR/aprs_manager.py stop $PROFILE_NAME"
fi
echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
