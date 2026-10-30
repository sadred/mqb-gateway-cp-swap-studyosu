# Lisans / License — Denizli Garaj MQB Gateway CP & SWaP Stüdyo

Copyright © 2026 Denizli Garaj

## Türkçe

Bu yazılım **ücretsiz** olarak, **ticari olmayan** amaçlarla (kişisel araştırma, hobi, kendi aracında
retrofit, sağdan onarım / Right-to-Repair) kullanılmak üzere yayınlanmıştır.

İzin verilenler:

- Yazılımı kendi aracında / kendi atölyende ücretsiz kullanmak,
- Kaynak kodu incelemek, kopyalamak, değiştirmek ve değiştirilmiş sürümü aynı şartlarla paylaşmak,
- İçeriği forum, blog ve video gibi ücretsiz topluluk alanlarında paylaşmak (atıf korunarak).

Yasak olanlar:

- Yazılımı **satmak**, ücretli paketlerle birlikte dağıtmak, ücretli "aktivasyon"/"kodlama" hizmetinin
  parçası yapmak, grup alımı (group-buy) adı altında para toplamak,
- Atıf bilgisini (program penceresi, README, kaynak dosyalar) silmek veya değiştirmek,
- Ticari ürün veya hizmet içinde bu aracı kullanmak.

## English

This software is released **free of charge** for **non-commercial** use only (personal research,
hobby, retrofitting your own vehicle, Right-to-Repair).

Allowed: use on your own vehicle/workshop, study/fork/modify and share under the same terms, share in
free community spaces with attribution preserved.

Prohibited: selling the software, bundling it into paid packages, using it as part of a paid
"activation"/"coding" service, paid group-buys, removing the attribution, or using it inside a
commercial product/service.

## Kaynak / Upstream

Bu proje iki katmandan oluşur:

1. **Arayüz (bu depo):** Denizli Garaj tarafından yazılmıştır (Tkinter, tek dosya).
2. **Yama motoru (gömülü, `motor/conti_cp_tool.py`):** **mqb_contitool — PerkTheFox**
   · https://github.com/perkthefox/mqb_contitool · https://vwhacking.antonperk.com
   Motorun kendisi PerkTheFox'a aittir; onun şartları geçerlidir: ücretsiz, **satılamaz**,
   atıf korunmalıdır (vwhacking.antonperk.com · Drive2: perkthefox · Telegram: @perkthefox).

## Sorumluluk / Liability

Yazılım **"OLDUĞU GİBİ" (AS IS)** sunulur; hiçbir garanti verilmez. Gateway firmware'ini, CP/KSHUTZ
kayıtlarını veya bootloader kodunu değiştirmek ECU'yu **brick** edebilir, güvenlik anahtarlarını
bozabilir veya araçta bileşen koruması hatalarına yol açabilir. Tüm risk kullanıcıya aittir; yazar
hiçbir zarardan sorumlu değildir. Yazmadan önce her zaman tam yedek alın.
