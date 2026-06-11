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

### 2. Ayarları Düzenleyin
`install.sh` dosyasının en üstünde yer alan yapılandırma alanını kendi çağrı işaretiniz, konumunuz ve mesajınıza göre düzenleyin:

```bash
# ==============================================================================
# APRS YAPILANDIRMASI
# ==============================================================================
CALLSIGN="TA1XBA-2"
PASSCODE="17082"                       # Boş bırakılırsa otomatik hesaplanır
LATITUDE="41.028399"
LONGITUDE="28.976864"
SYMBOL_TABLE="/"                       # / -> Birincil tablo
SYMBOL_CODE="X"                        # X -> Helikopter simgesi
COMMENT="linktr.ee/MCTURAN | ARC"
INTERVAL_MINUTES=20
# ==============================================================================
```

### 3. Kurulum Betiğini Çalıştırın
Betiğe çalıştırma izni verip çalıştırın:
```bash
chmod +x install.sh aprs_beacon.py
./install.sh
```

Bu komut ile:
- `~/.aprs-beacon/` dizini altına ayarlarınız (`config.json`) yazılır.
- `aprs_beacon.py` ana scripti buraya kopyalanır.
- `~/.config/systemd/user/aprs-beacon.service` dosyası oluşturulur.
- Arka plan servisi aktif edilip başlatılır.
- Bilgisayar başladığında otomatik çalışması için **linger** modu aktif edilir.

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

## 🗺️ Harita Üzerinde İzleme

Servis ilk paketi gönderdikten sonra (yaklaşık 1-2 dakika içinde), istasyonunuzu canlı olarak [aprs.fi](https://aprs.fi/) üzerinden takip edebilirsiniz:

👉 `https://aprs.fi/#!call=a%2F<ÇAGRI_İŞARETİNİZ>` (Örn: `https://aprs.fi/#!call=a%2FTA1XBA-2`)
