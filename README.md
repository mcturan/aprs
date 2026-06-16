# 📻 Linux ve Windows Arka Plan APRS Beacon İstemcisi

Bu proje; Linux ve Windows tabanlı cihazlarda sistem açılışında arka planda tamamen otomatik çalışan, sistem kaynaklarını tüketmeyen hafif bir **APRS-IS (Automatic Packet Reporting System - Internet Service)** konum bildirim istemcisidir.

Herhangi bir grafik arayüze (GUI) ihtiyaç duymadan çalışır. İstasyonunuzun konumunu, durum mesajını ve harita simgesini periyodik olarak gönderir.

---

## ✨ Özellikler

- **Sıfır Bağımlılık:** Sadece standart Python 3 kütüphanelerini kullanır (pip ile ek paket yüklemeye gerek yoktur).
- **Otomatik Başlangıç:** 
  - **Linux:** `systemd` kullanıcı servisi (`systemd --user`) ve `loginctl linger` kullanır. Bilgisayar açıldığında kullanıcı oturum açmasa dahi arka planda otomatik başlar.
  - **Windows:** Windows Görev Zamanlayıcı (Task Scheduler) ile kullanıcı oturum açtığında görünmez şekilde (konsol açılmadan) çalışır.
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
Bu projeyi tek bir komutla doğrudan kurabilir veya güncelleyebilirsiniz. **PowerShell** ekranında aşağıdaki komutu çalıştırmanız yeterlidir:
```powershell
PowerShell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/mcturan/aprs/main/install.ps1 | iex"
```
*(Görev Zamanlayıcıya eklenir. Log takibi için: `Get-Content -Path "$HOME\.aprs-beacon\aprs_beacon.log" -Wait -Tail 10`)*

---

## 🗺️ Harita Üzerinde İzleme

Servis ilk paketi gönderdikten sonra, istasyonunuzu canlı olarak [aprs.fi](https://aprs.fi/) üzerinden takip edebilirsiniz:

👉 `https://aprs.fi/#!call=a%2F<ÇAGRI_İŞARETİNİZ>` (Örn: `https://aprs.fi/#!call=a%2FN0CALL-9`)

---

## 🎛️ Çoklu Profil ve Yönetim Arayüzü (APRS Manager)

Bu güncelleme ile artık aynı anda birden fazla APRS beacon'ını (örneğin farklı SSID veya çağrı işaretleri ile) çalıştırabilir ve bunları görsel arayüzden yönetebilirsiniz.

### Özellikler:
- **Grafik Arayüz (GUI):** Sisteminizdeki tüm profilleri listeler, aktif/pasif durumlarını gösterir, tek tıklamayla başlatıp durdurmanızı sağlar. **Aydınlık (light) temalı, temiz ve modern bir tasarıma sahiptir.**
- **APRS Chat (Mesajlaşma):** Her profile ait özel "Chat" butonu ile diğer çağrı işaretlerine veya SMS/E-posta ağ geçitlerine (örneğin SMSGTE) doğrudan APRS kısa mesajı gönderip alabilirsiniz.
- **Özelleştirilebilir Perşembe Etkinliği (APRS Thursday):** ANSRVR grubuna perşembe günleri gönderilen katılım mesajı metnini ve saatini her profil için ayrı ayrı özelleştirebilirsiniz.
- **Otomatik Güncelleme Kontrolü:** Program günlük olarak arka planda en son sürümü kontrol eder, yeni bir sürüm varsa otomatik yükler ve sizi bilgilendirir.
- **Sistem Tepsisi (Tray Icon):** Uygulama kapatıldığında arka planda sistem tepsisinde (görev çubuğunda) çalışmaya devam eder. Hızlıca durumları izleyebilir ve profilleri kontrol edebilirsiniz.
- **Log İzleyici:** Her profile ait logları arayüz üzerinden canlı ve anlık olarak takip edebilirsiniz.
- **CLI Modu:** GUI kütüphaneleri yüklü olmayan veya grafik arayüzü bulunmayan (headless) sunucularda terminal komutları ile tüm profilleri kolayca yönetebilirsiniz.

### Kullanım:
Yönetim panelini başlatmak için:
```bash
python3 ~/.aprs-beacon/aprs_manager.py gui
```
*(Uygulama menüsündeki "APRS Multi-Beacon Manager" kısayolunu da kullanabilirsiniz).*

Terminal üzerinden (CLI) yönetim komutları:
- Profilleri Listele: `python3 ~/.aprs-beacon/aprs_manager.py list`
- Yeni Profil Ekle: `python3 ~/.aprs-beacon/aprs_manager.py create`
- Profil Düzenle (Güncelle): `python3 ~/.aprs-beacon/aprs_manager.py edit`
- Profili Başlat: `python3 ~/.aprs-beacon/aprs_manager.py start <profil_adi>`
- Profili Durdur: `python3 ~/.aprs-beacon/aprs_manager.py stop <profil_adi>`
- Profili Sil: `python3 ~/.aprs-beacon/aprs_manager.py delete <profil_adi>`
- Ayarları Dışa Aktar: `python3 ~/.aprs-beacon/aprs_manager.py export [yedek_yolu.json]`
- Ayarları İçe Aktar: `python3 ~/.aprs-beacon/aprs_manager.py import <yedek_yolu.json>`
- Uygulamayı Güncelle (Git Pull): `python3 ~/.aprs-beacon/aprs_manager.py update`

---

## 🗑️ Tamamen Kaldırma (Uninstall)

Uygulamayı, arka plan servislerini, zamanlanmış görevleri ve tüm yapılandırma/günlük dosyalarını sisteminizden tamamen temizlemek için aşağıdaki adımları uygulayabilirsiniz:

### 🐧 Linux (Tek Komutla Kaldırma)
Aşağıdaki komutu terminale yapıştırarak tüm servisleri durdurup uygulamayı silebilirsiniz:
```bash
systemctl --user stop aprs-beacon.service 2>/dev/null
systemctl --user disable aprs-beacon.service 2>/dev/null
rm -f ~/.config/systemd/user/aprs-beacon.service
systemctl --user daemon-reload
rm -rf ~/.aprs-beacon
```

---

### 💻 Windows (PowerShell ile Kaldırma)
**PowerShell** ekranında aşağıdaki komutları sırasıyla çalıştırarak zamanlanmış görevi kaldırıp dosyaları temizleyebilirsiniz:
```powershell
Stop-ScheduledTask -TaskName "APRSBeacon" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "APRSBeacon" -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -Path "$env:USERPROFILE\.aprs-beacon" -Recurse -Force -ErrorAction SilentlyContinue
```

---



