# -*- coding: utf-8 -*-
"""Türkçe referans metinleri (5. sekme).

Motor (mqb_contitool) yalnız RU/EN ürettiği için CP banka tablosu ve adım adım
rehber burada Türkçe olarak tutulur. Banka verileri motordan (SlotSpec) gelir.
"""

MODULE_TR = {
    "17": "Gösterge tablosu / immobilizer (J285, AID / Virtual Cockpit)",
    "09": "Merkezi elektrik / BCM (J519)",
    "13": "Adaptif hız sabitleyici / ACC radarı (J428)",
    "15": "Hava yastığı beyni (J234)",
    "47": "Ses sistemi / amfi — Canton, Dynaudio, Fender (J525)",
    "57": "TV tuner (R78)",
    "5F": "Multimedya ünitesi MIB1 / MIB2 / MIB3 (J794)",
    "3C": "Şerit değiştirme asistanı 1 / Side Assist master (J769)",
    "CF": "Şerit değiştirme asistanı 2 / Side Assist slave (J770)",
    "3D": "Özel amaçlı modül (J608)",
    "A5": "Ön sürüş destek kamerası MFK (R242, 3Q0 / 2Q0)",
    "8C": "Hibrit / EV yüksek voltaj batarya yönetimi (J840)",
    "19": "Gateway'in kendi ana anahtarı (GFA, key_type=3) — DOKUNMA",
}


def banks_table(slots) -> str:
    """CP banka referans tablosunu Türkçe üretir."""
    lines = []
    lines.append("CONTINENTAL J533 GATEWAY (3Q0 907 530 xx) — 12 CP BANKASI")
    lines.append("Renesas RH850/F1L · R7F7010543 / R7F7010563 · 64 KB DataFlash")
    lines.append("")
    lines.append("Her banka DataFlash'ta İKİ kopya halinde durur (asıl + 0x80 ayna),")
    lines.append("0x55555555 başlık sözcüğü ve IEEE CRC-32 (zlib.crc32) ile korunur.")
    lines.append("")
    hdr = ("#", "ECU", "Modül", "DataFlash", "NvM", "95640", "UDS istek/yanıt", "CP CAN")
    lines.append(f"{hdr[0]:<3} {hdr[1]:<4} {hdr[2]:<52} {hdr[3]:<16} {hdr[4]:<5} "
                 f"{hdr[5]:<7} {hdr[6]:<18} {hdr[7]}")
    lines.append("-" * 150)
    for s in slots:
        name = MODULE_TR.get(s.ecu_addr, s.short_en)
        off1 = s.off1 if isinstance(s.off1, int) else int(str(s.off1), 0)
        off2 = s.off2 if isinstance(s.off2, int) else int(str(s.off2), 0)
        nvm = s.nvm_id if isinstance(s.nvm_id, int) else int(str(s.nvm_id), 0)
        mask = s.mask_bit if isinstance(s.mask_bit, int) else int(str(s.mask_bit), 0)
        suf = getattr(s, "can_suffix", None)
        can = f"0x17FC01{suf:02X}/0x17FE01{suf:02X}" if isinstance(suf, int) else "—"
        req = s.uds_req if str(s.uds_req).startswith("0x") else f"0x{int(str(s.uds_req), 0):03X}"
        rsp = s.uds_resp if str(s.uds_resp).startswith("0x") else f"0x{int(str(s.uds_resp), 0):03X}"
        lines.append(f"{s.slot:<3} {s.ecu_addr:<4} {name:<52} "
                     f"0x{off1:04X}/0x{off2:04X} 0x{nvm:02X}  0x{mask:04X}  "
                     f"{req}/{rsp:<10} {can}")
    lines.append("")
    lines.append("MASTER (banka 0): DataFlash 0xDA00 / 0xDA80 · NvM 0x7B · UDS 710/77A")
    lines.append("Gatewway'in kendi uygulama anahtarıdır (GFA) — CP bağlarken DEĞİŞTİRME.")
    lines.append("")
    lines.append("DataFlash yerleşimi (64 KB):")
    lines.append("  0x0000-0x007F  ZDC başlığı (dataset kimliği, DID F1A0/F1A1)")
    lines.append("  0x0080-0x303F  7 ZDC bloğu (araç parametreleri; Base, MKE, FPA, Aux, GW, Cal, BEM)")
    lines.append("  0x3040-0xBFFF  FDL havuzu (boş, 0xFF)")
    lines.append("  0xC000-0xCBFF  12 CP bankası (#1..#12) — 2 × 128 bayt")
    lines.append("  0xCC00-0xD8FF  ayrılmış anahtar slotları")
    lines.append("  0xD900-0xD9FF  95640 blok 0x5E için ICUS0 AES-CMAC etiketleri")
    lines.append("  0xDA00-0xDAFF  gateway ana anahtarı (GFA)")
    lines.append("  0xDB00-0xDCFF  SWaP RSA-1024 modulus önbelleği (0xDB04) + VCRN (0xDC0C) + CRC-32 (0xDCE4)")
    lines.append("  0xDD00-0xE83F  15 adet SWaP FSC sertifika slotu (düz VIN +0x10)")
    lines.append("  0xE840-0xF0BF  SWaP sayaçları / NvM düzen sürümü")
    lines.append("")
    lines.append("CodeFlash içindeki iki açık anahtar (RSA-1024, e = 3):")
    lines.append("  SWaP (FeC/FSC doğrulaması) : 0x02620E  — 128 bayt modulus")
    lines.append("  FBL  (bootloader/.odx imza): 0x0000A2F7 — Sector 5, ayrıca üs alanı 0x0000A277")
    return "\n".join(lines)


