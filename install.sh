#!/usr/bin/env bash

# ==============================================================================
# APRS YAPILANDIRMASI (BAŞKA BİLGİSAYARLAR İÇİN BURAYI DÜZENLEYİN)
# ==============================================================================
CALLSIGN="TA1XBA-2"
PASSCODE="17082"                       # Boş bırakılırsa otomatik hesaplanır
LATITUDE="41.028399"
LONGITUDE="28.976864"
SYMBOL_TABLE="/"                       # / -> Birincil tablo
SYMBOL_CODE="X"                        # X -> Helikopter simgesi
COMMENT="linktr.ee/MCTURAN | ARC"
INTERVAL_MINUTES=20
SERVER="rotate.aprs2.net"
PORT=14580
# ==============================================================================

# Terminal Renkleri
C_GREEN='\033[92m'
C_YELLOW='\033[93m'
C_BLUE='\033[94m'
C_CYAN='\033[96m'
C_RED='\033[91m'
C_BOLD='\033[1m'
C_RESET='\033[0m'

echo -e "${C_CYAN}${C_BOLD}"
echo "   _   ___  ___  ___   ___                             "
echo "  /_\ | _ \| _ \/ __| | _ ) ___ __ _ __ ___ _ _        "
echo " / _ \|  _/|   /\__ \ | _ \/ -_) _\` / _/ _ \ ' \       "
echo "/_/ \_\_|  |_|_\|___/ |___/\___\__,_\__\___/_||_|      "
echo -e "       Linux APRS Beacon Kurulum ve Güncelleme Betiği${C_RESET}\n"

# Python3 kontrolü
if ! command -v python3 &> /dev/null; then
    echo -e "${C_RED}[!] Hata: Sistemde Python3 bulunamadı. Lütfen önce yükleyin.${C_RESET}"
    exit 1
fi

INSTALL_DIR="$HOME/.aprs-beacon"
mkdir -p "$INSTALL_DIR"

# Eğer şifre belirtilmemişse otomatik hesapla
if [ -z "$PASSCODE" ]; then
    echo -e "${C_BLUE}[i] Passcode otomatik hesaplanıyor...${C_RESET}"
    # Python ile passcode'u hesapla
    PASSCODE=$(python3 -c "
callsign = '${CALLSIGN}'.upper().split('-')[0]
hash_val = 0x73e2
for i in range(0, len(callsign), 2):
    char1 = ord(callsign[i]) << 8
    char2 = ord(callsign[i+1]) if (i + 1 < len(callsign)) else 0
    hash_val ^= (char1 + char2)
print(hash_val & 0x7fff)
")
    echo -e "${C_GREEN}[+] Passcode hesaplandı: $PASSCODE${C_RESET}"
fi

# config.json dosyasını oluştur
cat <<EOF > "$INSTALL_DIR/config.json"
{
    "callsign": "$CALLSIGN",
    "passcode": $PASSCODE,
    "latitude": $LATITUDE,
    "longitude": $LONGITUDE,
    "symbol_table": "$SYMBOL_TABLE",
    "symbol_code": "$SYMBOL_CODE",
    "comment": "$COMMENT",
    "interval_minutes": $INTERVAL_MINUTES,
    "server": "$SERVER",
    "port": $PORT
}
EOF

echo -e "${C_GREEN}[+] Yapılandırma dosyası güncellendi: $INSTALL_DIR/config.json${C_RESET}"

# aprs_beacon.py dosyasını çalışma dizinine kopyala
if [ -f "./aprs_beacon.py" ]; then
    cp "./aprs_beacon.py" "$INSTALL_DIR/aprs_beacon.py"
else
    echo -e "${C_YELLOW}[!] Uyarı: Mevcut dizinde aprs_beacon.py bulunamadı, güncellenmedi.${C_RESET}"
fi
chmod +x "$INSTALL_DIR/aprs_beacon.py"

# Systemd servis klasörünü oluştur ve dosyayı yaz
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

echo -e "${C_GREEN}[+] Systemd servis dosyası güncellendi: $SYSTEMD_USER_DIR/aprs-beacon.service${C_RESET}"

# Servisi yeniden yükle, aktifleştir ve başlat
echo -e "${C_BLUE}[i] Servis yeniden başlatılıyor...${C_RESET}"
systemctl --user daemon-reload
systemctl --user enable aprs-beacon.service
systemctl --user restart aprs-beacon.service

# Bilgisayar açılışında (login olmadan) otomatik başlamasını sağla (linger aktifleştir)
echo -e "${C_BLUE}[i] Bilgisayar açılışında otomatik başlama (Linger) yetkisi ayarlanıyor...${C_RESET}"
loginctl enable-linger "$USER" 2>/dev/null || echo -e "${C_YELLOW}[!] Not: Linger yetkisi verilemedi (sudo veya root yetkisi gerekebilir), ancak aktif oturumunuzda çalışmaya devam edecektir.${C_RESET}"

# Servis durumunu kontrol et
sleep 1.5
if systemctl --user is-active aprs-beacon.service &>/dev/null; then
    echo -e "\n${C_GREEN}${C_BOLD}================================================================${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}           APRS ARKA PLAN SERVİSİ BAŞARIYLA AKTİF EDİLDİ!${C_RESET}"
    echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}"
    echo -e "${C_BOLD}Çağrı İşareti  :${C_RESET} $CALLSIGN"
    echo -e "${C_BOLD}Konum          :${C_RESET} Enlem=$LATITUDE, Boylam=$LONGITUDE"
    echo -e "${C_BOLD}Simge          :${C_RESET} $SYMBOL_TABLE$SYMBOL_CODE (Helikopter)"
    echo -e "${C_BOLD}Mesaj          :${C_RESET} $COMMENT"
    echo -e "${C_BOLD}Gönderim Sıklığı:${C_RESET} $INTERVAL_MINUTES dakikada bir"
    echo -e "${C_BOLD}Durum          :${C_RESET} Arka planda çalışıyor (Systemd User Service)"
    echo -e "${C_BOLD}Otomatik Başlama:${C_RESET} Bilgisayar açılışında otomatik başlayacak (Linger: Aktif)"
    echo -e "----------------------------------------------------------------"
    echo -e "${C_CYAN}Canlı izlemek için (Birkaç dakika içinde haritada görünür):${C_RESET}"
    echo -e "  https://aprs.fi/#!call=a%2F$CALLSIGN"
    echo -e "----------------------------------------------------------------"
    echo -e "${C_CYAN}Servis durumunu sorgula:${C_RESET}     systemctl --user status aprs-beacon"
    echo -e "${C_CYAN}Canlı log takibi:${C_RESET}             journalctl --user -u aprs-beacon -f"
    echo -e "${C_CYAN}Servisi durdur:${C_RESET}              systemctl --user stop aprs-beacon"
    echo -e "${C_GREEN}${C_BOLD}================================================================${C_RESET}\n"
else
    echo -e "${C_RED}[!] Hata: Servis başlatıldı ancak aktif olamadı. Lütfen 'systemctl --user status aprs-beacon.service' çıktısını kontrol edin.${C_RESET}"
fi
