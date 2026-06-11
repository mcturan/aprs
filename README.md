# 📻 Linux, Windows ve Android (Termux) Arka Plan APRS Beacon İstemcisi

Bu proje; Linux, Windows ve Android (Termux) tabanlı cihazlarda sistem açılışında arka planda tamamen otomatik çalışan, sistem kaynaklarını tüketmeyen hafif bir **APRS-IS (Automatic Packet Reporting System - Internet Service)** konum bildirim istemcisidir.

Herhangi bir grafik arayüze (GUI) ihtiyaç duymadan çalışır. İstasyonunuzun konumunu, durum mesajını ve harita simgesini periyodik olarak gönderir.

---

## ✨ Özellikler

- **Sıfır Bağımlılık:** Sadece standart Python 3 kütüphanelerini kullanır (pip ile ek paket yüklemeye gerek yoktur).
- **Otomatik Başlangıç:** 
  - **Linux:** `systemd` kullanıcı servisi (`systemd --user`) ve `loginctl linger` kullanır. Bilgisayar açıldığında kullanıcı oturum açmasa dahi arka planda otomatik başlar.
  - **Windows:** Windows Görev Zamanlayıcı (Task Scheduler) ile kullanıcı oturum açtığında görünmez şekilde (konsol açılmadan) çalışır.
  - **Android (Termux):** `Termux:Boot` eklentisi aracılığıyla telefon açıldığında otomatik başlar ve arka planda çalışır.
- **Otomatik GPS (Android):** Telefonun dahili GPS alıcısından anlık konumu çekebilir (hızlı çalışması için önce en son önbelleğe alınan konumu sorgular, bulamazsa güncel GPS kilidi dener).
- **Passcode Üretici:** Kurulum esnasında çağrı işaretiniz için gerekli olan APRS-IS şifresini (passcode) otomatik hesaplar.
- **Düşük Kaynak Tüketimi:** Sürekli TCP bağlantısı açık tutmak yerine belirtilen dakikada bir sunucuya bağlanıp paketi iletir ve bağlantıyı kapatır.

---

## 🚀 Kurulum ve Çalıştırma

### 🐧 Linux Kurulumu
Bu projeyi tek bir komutla doğrudan kurabilir veya güncelleyebilirsiniz:
```bash
bash <(curl -sL https://raw.githubusercontent.com/mcturan/aprs/main/install.sh)
```
*(Kurulum bittikten sonra log takibi için: `tail -f ~/.aprs-beacon/aprs_beacon.log`)*

---

### 💻 Windows Kurulumu
Windows üzerinde bu beacon'ı arka planda sessizce çalıştırmak için:

1. Depoyu indirip klasöre gidin. **PowerShell'i** açın:
   ```powershell
   cd path/to/aprs
   ```
2. **Kurulum Sihirbazını Çalıştırın**:
   ```powershell
   PowerShell -ExecutionPolicy Bypass -File install.ps1
   ```
*(Görev Zamanlayıcıya eklenir. Log takibi için: `Get-Content -Path "$HOME\.aprs-beacon\aprs_beacon.log" -Wait -Tail 10`)*

---

### 📱 Android (Termux) Kurulumu
Telefonunuzun GPS alıcısını kullanarak arka planda konum göndermesini istiyorsanız Termux üzerinde kurulumu gerçekleştirebilirsiniz.

#### 1. Ön Hazırlık (İzinler ve API)
- Google Play veya F-Droid üzerinden **Termux** ve **Termux:API** (ayrıca otomatik başlasın istiyorsanız **Termux:Boot**) uygulamalarını yükleyin. (Not: İmza uyuşmazlığı olmaması için tüm uygulamaları aynı mağazadan indirin).
- Android Ayarları $\rightarrow$ Uygulamalar $\rightarrow$ **Termux:API** uygulamasının izinlerinden **Konum (Location)** iznini aktif edin.

#### 2. Termux Paketlerini Kurun
Termux uygulamasını açın ve Android API entegrasyonu ile gerekli bağımlılıkları yükleyin:
```bash
pkg update && pkg install termux-api python -y
```

#### 3. Kurulum Sihirbazını Çalıştırın
Aşağıdaki komutu kopyalayıp Termux ekranına yapıştırarak çalıştırın:
```bash
bash <(curl -sL https://raw.githubusercontent.com/mcturan/aprs/main/install.sh)
```

Sihirbaz esnasında:
- **Konum Ayarı (Android)** sorusuna `Y` (Evet) yanıtını verin. Bu sayede manuel koordinat girmeniz istenmez, sistem telefonun dahili GPS alıcısını kullanacak şekilde ayarlanır.
- **Sistem açılışında otomatik başlasın mı?** sorusuna `Y` yanıtını vererek başlangıç kaydını yapın.

*(Log takibi için: `tail -f ~/.aprs-beacon/aprs_beacon.log` | Servisi durdurmak için: `pkill -f aprs_beacon.py`)*

---

## 🗺️ Harita Üzerinde İzleme

Servis ilk paketi gönderdikten sonra, istasyonunuzu canlı olarak [aprs.fi](https://aprs.fi/) üzerinden takip edebilirsiniz:

👉 `https://aprs.fi/#!call=a%2F<ÇAGRI_İŞARETİNİZ>` (Örn: `https://aprs.fi/#!call=a%2FN0CALL-9`)
