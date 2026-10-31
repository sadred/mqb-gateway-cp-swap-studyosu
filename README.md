# Denizli Garaj MQB Gateway CP & SWaP Stüdyo

Continental VAG MQB **J533 Gateway** (`3Q0 907 530 AC/AG/AJ/AL/AM/AN/AP/AQ/AR`, Renesas `RH850/F1L`
`R7F7010543` / `R7F7010563`, 64 KB DataFlash) için Türkçe masaüstü aracı:

- **Bileşen koruması (CP / `KSCHUTZ` / `#MoLaLi`) bağlama** — kullanılmış veya sonradan takılan ECU'ları
  (MIB2 `5F`, gösterge `17`, ACC `13`, amfi `47`, kamera `A5` …) gateway'e bağlar.
- **Engineering Mode** — Uflash bootloader'a RSA kontrolünü atlayan yama (OBD'den imzasız `.odx`),
  CodeFlash'ta ASAM CCP erişimi ve CAN RAM-Loader kilidinin açılması.
- **RSA-1024 (`e = 3`) / SWaP** — kendi anahtar çiftini üret, gateway'e göm, 171 baytlık SWaP/FeC
  (FSC) sertifikası ve 128 baytlık firmware imzası (`<FW-SIGNATURE>`) üret.
- **Dump inceleme** — CodeFlash / DataFlash / Uflash analizi: 12 CP bankasının durumu, SWaP slotları,
  VCRN, CRC'ler, CP kancası ve engineering kilitleri.

Yama motoru **exe'nin içine gömülüdür**: harici `.py` dosyası, kurulum veya internet bağlantısı
gerekmez. Program internete **bağlanmaz**, hiçbir şey indirmez.

## Özellikler

| Sekme | Ne yapar |
|---|---|
| **1 · Dump İncele** | Otomatik tarama (isim + boyut doğrulaması) veya elle seçim; 12 CP bankası tablosu (`BOŞ`/`DOLU (she\|plain)`), SWaP özeti, ham rapor |
| **2 · CP Bağla** | `patch-cflash` (hibrit KSCHUTZ kancası + App CRC-16) + `set-cp-key` (16 baytlık düz IKA); 95640 EEPROM maske atlaması, banka boşaltma |
| **3 · Engineering Mode** | `patch-engineering` — Uflash RSA-free FBL + CCP erişimi + RAM-Loader; `--restore-stock` ile geri alma |
| **4 · RSA & SWaP** | Üstte **public key** satırı (kopyalanabilir) · **4.1** açık anahtarı göm (SWaP/FBL/ikisi) · **4.2** **SWaP seç + FSC oluştur** (şase + VCRN + işaretli SWaP kodları) · **4.3** firmware imzası |
| **5 · Referans** | 12 banka referans tablosu ve adım adım rehber (motorun kendi dokümanı) |

> [!IMPORTANT]
> **Anahtar pakete gömülüdür** — `assets/anahtar/swap_rsa1024.json` (+ `.private.pem`). Program anahtar
> **üretmez, sormaz, seçtirmez**; 4.1'de açık anahtarı gateway'e yazar, 4.2/4.3'te aynı anahtarın özel
> kısmıyla imzalar. Kullanılan public key (modulus, e=3) sekmenin üstünde görünür ve **Kopyala** ile alınır.
>
> ⚠ Bu depo **public** olduğu için gömülü **özel anahtar da herkese açıktır**: aynı anahtarı kullanan
> bir gateway'e herkes geçerli FSC üretebilir. Sadece kendi araçların için sorun değil; ticari/kapalı
> kullanım istersen `assets/anahtar/` içeriğini kendi özel anahtarınla değiştir ve depoyu private yap.

Her bölümün altında **sonuç etiketi** vardır (✔ üretildi / ✘ sebep), yani ne olduğu günlüğe bakmadan
görünür. `sign-fsc` için **VCRN zorunludur**: alanı elle doldur (10 hex, örn. `0102030405`) veya
DataFlash dump'ı varsa **Oku** düğmesiyle DID `0x3C03` değerini çek.

