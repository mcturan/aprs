# Windows APRS Beacon Kurulum Sihirbazı
# Bu betik, Windows üzerinde arka planda sessizce (konsol penceresi açılmadan)
# çalışacak şekilde APRS beacon servisini kurar.

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "       Windows APRS Beacon Kurulum Sihirbazı" -ForegroundColor Cyan -Bold
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
if (!(Test-Path $installDir)) {
    New-Item -ItemType Directory -Force -Path $installDir | Out-Null
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
Write-Host "  İpucu: Haritada tıklanabilir link göstermek için 'https://' ekleyin (Örn: https://example.com | ARC)" -ForegroundColor Yellow
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
    # Try multiple geolocation APIs
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

    Write-Host "[!] Lütfen koordinatlarınızı manuel girin (Açılan haritadan Taksim Meydanı gibi konumunuzu bulun):" -ForegroundColor Yellow
    while ($true) {
        $latitude = (Read-Host "  Enlem (Latitude, Örn: 41.037002 - Taksim Meydanı)").Trim()
        if ([double]::TryParse($latitude, [ref]0.0)) { break }
        Write-Host "Hata: Geçersiz enlem değeri!" -ForegroundColor Red
    }
    while ($true) {
        $longitude = (Read-Host "  Boylam (Longitude, Örn: 28.985012 - Taksim Meydanı)").Trim()
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

# 7. Gelişmiş/Profesyonel Özellikler
Write-Host "`n7. Gelişmiş/Profesyonel APRS Özellikleri:" -ForegroundColor Cyan

# 7.1 Telemetri
$enableTelemetry = (Read-Host "  Sistem Telemetrisi etkinleştirilsin mi? (aprs.fi'de CPU Sıcaklığı, RAM, Disk grafikleri oluşturur) [y/N]").Trim().ToLower()
$sendTelemetry = "false"
if ($enableTelemetry -eq "y") {
    $sendTelemetry = "true"
}

# 7.2 Drone Animasyonu
$enableOrbit = (Read-Host "  İstasyonunuz etrafında dönen hareketli bir 'Drone' (Nesne Animasyonu) simüle edilsin mi? [y/N]").Trim().ToLower()
$orbitAnimation = "false"
if ($enableOrbit -eq "y") {
    $orbitAnimation = "true"
}

# 7.3 Mesaj Botu
$enableBot = (Read-Host "  İnteraktif Mesaj Botu etkinleştirilsin mi? (Gelen 'ping', 'status', 'uptime' mesajlarına otomatik yanıt verir) [y/N]").Trim().ToLower()
$interactiveBot = "false"
if ($enableBot -eq "y") {
    $interactiveBot = "true"
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
    "send_telemetry": $sendTelemetry,
    "orbit_animation": $orbitAnimation,
    "interactive_bot": $interactiveBot,
    "server": "rotate.aprs2.net",
    "port": 14580
}
"@

$configJson | Out-File -FilePath "$installDir\config.json" -Encoding utf8
Write-Host "`n[+] Yapılandırma dosyası kaydedildi: $installDir\config.json" -ForegroundColor Green

# Python dosyasını kopyala
if (Test-Path ".\aprs_beacon.py") {
    Copy-Item -Path ".\aprs_beacon.py" -Destination "$installDir\aprs_beacon.py" -Force
} else {
    Write-Host "[!] Hata: Mevcut klasörde aprs_beacon.py bulunamadı!" -ForegroundColor Red
    Exit
}

# 8. Başlangıç Ayarı
$autoStart = (Read-Host "`n8. Sistem açılışında otomatik başlasın mı? [Y/n]").Trim().ToLower()

# Windows Görev Zamanlayıcıya ekleme (Sadece kullanıcı oturum açtığında arka planda çalıştır)
if ($autoStart -ne "n") {
    Write-Host "[i] Görev Zamanlayıcı ayarlanıyor..." -ForegroundColor Blue
    
    # pythonw.exe konsol ekranı açmadan Python çalıştırır
    $action = New-ScheduledTaskAction -Execute "pythonw.exe" -Argument "`"$installDir\aprs_beacon.py`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    
    # Görevi kaydet
    Register-ScheduledTask -TaskName "APRSBeacon" -Action $action -Trigger $trigger -Settings $settings -Description "APRS Background Beacon" -Force | Out-Null
    
    Write-Host "`n================================================================" -ForegroundColor Green
    Write-Host "           APRS WINDOWS SERVİSİ BAŞARIYLA AKTİF EDİLDİ!" -ForegroundColor Green -Bold
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host "Çağrı İşareti  : $callsign"
    Write-Host "Konum          : Enlem=$latitude, Boylam=$longitude"
    Write-Host "Simge          : $symbolTable$symbolCode"
    Write-Host "Durum          : Arka planda sessizce çalışacak (Görev Zamanlayıcı)"
    Write-Host "Gönderim Sıklığı: $interval dakikada bir"
    Write-Host "Telemetri      : $(if ($sendTelemetry -eq "true") { "Aktif" } else { "Pasif" })"
    Write-Host "Drone Animasyon: $(if ($orbitAnimation -eq "true") { "Aktif" } else { "Pasif" })"
    Write-Host "Mesaj Botu     : $(if ($interactiveBot -eq "true") { "Aktif" } else { "Pasif" })"
    Write-Host "Otomatik Başlama: Kullanıcı oturum açtığında otomatik başlayacak."
    Write-Host "----------------------------------------------------------------"
    Write-Host "Manuel başlatmak için:  Start-ScheduledTask -TaskName 'APRSBeacon'"
    Write-Host "Durdurmak için:         Stop-ScheduledTask -TaskName 'APRSBeacon'"
    Write-Host "================================================================" -ForegroundColor Green
} else {
    Write-Host "[!] Görev zamanlayıcı kurulumu atlandı. Manuel çalıştırmak için:" -ForegroundColor Yellow
    Write-Host "  pythonw.exe `"$installDir\aprs_beacon.py`""
}
