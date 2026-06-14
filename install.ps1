# Windows APRS Beacon Kurulum Sihirbazı
# Bu betik, Windows üzerinde arka planda sessizce (konsol penceresi açılmadan)
# çalışacak şekilde APRS beacon servisini kurar.

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "       Windows APRS Multi-Profile Beacon Sihirbazı" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Bu sihirbaz, APRS beacon'ınızı yapılandıracak ve bilgisayarınız"
Write-Host "başladığında arka planda otomatik çalışması için Görev Zamanlayıcı'ya ekleyecektir."
Write-Host "----------------------------------------------------------------`n"

# Python kontrolü
try {
    $pythonTest = python --version 2>$null
    if ($null -eq $pythonTest) {
         throw "Python bulunamadı"
    }
} catch {
    Write-Host "[!] Hata: Sistemde Python yüklü değil veya PATH'e eklenmemiş!" -ForegroundColor Red
    Write-Host "Lütfen python.org sitesinden Python'ı indirin ve yüklerken 'Add Python to PATH' seçeneğini işaretleyin." -ForegroundColor Yellow
    Exit
}

$installDir = "$env:USERPROFILE\.aprs-beacon"
$profilesDir = "$installDir\profiles"
$logsDir = "$installDir\logs"

if (!(Test-Path $installDir)) { New-Item -ItemType Directory -Force -Path $installDir | Out-Null }
if (!(Test-Path $profilesDir)) { New-Item -ItemType Directory -Force -Path $profilesDir | Out-Null }
if (!(Test-Path $logsDir)) { New-Item -ItemType Directory -Force -Path $logsDir | Out-Null }

# GUI Bağımlılıkları Kurulumu (Windows için)
Write-Host "[i] Görsel arayüz için kütüphaneler kontrol ediliyor (pystray, Pillow)..." -ForegroundColor Blue
try {
    python -c "import pystray, PIL" 2>$null
    Write-Host "[+] Gerekli paketler kurulu." -ForegroundColor Green
} catch {
    Write-Host "[!] Gerekli kütüphaneler kuruluyor (pystray, Pillow)..." -ForegroundColor Yellow
    pip install pystray Pillow --quiet
}

# 0. Profil Adı
Write-Host "`n=== 0. Profil Yapılandırması ===" -ForegroundColor Cyan
while ($true) {
    $profileName = (Read-Host "Kurulacak Profil Adı [Varsayılan: default]").Trim().ToLower()
    if ($profileName -eq "") {
        $profileName = "default"
    }
    if ($profileName -match '^[a-z0-9_-]+$') {
        break
    }
    Write-Host "Hata: Profil adı sadece küçük harf, rakam, tire veya alt çizgi içerebilir!" -ForegroundColor Red
}

# 1. Çağrı İşareti
while ($true) {
    $callsign = (Read-Host "1. Çağrı İşaretiniz (Örn: N0CALL-9)").Trim().ToUpper()
    if ($callsign -ne "") { break }
    Write-Host "Hata: Çağrı işareti boş olamaz!" -ForegroundColor Red
}

# 2. Şifre (Passcode)
$passcode = (Read-Host "2. Şifreniz (APRS-IS Passcode) [Otomatik hesaplamak için Enter]").Trim()
if ($passcode -eq "") {
    Write-Host "[i] Çağrı işaretinizden şifre otomatik hesaplanıyor..." -ForegroundColor Blue
    $callsignClean = $callsign.Split("-")[0]
    $hashVal = 0x73e2
    for ($i = 0; $i -lt $callsignClean.Length; $i += 2) {
        $char1 = [int][char]$callsignClean[$i] -shl 8
        $char2 = 0
        if (($i + 1) -lt $callsignClean.Length) {
            $char2 = [int][char]$callsignClean[$i+1]
        }
        $hashVal = $hashVal -bxor ($char1 + $char2)
    }
    $passcode = $hashVal -band 0x7fff
    Write-Host "[+] Hesaplanan Şifre: $passcode" -ForegroundColor Green
}

# 3. Mesaj
Write-Host "`n3. Durum Mesajı Ayarı:" -ForegroundColor Cyan
Write-Host "  İpucu: Frekans ve ton bilgisi eklemek için mesajın başına ekleyin (Örn: 145.550MHz T088)" -ForegroundColor Yellow
Write-Host "  İpucu: Haritada tıklanabilir link göstermek için 'https://' ekleyin (Örn: https://example.com)" -ForegroundColor Yellow
$comment = (Read-Host "Durum Mesajınız [Varsayılan: Windows APRS Beacon]").Trim()
if ($comment -eq "") {
    $comment = "Windows APRS Beacon"
}