**Transfer SWaP (adaptasyon):** her SWaP kodunun yanında **Kopyala** düğmesi vardır (yalnız o kodun 342 karakterlik
HEX'ini üretip panoya alır). Üstteki **"Transfer SWaP HEX (kopyala)"** düğmesi ayrı pencere açmaz;
**kopyalama menüsü** açar: her FeC için `HEX kopyala · FeC xxxxxxxx (342 karakter)`, çoklu seçimde
`Tümünü kopyala`, ayrıca `HEX'i .txt dosyasına yaz` (sadece HEX). Değer 171 baytlık FSC'nin HEX'idir. Şart: önce **4.1** ile
senin public key'in gateway'e yazılmış olmalı, yoksa imza reddedilir.

**4.2 akışı:** şase (VIN) + VCRN gir → istediğin SWaP kodlarını **işaretle** (14 bilinen kod, Türkçe adlarıyla)
veya `Özel kod(lar)` alanına virgülle yaz → **"Seçilen SWaP'lar için FSC oluştur"**. Her kod için ayrı
`fsc_<kod>.fsc` üretilir. Şase/VCRN bir sonraki açılışta hatırlanır; gerekirse VCRN **DataFlash'tan oku** ile çekilir.

> [!IMPORTANT]
> **4.2 için DataFlash şart değil, ama araçta çalışması için gerekir.** Modulus CodeFlash'a yazılır
> (`0x02620E`, 128 bayt + App CRC-16). Çalışan bir gateway'de FSC doğrulaması modulus'u
> **DataFlash NvM `0x7C` (`0xDB04`) önbelleğinden** okur — DataFlash da verilmezse araç yeni
> sertifikayı reddeder. Program bunu uyarı olarak gösterir.

Her düğme/alan üzerine gelindiğinde **Türkçe açıklama** gösterir.

## Kurulum

**Hazır exe (önerilen):** `dist/MQB-Gateway-CP-SWaP-Studyosu.exe` — tek dosya, Python gerekmez,
motor gömülü. Kod imzalı (self-signed, `assets/denizli-garaj-kod-imza.cer`).

**Kaynaktan:**

```bash
python gateway_studio.py        # Python 3.9+, tkinter, harici paket yok
MQB-Gateway-Studyosu.bat        # çift tıkla
```

## Kullanım akışı (tipik retrofit)

1. Gateway'i sök, bench'te **voltage glitch** programmer ile `CodeFlash.bin` (1.5 MB),
   `DataFlash.bin` (64 KB) ve mümkünse `Uflash.bin` (32 KB) oku.
   ⚠ Programmer'da **64 KB** DataFlash profili seç (`R7F7010543`/`R7F7010563`);
   `32 KB` profil tüm CP bankalarını keser.
2. Bağlanacak ECU'nun **16 baytlık IKA (K3) anahtarını** kendi dump'ından çıkar.
   Bu anahtar CAN/UDS üzerinden okunamaz.
3. **1 · Dump İncele** → dump'ları yükle, banka tablosunu gör.
4. **2 · CP Bağla** → bankayı işaretle, IKA anahtarını gir → `CodeFlash.patched.bin` +
   `DataFlash.patched.bin` üretilir (otomatik doğrulanır).
5. Yamalı dosyaları programmer ile geri yaz, gateway'i araca tak.

## Exe derleme

```bash
python -m venv .build-venv
.build-venv/Scripts/python -m pip install pyinstaller
.build-venv/Scripts/python -m PyInstaller --noconfirm --onefile --windowed ^
  --icon assets/logo.ico --add-data "assets;assets" --add-data "motor;motor" ^
  --hidden-import argparse --hidden-import atexit --hidden-import base64 --hidden-import codecs ^
  --hidden-import collections --hidden-import dataclasses --hidden-import hashlib ^
  --hidden-import secrets --hidden-import select --hidden-import signal --hidden-import struct ^
  --hidden-import unicodedata --hidden-import zlib --hidden-import random ^
  --name MQB-Gateway-CP-SWaP-Studyosu gateway_studio.py
```

`motor/` klasörü `conti_cp_tool.py`'nin (PerkTheFox) yamasız kopyasıdır ve gömülür.

## Kod imzası

exe, **Denizli Garaj** adına üretilmiş self-signed sertifikayla imzalanır (SHA-256, zaman damgalı).
Bu makinede sertifika `Trusted Root` + `Trusted Publisher` depolarında olduğu için uyarı çıkmaz.
Başka bilgisayarda `assets/denizli-garaj-kod-imza.cer` dosyasını aynı depolara ekleyin.

## ⚠ Uyarılar

- Bu araç **tek tuşla çalışan bir OBD aracı değildir**: gerçek bench dump'ı ve hedef ECU'nun IKA
  anahtarı olmadan hiçbir işlem yapılamaz.
- Yanlış dump yazımı gateway'i **brick** edebilir. Yazmadan önce CodeFlash, DataFlash, Uflash ve
  harici `95640` EEPROM'un tam yedeğini al.
- Bu program hiçbir firmware veya OEM kodu içermez; tüm dump dosyaları kullanıcının diskindedir.

## Kaynak ve lisans

- Kaynak / yama motoru: **mqb_contitool — PerkTheFox** · https://github.com/perkthefox/mqb_contitool
- Fork: https://github.com/sadred/mqb_contitool
- Lisans: **non-commercial / Right-to-Repair** — aracın satışı, ücretli paketlerle dağıtımı ve
  ücretli "aktivasyon" hizmeti yasaktır. Atıf korunmalıdır:
  [vwhacking.antonperk.com](https://vwhacking.antonperk.com) ·
  [Drive2](https://www.drive2.ru/users/perkthefox/) · [Telegram](https://t.me/perkthefox)
