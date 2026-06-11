# 📻 Linux Arka Plan APRS Beacon İstemcisi

Bu proje, Linux tabanlı işletim sistemlerinde arka planda tamamen otomatik çalışan, sistem açılışında kendi kendine başlayan hafif bir **APRS-IS (Automatic Packet Reporting System - Internet Service)** konum bildirim istemcisidir.

Herhangi bir grafik arayüze (GUI) ihtiyaç duymadan, sistem kaynaklarını tüketmeden çalışır. İstasyonunuzun konumunu, durum mesajını, hızını ve harita simgesini periyodik olarak gönderir.

---

## ✨ Özellikler

- **Sıfır Bağımlılık:** Sadece standart Python 3 kütüphanelerini kullanır (pip ile ek paket yüklemeye gerek yoktur).
- **Otomatik Başlangıç:** `systemd` kullanıcı servisi (`systemd --user`) ve `loginctl linger` kullanır. Bilgisayar açıldığında kullanıcı oturum açmasa dahi arka planda otomatik başlar.
- **Passcode Üretici:** Kurulum esnasında çağrı işaretiniz için gerekli olan APRS-IS şifresini (passcode) otomatik hesaplar.
- **Düşük Kaynak Tüketimi:** Sürekli TCP bağlantısı açık tutmak yerine belirtilen dakikada bir sunucuya bağlanıp paketi iletir ve bağlantıyı kapatır. Hem ağ trafiği hem işlemci için son derece hafiftir.

---

## 🚀 Kurulum ve Çalıştırma

Bu projeyi başka bir bilgisayarda veya kendi bilgisayarınızda kurmak için şu adımları izleyin:

### 1. Dosyaları İndirin
```bash
git clone https://github.com/mcturan/aprs.git
cd aprs
```

### 2. Kurulum Betiğini Çalıştırın
Betiğe çalıştırma izni verip sihirbazı başlatın:
```bash
chmod +x install.sh aprs_beacon.py
./install.sh
```

Sihirbaz sizi adım adım yönlendirerek aşağıdaki ayarları yapmanızı isteyecektir:
1. **Çağrı İşareti** (Örn: `N0CALL-9`)
2. **Şifre** (Girilmezse otomatik hesaplanır)
3. **Durum Mesajı** (Örn: `Linux APRS Beacon`)
4. **Harita Simgesi** (Helikopter `X`, Araba `>`, Yaya `[`, vb.)
5. **Konum Tespiti** (İnternet üzerinden otomatik tespit veya Taksim Meydanı `41.037002, 28.985012` koordinatları gibi manuel giriş)
6. **Otomatik Başlangıç** (Sistem açılışında otomatik başlama tercihi)

Bu işlem sonucunda:
- `~/.aprs-beacon/` dizini altına ayarlarınız (`config.json`) yazılır.
- `aprs_beacon.py` ana scripti buraya kopyalanır.
- `~/.config/systemd/user/aprs-beacon.service` dosyası oluşturulur.
- Eğer otomatik başlangıç seçildiyse servis aktif edilip başlatılır ve **linger** modu aktif edilir.

---

## 🛠️ Servis Yönetim Komutları

Servisi yönetmek için `sudo` veya `root` yetkisine ihtiyaç yoktur. Aşağıdaki komutlar doğrudan normal kullanıcıyla çalıştırılabilir:

### 📊 Durum Kontrolü
Servisin o anki çalışma durumunu sorgulamak için:
```bash
systemctl --user status aprs-beacon.service
```

### 📝 Çalışma Günlüklerini (Log) Canlı İzleme
Gönderilen paketleri, sunucu yanıtlarını ve bağlantı durumlarını anlık görmek için:
```bash
journalctl --user -u aprs-beacon.service -f
```

### 🛑 Servisi Durdurma
Konum göndermeyi geçici olarak durdurmak için:
```bash
systemctl --user stop aprs-beacon.service
```

### ▶️ Servisi Yeniden Başlatma / Çalıştırma
```bash
systemctl --user start aprs-beacon.service
```

### ❌ Servisi Devre Dışı Bırakma
Sistem başlangıcında otomatik açılmasını iptal etmek için:
```bash
systemctl --user disable aprs-beacon.service
```

---

## 💻 Windows Kurulumu (Görev Zamanlayıcı)

Windows üzerinde bu beacon'ı arka planda konsol penceresi açılmadan (sessizce) çalıştırmak için:

1. **PowerShell'i Açın** ve indirdiğiniz proje klasörüne gidin:
   ```powershell
   cd path/to/aprs
   ```
2. **Kurulum Sihirbazını Çalıştırın**:
   ```powershell
   PowerShell -ExecutionPolicy Bypass -File install.ps1
   ```
3. Sihirbaz bilgileri aldıktan sonra `config.json` dosyasını oluşturacak ve Windows Görev Zamanlayıcı'ya (Task Scheduler) ekleyecektir.
4. **Yönetim Komutları (PowerShell)**:
   - Başlat: `Start-ScheduledTask -TaskName 'APRSBeacon'`
   - Durdur: `Stop-ScheduledTask -TaskName 'APRSBeacon'`

## 📱 Android İçin Alternatif Öneri (APRSdroid)

Android'in sıkı güvenlik yapısı ve arka plan kısıtlamaları (Doze Mode) nedeniyle, bu tür komut satırı tabanlı betikleri telefonda çalıştırmak oldukça zahmetlidir. 

Android cihazlarda konumunuzu arka planda otomatik güncelleyerek göndermek ve harita/mesajlaşma özelliklerini kullanmak için doğrudan resmi **[APRSdroid](https://aprsdroid.org/)** uygulamasını kullanmanız önerilir. Uygulama ayarlarından "Start on Boot" seçeneğini aktif edip pil kısıtlamasını "Kısıtlamasız" yaptığınızda telefon açıldığında otomatik olarak arka planda çalışmaya başlayacaktır.




---

## 🗺️ Harita Üzerinde İzleme

Servis ilk paketi gönderdikten sonra (yaklaşık 1-2 dakika içinde), istasyonunuzu canlı olarak [aprs.fi](https://aprs.fi/) üzerinden takip edebilirsiniz:

👉 `https://aprs.fi/#!call=a%2F<ÇAGRI_İŞARETİNİZ>` (Örn: `https://aprs.fi/#!call=a%2FN0CALL-9`)