# 4. Simge (Symbol)
Write-Host "`n4. Haritada görünecek Simgeyi seçin:" -ForegroundColor Cyan
Write-Host "  1) Helikopter (X) [Varsayılan]"
Write-Host "  2) Otomobil / Araba (>)"
Write-Host "  3) Yaya / Yürüyüşçü ([)"
Write-Host "  4) Ev / QTH İstasyonu (-)"
Write-Host "  5) Sabit Telsiz / Cihaz (#)"
$symChoice = (Read-Host "Seçiminiz [1-5]").Trim()

$symbolTable = "/"
$symbolCode = "X"
switch ($symChoice) {
    "2" { $symbolCode = ">" }
    "3" { $symbolCode = "[" }
    "4" { $symbolCode = "-" }
    "5" { $symbolCode = "#" }
    Default { $symbolCode = "X" }
}

# 5. Konum (Location)
Write-Host "`n5. Konum ayarları:" -ForegroundColor Cyan
$autoLoc = (Read-Host "Sistem konumunuzu internet üzerinden otomatik tespit etsin mi? [Y/n]").Trim().ToLower()

$latitude = ""
$longitude = ""

if ($autoLoc -ne "n") {
    Write-Host "[i] Konumunuz internet üzerinden otomatik tespit ediliyor..." -ForegroundColor Blue
    $apis = @(
        "http://ip-api.com/json",
        "https://ipapi.co/json/"
    )
    foreach ($api in $apis) {
        try {
            $ipLoc = Invoke-RestMethod -Uri $api -TimeoutSec 4
            if ($ipLoc.status -eq "success" -or $ipLoc.latitude -ne $null) {
                $lat = if ($ipLoc.lat) { $ipLoc.lat } else { $ipLoc.latitude }
                $lon = if ($ipLoc.lon) { $ipLoc.lon } else { $ipLoc.longitude }
                $city = if ($ipLoc.city) { $ipLoc.city } else { "Bilinmiyor" }
                $country = if ($ipLoc.country_name) { $ipLoc.country_name } else { $ipLoc.country }
                
                Write-Host "[+] Otomatik Konum Tespit Edildi: $city, $country ($lat, $lon)" -ForegroundColor Green
                $latitude = $lat
                $longitude = $lon
                break
            }
        } catch {
            continue
        }
    }
    if ($latitude -eq "" -or $longitude -eq "") {
        Write-Host "[!] Otomatik konum tespiti başarısız oldu." -ForegroundColor Red
    }
}

if ($latitude -eq "" -or $longitude -eq "") {
    Write-Host "[i] Koordinatlarınızı kolayca bulabilmeniz için tarayıcıda OpenStreetMap açılıyor..." -ForegroundColor Blue
    try {
        Start-Process "https://www.openstreetmap.org"
    } catch {}

    Write-Host "[!] Lütfen koordinatlarınızı manuel girin (Açılan haritadan enlem/boylam kopyalayın):" -ForegroundColor Yellow
    while ($true) {
        $latitude = (Read-Host "  Enlem (Latitude, Örn: 41.037002)").Trim()
        if ([double]::TryParse($latitude, [ref]0.0)) { break }
        Write-Host "Hata: Geçersiz enlem değeri!" -ForegroundColor Red
    }
    while ($true) {
        $longitude = (Read-Host "  Boylam (Longitude, Örn: 28.985012)").Trim()
        if ([double]::TryParse($longitude, [ref]0.0)) { break }
        Write-Host "Hata: Geçersiz boylam değeri!" -ForegroundColor Red
    }
}

# 6. Sıklık (Interval)
while ($true) {
    $intervalInput = (Read-Host "6. Kaç dakikada bir beacon gönderilsin? [Varsayılan: 5]").Trim()
    if ($intervalInput -eq "") {
        $interval = 5
        break
    }
    if ([int]::TryParse($intervalInput, [ref]0) -and [int]$intervalInput -ge 1) {
        $interval = [int]$intervalInput
        break
    }
    Write-Host "Hata: Aralık en az 1 dakika olmalıdır!" -ForegroundColor Red
}

# 6.5 APRS Perşembe Etkinliği
$thursdayInput = (Read-Host "6.5 Her Perşembe APRS Perşembe etkinliğine katılım sağlansın mı? (ANSRVR) [y/N]").Trim().ToLower()
$aprsThursday = $false
if ($thursdayInput -eq "y") {
    $aprsThursday = $true
}

