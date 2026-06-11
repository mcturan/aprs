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
$comment = (Read-Host "3. Durum Mesajınız [Varsayılan: Windows APRS Beacon]").Trim()
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
    try {
        $ipLoc = Invoke-RestMethod -Uri "http://ip-api.com/json" -TimeoutSec 4
        if ($ipLoc.status -eq "success") {
            Write-Host "[+] Otomatik Konum Tespit Edildi: $($ipLoc.city), $($ipLoc.country) ($($ipLoc.lat), $($ipLoc.lon))" -ForegroundColor Green
            $latitude = $ipLoc.lat
            $longitude = $ipLoc.lon
        } else {
            Write-Host "[!] Otomatik konum tespiti başarısız oldu." -ForegroundColor Red
        }
    } catch {
        Write-Host "[!] Konum servislerine erişilemedi." -ForegroundColor Yellow
    }
}

if ($latitude -eq "" -or $longitude -eq "") {
    Write-Host "[!] Lütfen koordinatlarınızı manuel girin:" -ForegroundColor Yellow
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

# 6. Başlangıç Ayarı
$autoStart = (Read-Host "Sistem açılışında otomatik başlasın mı? [Y/n]").Trim().ToLower()

# Yapılandırmayı JSON olarak kaydet
$configJson = @"
{
    "callsign": "$callsign",
    "passcode": $passcode,
    "latitude": $latitude,
    "longitude": $longitude,
    "symbol_table": "$symbolTable",
    "symbol_code": "$symbolCode",
    "comment": "$comment",
    "interval_minutes": 20,
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
    Write-Host "Otomatik Başlama: Kullanıcı oturum açtığında otomatik başlayacak."
    Write-Host "----------------------------------------------------------------"
    Write-Host "Manuel başlatmak için:  Start-ScheduledTask -TaskName 'APRSBeacon'"
    Write-Host "Durdurmak için:         Stop-ScheduledTask -TaskName 'APRSBeacon'"
    Write-Host "================================================================" -ForegroundColor Green
} else {
    Write-Host "[!] Görev zamanlayıcı kurulumu atlandı. Manuel çalıştırmak için:" -ForegroundColor Yellow
    Write-Host "  pythonw.exe `"$installDir\aprs_beacon.py`""
}
