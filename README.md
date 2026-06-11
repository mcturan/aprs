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

---

## 📱 Android Kurulumu (Görünmez Arka Plan Servisi - Termux:Boot)

Android telefonunuzda görsel bir uygulama açmak zorunda kalmadan, telefon açıldığında arka planda tamamen sessizce (başlangıçta otomatik olarak) başlayacak ve **"Son Uygulamalar" (Recents) ekranında görünmeyeceği için yanlışlıkla kapatılamayacak** bir yapı kurmak için:

### 1. Sihirbazı Çalıştırma
Termux uygulamasını açın ve doğrudan aşağıdaki komutları yapıştırarak sihirbazı başlatın:
```bash
git clone https://github.com/mcturan/aprs.git
cd aprs
chmod +x install.sh aprs_beacon.py
./install.sh
```

### 2. Sihirbazın Yönlendirmesiyle Kurulum
- Sihirbaz, **Termux:API** ve **Termux:Boot** companion uygulamalarının telefonunuzda kurulu olup olmadığını kontrol eder. 
- Eksikse, APK dosyalarını otomatik olarak F-Droid deposundan çeker ve Android'in uygulama yükleme ekranını açar. Sizin tek yapmanız gereken **"Yükle" (Install)** butonuna dokunmaktır.
- Sihirbaz, telefonun GPS izin penceresini otomatik tetikler. **"Konum (Her zaman izin ver)"** seçeneğini işaretleyin.
- Sihirbazda `"Android cihazınızın canlı GPS konumunu kullanmak ister misiniz?"` sorusuna `Evet` deyin.
- `"Cihaz her açıldığında otomatik başlasın mı?"` sorusuna `Evet` deyin.

### 3. Kalıcılık Ayarları (Çok Önemli!)
Android'in servisi uyutmasını engellemek için şu 3 adımı yapın:
1. **Termux:Boot** uygulamasını telefonda bir kez açıp kapatın (Android tetikleyicisi için zorunludur).
2. Telefon Ayarları > Uygulamalar > **Termux** ve **Termux:Boot** için **Pil Kısıtlamasını Kaldırın ("Kısıtlamasız" / "Optimize Etme")**.
3. Cihazınızda varsa "Otomatik Başlatma" (Auto-start / App Launch) iznini hem **Termux** hem **Termux:Boot** için aktif edin.
4. Termux bildirim panelinde yer alan **"Acquire Wakelock"** seçeneğine tıklayın.

*Artık telefonunuz her yeniden başladığında, Termux arka planda uyanacak, GPS uydularından canlı konumunuzu çekerek belirttiğiniz sıklıkta (varsayılan 5dk) haritaya yollayacaktır. Arayüzü olmadığı için kazara kapatılması mümkün değildir.*



---

## 🗺️ Harita Üzerinde İzleme

Servis ilk paketi gönderdikten sonra (yaklaşık 1-2 dakika içinde), istasyonunuzu canlı olarak [aprs.fi](https://aprs.fi/) üzerinden takip edebilirsiniz:

👉 `https://aprs.fi/#!call=a%2F<ÇAGRI_İŞARETİNİZ>` (Örn: `https://aprs.fi/#!call=a%2FN0CALL-9`)