# Yapılandırmayı JSON olarak kaydet
$configJson = @"
{
    "callsign": "$callsign",
    "passcode": $passcode,
    "latitude": $latitude,
    "longitude": $longitude,
    "use_termux_gps": false,
    "symbol_table": "$symbolTable",
    "symbol_code": "$symbolCode",
    "comment": "$comment",
    "interval_minutes": $interval,
    "aprs_thursday": $($aprsThursday.ToString().ToLower()),
    "server": "rotate.aprs2.net",
    "port": 14580
}
"@

$configJson | Out-File -FilePath "$profilesDir\$profileName.json" -Encoding utf8
Write-Host "`n[+] Yapılandırma dosyası kaydedildi: $profilesDir\$profileName.json" -ForegroundColor Green

# Dosyaları kopyala
if (Test-Path ".\aprs_beacon.py") {
    Copy-Item -Path ".\aprs_beacon.py" -Destination "$installDir\aprs_beacon.py" -Force
} else {
    Write-Host "[!] Hata: Mevcut klasörde aprs_beacon.py bulunamadı!" -ForegroundColor Red
    Exit
}

if (Test-Path ".\aprs_manager.py") {
    Copy-Item -Path ".\aprs_manager.py" -Destination "$installDir\aprs_manager.py" -Force
}

# Geriye dönük uyumluluk (Eski tekli config varsa taşıyalım)
if (Test-Path "$installDir\config.json") {
    Move-Item -Path "$installDir\config.json" -Destination "$profilesDir\default.json" -Force -ErrorAction SilentlyContinue
    Move-Item -Path "$installDir\aprs_beacon.log" -Destination "$logsDir\default.log" -Force -ErrorAction SilentlyContinue
}

# Test Gönderimi
Write-Host "`n[i] Ayarların doğruluğunu onaylamak için test paketi gönderiliyor..." -ForegroundColor Blue
python "$installDir\aprs_beacon.py" --profile "$profileName" --once
if ($LASTEXITCODE -eq 0) {
    Write-Host "[+] Test Başarılı! Konum paketi APRS-IS ağına iletildi." -ForegroundColor Green
} else {
    Write-Host "[!] Test Başarısız! Paket sunucuya ulaştırılamadı." -ForegroundColor Red
    $proceed = (Read-Host "Yine de devam etmek istiyor musunuz? [y/N]").Trim().ToLower()
    if ($proceed -ne "y") {
        Write-Host "Kurulum iptal edildi."
        Exit
    }
}

# 7. Başlangıç Ayarı
$autoStart = (Read-Host "`n7. Sistem açılışında otomatik başlasın mı? [Y/n]").Trim().ToLower()

# Windows Görev Zamanlayıcıya ekleme (Sadece kullanıcı oturum açtığında arka planda çalıştır)
if ($autoStart -ne "n") {
    Write-Host "[i] Görev Zamanlayıcı ayarlanıyor..." -ForegroundColor Blue
    
    # pythonw.exe konsol ekranı açmadan Python çalıştırır
    $action = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "`"$installDir\aprs_beacon.py`" --profile $profileName"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
    
    # Görevi kaydet
    Register-ScheduledTask -TaskName "APRSBeacon-$profileName" -Action $action -Trigger $trigger -Settings $settings -Description "APRS Background Beacon ($profileName)" -Force | Out-Null
    
    Write-Host "`n================================================================" -ForegroundColor Green
    Write-Host "           APRS WINDOWS SERVİSİ ($profileName) BAŞARIYLA AKTİF EDİLDİ!" -ForegroundColor Green -Bold
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "Profil Adı     : $profileName"
    Write-Host "Çağrı İşareti  : $callsign"
    Write-Host "Durum          : Arka planda sessizce çalışacak (Görev Zamanlayıcı)"
    Write-Host "Gönderim Sıklığı: $interval dakikada bir"
    Write-Host "Otomatik Başlama: Kullanıcı oturum açtığında otomatik başlayacak."
    Write-Host "----------------------------------------------------------------"
    Write-Host "Yönetim Panelini açmak için: python `"$installDir\aprs_manager.py`" gui"
    Write-Host "Canlı Log Takibi (PowerShell):"
    Write-Host "  Get-Content -Path `"$logsDir\$profileName.log`" -Wait -Tail 10"
    Write-Host "================================================================" -ForegroundColor Green
} else {
    Write-Host "[!] Görev zamanlayıcı kurulumu atlandı." -ForegroundColor Yellow
}