def guide_text(public_key: str = "—") -> str:
    """Adım adım Türkçe çalışma rehberi."""
    return f"""ADIM ADIM REHBER — MQB J533 GATEWAY (3Q0 907 530)

Pakette gömülü public key (4.1'de gateway'e yazılır):
  N = {public_key} · e = 3

────────────────────────────────────────────────────────────────────────
0) ÖNCE OKU — BU ARAÇ TEK TUŞLA ÇALIŞAN BİR OBD ARACI DEĞİLDİR
────────────────────────────────────────────────────────────────────────
• Gateway'i OBD'den yamalayamazsın: RH850/F1L MCU fabrikada okuma korumalıdır.
• Gereken: gateway'i söküp bench'te voltage glitch programmer (VVDI Multi-Prog,
  CG100X, Orange-5 RH850 Glitch) ile CodeFlash + DataFlash okumak.
• Hedef ECU'nun 16 baytlık IKA (K3) anahtarı da önceden hedef modülün kendi
  dump'ından çıkarılmış olmalı — bu anahtar CAN/UDS üzerinden ASLA okunamaz.
• Yazmadan önce TAM YEDEK al: CodeFlash (1,5 MB), DataFlash (64 KB),
  Uflash (32 KB) ve kart üzerindeki harici 95640 SPI EEPROM (8 KB).

────────────────────────────────────────────────────────────────────────
1) DUMP OKUMA — PROGRAMLAYICI AYARI
────────────────────────────────────────────────────────────────────────
• Gateway 3Q0 907 530 içindeki gerçek silikon R7F7010543 / R7F7010563'tür ve
  64 KB DataFlash'ı vardır.
• Programlayıcıda "3Q0 907 530 / MQB Gateway Continental" profilini seç
  veya elle R7F7010543 / R7F7010563 (64 KB) seç.
• ASLA 32 KB R7F7010343 profili kullanma: 12 CP bankası, GFA anahtarı ve
  SWaP sertifikaları DataFlash'ın üst yarısındadır (0xC000-0xF0BF) — 32 KB
  okuma bunları tamamen keser ve program eksik dump'ı reddeder.

────────────────────────────────────────────────────────────────────────
2) DUMP İNCELE (1. sekme)
────────────────────────────────────────────────────────────────────────
• CodeFlash.bin (1.523.200 veya 1.572.864 bayt), DataFlash.bin (65.536 bayt),
  Uflash.bin (32.768 bayt) dosyalarını seç veya "Otomatik tara".
• Bakılacaklar: App CRC-16 (@0xC21C) OK mi, CP kancası STOCK mu, 95640 maske
  durumu, CCP gate / blacklist / OTP A167 kilitleri, SWaP modulus stok mu.
• 12 banka tablosunda hangi bankaların dolu olduğunu gör (BOŞ / DOLU).

────────────────────────────────────────────────────────────────────────
3) BİLEŞEN KORUMASI (CP / KSCHUTZ) BAĞLAMA (2. sekme)
────────────────────────────────────────────────────────────────────────
Kullanılmış veya sonradan takılan bir ECU'yu gateway'e bağlamak için:
 a) CodeFlash'a hibrit KSCHUTZ kancası kurulur (38 baytlık trampoline).
    Fabrika ECU'ları SHE (ICUS0 CMD_LOAD_KEY 0x40) ile çalışmaya devam eder,
    yeni/düz anahtarlı ECU'lar IKA (CMD_LOAD_PLAIN_KEY 0x10) ile doğrulanır.
 b) DataFlash'ta seçilen bankaya 16 baytlık düz IKA anahtarı yazılır.
 c) App CRC-16 otomatik yeniden hesaplanır (FBL FF01 kontrolü geçsin diye).
• Daha önce hiç kullanılmamış (FF..FF) bir bankaya modül takıyorsan
  "95640 EEPROM maske atlaması" işaretli olmalı — harici EEPROM sökülmez.
• Çıktı: CodeFlash.patched.bin + DataFlash.patched.bin. Cihaza yazmaz.
• Yazma sırası: önce CodeFlash+DataFlash (bench), sonra gateway'i topla.

────────────────────────────────────────────────────────────────────────
4) ENGINEERING MODE (3. sekme) — imzasız OBD yazma + canlı CCP
────────────────────────────────────────────────────────────────────────
• Uflash bootloader'daki RSA kontrolü atlanır (0x0100342A): OBD'den imzasız
  .odx yazılabilir (ODIS-E / VCP, rutin 31 01 02 02).
• CodeFlash'ta ASAM CCP erişimi (Feature 0x80/0x81/0x83) ve CCP adres kara
  listesi açılır; CAN RAM-Loader kilidi (OTP 0xA167) atlanır.
• "Fabrika kilitlerini geri yükle" seçeneği her şeyi stoğa döndürür.
• Çıktı: CodeFlash.eng.bin + Uflash.eng.bin.

────────────────────────────────────────────────────────────────────────
5) SWaP / FeC (4. sekme)
────────────────────────────────────────────────────────────────────────
5.1 — PUBLIC KEY'İ GATEWAY'E GÖM
    Hedef: SWaP (FeC/FSC doğrulaması), FBL (.odx imza doğrulaması) veya ikisi.
    Yapılan: 128 baytlık modulus N yazılır (SWaP 0x02620E, FBL 0x0000A2F7),
    CodeFlash App CRC-16 yeniden hesaplanır.
    DataFlash da verilirse NvM 0x7C önbelleği (0xDB04) ve CRC-32 de güncellenir
    — ÇALIŞAN bir gateway'de FSC doğrulaması bu önbelleği okur, yani
    DataFlash'ı da yazmadan araç yeni sertifikayı kabul etmez.

5.2 — FSC SERTİFİKASI ÜRET
    Şase (VIN, 17 karakter) + VCRN (5 bayt / 10 hex; DataFlash dump'ı varsa
    "DataFlash'tan oku" ile DID 0x3C03 değerinden alınır) gir.
    İstediğin SWaP kodlarını işaretle (14 bilinen kod) veya özel kod yaz.
    171 baytlık FSC yapısı:
      0        : 0x11 (FSC etiketi)
      1        : 0x02 (sürüm 2)
      2..5     : FeC kodu (uint32 big-endian, örn. 10000100 = FPA)
      6        : 0x03 (VCRN seçici)
      7..11    : 5 baytlık VCRN
      12..29   : 17 karakter VIN + 0x00 (18 bayt; hepsi 0x00 = VIN'siz/joker)
      30..33   : Unix zaman damgası (yeniden aktivasyonda ARTAN olmalı)
      34..42   : 9 bayt geçerlilik (0x00 = kalıcı/sınırsız)
      43..170  : 128 bayt RSA-1024 (e=3) imza — RIPEMD-160 + PKCS#1 v1.5
    Önemli: VCRN araca özeldir; yanlış VCRN ile sertifika araçta geçersiz olur.

5.3 — ARACA YAZMA (iki yol)
    a) UDS ile: 10 40 → 27 03/04 (SA 20103) → 2E 3C 01 <171 bayt>
       → 31 01 C0 01 → 31 03 C0 01.  (500 kbit/s, 0x710 → 0x77A, ISO-TP şart)
       VCP (Sonderfunktion / SWaP-FSC) veya CANtieCAR / python-udsoncan.
    b) Adaptasyon ile: ODIS/VCDS → Adaptasyon → "Transfer SWaP function"
       alanına 4.2'deki Kopyala düğmesiyle aldığın HEX'i (342 karakter) yapıştır.
       Gateway bu sayıyı 171 bayta çevirip imzayı senin public key'inle doğrular.
    Her iki yolda da önce 5.1 yapılmış olmalı; aksi halde imza reddedilir.

5.4 — DOĞRULAMA
    • DID 0x3C01 geri oku (sertifika yerleşti mi)
    • DID 0x3C00 / FeC listesinde kodun AKTİF göründüğünü kontrol et
    • ODIS'te "SWaP-Status" ekranı
    • Gateway'de 15 FSC slotu vardır; dolu slot üzerine yazarken zaman damgası
      artan olmalı.

────────────────────────────────────────────────────────────────────────
6) SIK HATALAR (NRC) VE ANLAMLARI
────────────────────────────────────────────────────────────────────────
• 0x33 securityAccessDenied → 27 03/04 login yapılmadı veya yanlış
• 0x24 requestSequenceError → istek sırası bozuk (10 40 → 27 → 2E → 31)
• 0x31 requestOutOfRange → DID/rutin desteklenmiyor (yanlış ECU'ya gidiyorsun)
• 0x72 generalProgrammingFailure → imza doğrulanamadı:
    - public key gateway'e yazılmamış (5.1 eksik) veya
    - VCRN eşleşmiyor veya
    - sertifika zaman damgası eski
• 0x7F serviceNotSupportedInActiveSession → oturum yükseltilmedi (10 40/10 03)

────────────────────────────────────────────────────────────────────────
7) BRICK OLURSA — KURTARMA SEVİYELERİ
────────────────────────────────────────────────────────────────────────
A) FBL sağlam, uygulama bozuk: VAS 6154A + ODIS-E 17/18 ile stok FRF yükle.
B) Gateway açık, bench'te: 12 V / 3 A besleme, CAN-H T12a-1, CAN-L T12a-2,
   500 kbit/s, 120 Ω sonlandırma; elle UDS:
   10 02 → 27 → 31 01 FF00 → 34/36/37 → 31 01 02 02 → 11 01
C) FBL de bozuksa: E2 emulator + Renesas Flash Programmer (RFP V3) ile JTAG
   üzerinden Bank0 imajını yaz. OCD ID doğrulaması / OTP koruması aşılamıyorsa
   MCU değişimi gerekir.

────────────────────────────────────────────────────────────────────────
8) YASAL / ETİK
────────────────────────────────────────────────────────────────────────
Bu araç yalnız kendi aracında onarım ve araştırma içindir. Satışı, ücretli
paketlerle dağıtımı ve ücretli "aktivasyon" hizmeti yasaktır. Kaynak atfı
korunmalıdır: mqb_contitool — PerkTheFox (github.com/perkthefox/mqb_contitool).
Hiçbir firmware veya OEM kodu bu programın içinde değildir.
"""
