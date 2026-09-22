# yapikredi-pdf-extraction

## Yaklaşım Özeti

7 aşamalı bir çözüm kullandım, her aşama belli bir formatta girdi ve çıktı alıyor ve ara aşamalar JSON şeklinde kaydediliyor (artifacts altında).

PDF -> **PDF EXTRACTION** -> **NORMALIZASYON** -> **TABLO CONFIDENCE HESABI** -> **SAYFA TESPITI** -> **ADAY ÜRETİMİ** -> **İLİŞKİLENDİRME** -> **DOĞRULAMA** -> Tüm bilgileri içeren JSON dosyası.

Deney kolaylığı ve geliştirebilirlik sağlamak için yaklaşım olabildiğince mödüler tasarlandı, her aşamanın girdisi ve çıktısı veri formatına uyduğu sürece geliştirilebilir ve değiştirilebilir. 

Aşamaların açıklamaları:
1. **PDF EXTRACTION**:
Öncelikle PDF ten tablolar, sayfa numaralı, başlıklar ve diğer gerekli bilgiler OCR ve VLM kullanılarak JSON formatında kaydedildi.
2. **NORMALIZASYON**:
Çıkarılan bilgiler normalizasyon aşamasına gönderildi, burada kalemler arası hiyerarşı ve değerlerin parselanması gibi normalizasyondan geçirildi.
3. **TABLO CONFIDENCE HESABI**:
Yapılan iki döküman extraction ile confidence değerleri hesaplandı, hem kıyaslama yaparak hem dokuman içi doğrulama ile.
4. **SAYFA TESPITI**:
İçindekiler tablosu ve REGEX kullanılarak hedef sayfalar tespit edildi (verilen notu içeren).
5. **ADAY ÜRETİMİ**:
Notu içeren tüm özet ve not satırları onceki sayfada belirlenen sayfaları kullanarak, bağlamı ile beraber hazırlandı.
6. **İLİŞKİLENDİRME**:
Kurallar, bi-encoder, cross-encoder ve önceden hesaplanmış confidence kullanılarak satırlar arası ilişkiler ve ilişkilerin güvenilebilirliği hesaplandı.
7. **DOĞRULAMA**:
Tüm tablolar yapısal, format ve finansal doğrulamadan geçti.

En sonunda ise tüm istenen bilgiler (doküman bilgileri, tablolar, alakalı bulunan satırlar) incelenmek üzere JSON formatında kaydedildi. 

## Kurulum ve Çalıştırma

Çalıştırmadan önce app/config.py içinde config ayarlanarak hangi özet tablolarının işlenmesi istendiği, hangi notun çıkarılması istendiği, ve girdi PDF'in ismi ayarlanabilir. Değiştirilmezse default olarak sayfa 5, 6, 7 ve not 11 alakaları kurulcaktır.

```bash
chmod +x run.sh
./run.sh
```
PDF extraction aşamasında kullanılan Docling ve DeepSeek-OCR-2 farklı iki environment gerektiği için bunu halleden bir run script yazdım.

### Artifact'lar

| dosya | aşama |
|---|---|
| `00_pages.json` | extraction, docling + EasyOCR (ikinci görüş) |
| `01_pages.json` | extraction, DeepSeek-OCR (birincil) |
| `02_tables.json` | normalizasyon |
| `03_confidence.json` | hücre / satır / tablo confidence |
| `04_candidates.json` | aday çiftleri + bağlam |
| `05_relations.json` | ilişkiler, her scorer için ayrı. |
| `05_linking_candidates-*.jsonl` | puanlanan tüm adaylar logu |
| `06_validation.json` | doğrulama bulguları |
| `07_final_table.json` | doğrulama bulguları eklenmiş tablolar, yani son hali |
| `08_output.json` | **Tüm gerekli bilgileri içeren son çıktı** |

---

## PDF Extraction 

Bu aşamada birkaç farklı yöntem denedim?

1. **Tesseract OCR ve Docling**: Çok fazla rakam hatası ve kelime kayması olduğu için kullanılamazdı
2. **Docling VLM ve Docling**: Çıktı kalitesi yine çok düşüktü
3. **Qwen2.5 VL**: Tablolarda kayıp çoktu, kullanılamaz düzeyde
4. **Easy OCR ve Docling**: Kaymalar ve hatalar olsa da kabül edilebilir kalitede
5. **DeepSeek OCR 2**: En iyi başarı, ancak tablo formatında sistematic olarak düzeltilebilir kaymalar oldu

Sonuç olarak DeepSeek ve Easy OCR ile devam ettim. DeepSeek en iyi başarı gösterdiği için ana kaynak olarak onu tercih ettim,
PDF içi pozisyonel değerler ve doğrulama için. ikinci bir çıktı olarak kullanmak içinse Docling tercih ettim (Easy OCR tabanı ile)

Not: Tesseract'ın kendi confidence'ı hatalarıyla korelasyon göstermiyordu. Doğru değerlere düşük, yanlış değerlere yüksek confidence verdiği oluyordu, 
bu yüzden OCR katmanının confidencını hesaplamaya katmadım.

---

## Kullanılan Modeller ve Inference Ayarları

Hiçbir model eğitilmedi, hepsi sadece inference. Tüm modeller local hardware üzerinde çalıştırıldı, API kullanımı yok.

* **Extraction (Çıkarma Aşaması)**
* **Girdi:** PDF sayfaları tek tek işlenir.
* **DeepSeek-OCR-2 (Birincil Model):** Tüm dipnot referanslarını, ve az çok tüm değerleri doğru okuduğu için tercih edildi.
* **docling + EasyOCR (İkinci Görüş):** Çapraz kontrol sağlamak ve tablolardaki değerlerin indentation sayısını çıkarabilmek için kullanıldı.

* **İlişkilendirme Aşaması**
* **Girdi:** Satırın bağlamla zenginleştirilmiş hali (varsa modelin promptuna gömülü şekilde) iletilir.
* **`intfloat/multilingual-e5-base` (Bi-encoder):**
* **Amaç:** Türkçe destekli bi-encoder performansını test etmek.
* **İşleyiş:** Satırları tek tek alarak ayrı dense embedding'ler üretir.

* **`BAAI/bge-reranker-v2-m3` (Cross-encoder):**
* **Amaç:** Türkçe destekli cross-encoder performansını test etmek.
* **İşleyiş:** Çifti doğrudan girdi olarak alıp -1 ile 1 arasında tek bir alaka skoru üretir.

**Inference sırasında verilen bağlam.**  
Her satır bağlamıyla zenginleştiriliyor:   
Tablo başlığı, etiket kolonunun başlığı, alt kalemler için ana kalem, dipnot referansı ve boş olmayan tüm değerler kolon
başlıklarıyla.

Deney olarak bağlamı zenginleştirmeden, yalnızca kalem etiketi ve varsa ana kaleminin değerini de girdi olarak vermeyi denedim. 
Kod'da bu candidate mödülüne bağlam zenginliğini ayarlayan bir arguman ile ayarlanabiliyor. 

```
11. YATIRIM AMAÇLI GAYRİMENKULLER|
kalem: 31 Aralık 2012 itibari ile kapanış bakiyesi |
Arazi ve Arsalar: 177.730.044 | Binalar: 196.262.178 | Toplam: 373.992.222
```

İki etiketin ne kadar az şey paylaştığına dikkat: `Yatırım Amaçlı
Gayrimenkuller` ve `31 Aralık 2012 itibari ile kapanış bakiyesi` hiçbir ortak
anlamlı kelime içermiyor. Görevin "birebir metin eşleşmesi yetersizdir"
dediği nokta bu — ve aşağıda göreceğin gibi bi-encoder'ın da burada
zorlanmasının sebebi.

**Uzun doküman ve büyük tabloların parçalanması.** **Parça birimi satır.**
İlişki satır seviyesinde olduğu için doğal birim satır + bağlamı, yaklaşık 50
token. Hiçbir şey bölünmüyor çünkü hiçbir şey uzun değil. Doküman extraction'da
sayfa başına parçalanıyor (95 çağrı), aday üretiminde ise dipnot başına: sadece
tespit edilen sayfalar hedef oluyor, doküman tamamı asla. Daha büyük bir dipnot
için (29 numaralı dipnot 10 sayfa) aday sayısı artıyor ama her metin kısa
kalıyor; mekanizma cross-encoder öncesi bi-encoder ile top-K ön filtre, iki
`Scorer` implementasyonu bunu zaten destekliyor. 11 numaralı dipnotun 18 hedefi
için gerekmedi.

**Adayların üretilmesi ve sıralanması.** Üretim tamamen kural tabanlı ve
exhaustive: kaynak satırlar (dipnota referans veren) × hedef satırlar (dipnot
sayfalarındaki tüm satırlar) = 36 çift. Aday kümesi her scorer için aynı —
bilinçli bir seçim: iki yöntem farklı adaylar görseydi karşılaştırma iki farklı
problemin karşılaştırması olurdu. Sıralama füzyon puanıyla:

```
confidence = 0.55·model + 0.35·rules + 0.10·upstream
```

Model önde ama tek başına karar vermiyor — görevin "similarity tek başına
nihai confidence olamaz" şartı bu şekilde karşılanıyor.

**Karar eşiğinin belirlenmesi.** Tahminle değil, puan dağılımından. Her adayın
füzyon puanı `05_linking_candidates-*.jsonl` dosyasına loglanıyor. İki scorer
da tek bir geniş boşluk gösteriyor:

| scorer | son kabul | ilk red | boşluk | eşik |
|---|---|---|---|---|
| bi-encoder | 0.851 | 0.659 | **0.192** | 0.80 |
| cross-encoder | 0.671 | 0.465 | **0.206** | 0.55 |

Sıralamanın geri kalanında aralıklar 0.001–0.005. Boşluk tam olarak `rules`
puanının 0.675'ten 0.125'e düştüğü yere denk geliyor — yani değer eşleşmesinin
bittiği yere. Eşik boşluğun içine konuldu.

Eşiklerin farklı olmasının sebebi modellerin puanlarının farklı bantlarda
olması (bi-encoder 0.92–0.94, cross-encoder 0.53–0.65). 0.55 ağırlıkla bu
yaklaşık 0.21'lik sabit bir offset farkı demek, iki eşik arasındaki 0.25'in
neredeyse tamamı. Karar sınırı aynı, sadece offset kayıyor. Eşikler bu yüzden
scorer başına.

**Model başarısız olduğunda fallback.** `RuleScorer` fallback, ve gerçek bir
scorer — karşılaştırılan yöntemlerden biri. Üç senaryo:

1. **Model yüklenemiyor** (GPU yok, indirme başarısız, OOM). Pipeline
   exception'ı yakalıyor ve sadece kurallarla bağlıyor. `link()` seçilen
   scorer'ın kural scorer'ı olduğunu görüp ikinci çağrıyı atlıyor. Çıktıda
   `method: "rules"` yazıyor.
2. **Hiçbir aday eşiği geçmiyor.** Kaynak `status: "unlinked"` olarak, en iyi
   adayı ve puanıyla yazılıyor. Dipnota referans verip hiçbir şey üretmeyen bir
   satır bilgidir; sessizlik değildir.
3. **Hiç hedef yok** (hatalı sayfa tespiti). Aynı `unlinked` kaydı, puan 0.

Sadece kurallarla çalıştırıldığında her iki kaynak da doğru bağlanıyor —
fallback sonucu değil, sıralamayı bozuyor.

---

## Confidence Yöntemi

Dört seviye, hiçbiri sabit, hiçbiri tek başına model puanı.

**Hücre.**

```
hücre = 0.4·parse + 0.6·agreement
```

- `parse` — hücre sayı / tire / boşluk olarak çözüldü mü (1.0 veya 0.0)
- `agreement` — ikinci extractor aynı satır için ne okumuş:

| | |
|---|---|
| 1.0 | aynı metin |
| 0.6 | aynı rakamlar, farklı ayırıcı — birisi yanlış |
| 0.3 | farklı rakamlar |
| 0.5 | diğer extractor bu satırı hiç görmemiş: görüş yok, ceza yok |

Satırlar extractor'lar arası **token kümesiyle** eşleştiriliyor, metinle değil,
çünkü docling hücre içinde kelime sırasını bozuyor: `Gelirleri Satış` =
`Satış Gelirleri`. Etiketler tekrar ediyor (`Finansal Borçlar` hem kısa hem
uzun vadeli altında), bu yüzden bir anahtar aynı etiketi paylaşan tüm satırlara
gidiyor ve herhangi biriyle eşleşen değer agreement sayılıyor — çakışma ceza
üretmemeli.

İki extractor çalıştırmak başta birincil olanı *seçmek* içindi. İkincisini
tutmak her hücreye hiçbir modelin tek başına üretemeyeceği bir çapraz kontrol
kazandırıyor ve gerçek hataları yakalıyor: düşen dipnot referansı, kaybolan
504.851, `7.987,391` karşısında `7.987.391`.

**Satır.** Hücrelerinin ortalaması.

**Tablo.**

```
tablo = 0.8·rows + 0.2·columns
```

`columns`, bu tablonun kolon isimlerinin diğer extractor'ın aynı tablo için
okuduğu isimlerle token örtüşmesi — pozisyon pozisyon karşılaştırılıp ikisinin
genişi olanına bölünüyor, böylece farklı kolon sayısı ayrı bir kontrol
gerektirmeden puan kaybettiriyor.

Satırlar 4:1 ağırlıklı çünkü satır puanı tablodaki her hücreyi topluyor, kolon
isimleri ise birkaç string; eşit ağırlık tek bozuk bir ismin temiz bir tabloyu
iptal etmesine izin verirdi.

**İlişki.** Yukarıdaki füzyon. Her seviye parçalarını toplamla birlikte
saklıyor:

```json
"confidence": 0.915,
"confidence_parts": {"model": 0.941, "rules": 0.85, "upstream": 1.0}
```

**Kural özellikleri.**

| özellik | ağırlık | tanım |
|---|---|---|
| `value` | 0.6 | herhangi bir kaynak değeri herhangi bir hedef değerine eşitse 1.0 |
| `period` | 0.25 | eşleşen çift aynı yılı paylaşıyorsa 1.0, paylaşmıyorsa 0.3, değer eşleşmesi yoksa 0.5 |
| `label` | 0.15 | iki etiket arasında token Jaccard |

Bir değerin dönemi kolonunun yılı, ya da kolonun yılı yoksa satırın kendi
etiketindeki yıl. 11 numaralı dipnotun hareket tabloları varlık sınıfına göre
bölünüyor (`Arazi ve Arsalar` / `Binalar` / `Toplam`), kolonlarda yıl yok; yıl
`31 Aralık 2012 itibari ile kapanış bakiyesi` içinde. Bu fallback olmadan
`period` özelliği tam da en önemli tablolarda ölü kalıyor.

---

## Ana Kalem / Alt Kalem / Toplam İlişkisi

Üç kaynaktan geliyor:

| tier | sinyal |
|---|---|
| alt kalem | etiketin `-` öneki, metnin içinde açıkça var |
| ana kalem | **girinti** — docling'in hücre bbox'undan `l` değeri |
| toplam | büyük harfli etiket |

Girinti kısmı geç eklendi ve önemliydi. Bilançoda hiyerarşi tipografiyle ifade
ediliyor: `Dönen Varlıklar` sola dayalı, `Nakit ve Nakit Benzerleri` girintili,
`-İlişkili Taraflardan` daha girintili. DeepSeek'in markdown çıktısı bunu
tamamen atıyor (`grep -c '<|det|>'` → 0, `<td>` içinde baştaki boşluk yok),
ama docling her hücre için bbox tutuyor:

```
72.7  VARLIKLAR, Dönen Varlıklar, Duran Varlıklar   level 0
80.0  Nakit ve Nakit Benzerleri, Ticari Alacaklar   level 1
```

x değerleri seviye başına birbirinin aynısı, seviyeler arası fark 7.3pt, yani
4.0 toleransla rahat kümelenebiliyor. Satır eşleşmesi indeks üzerinden ama
etiket metniyle doğrulanıyor — indekse körü körüne güvenmek bir satır kayması
durumunda *yanlış* hiyerarşi üretir, hiç üretmemekten kötüdür.

**Gelir tablosunda bu özellik kapatıldı.** Gelir tablosu bir toplam ağacı
değil, akan bir sonuç: `FAALİYET KARI` yukarıdaki her şeyin toplamı değil,
önceki toplamın artı/eksi arada kalan satırlarla güncellenmiş hali. Girinti
orada bir roll-up ifade etmiyor, o yüzden `kind != "income_statement"` ile
geçiliyor.

Bunun değerli yanı: hiyerarşi **sayfanın düzeninden** okunuyor, sayılardan
çıkarılmıyor. Doğrulama aşaması toplamları bu hiyerarşiye karşı kontrol
ettiğinde iki bağımsız kanıt karşılaştırılıyor oluyor.

> **Not (isteğe bağlı, tuttuysan yaz):** Hiyerarşiyi aritmetik olarak çıkarmayı
> da denedim — yukarıdaki bir değere toplanan satır dizileri bulmak. Kaldırdım,
> çünkü döngüsel: aynı toplamlar doğrulama aşamasının bağımsız olarak kontrol
> etmesi gereken şey. Keşif ve doğrulama aynı kanıta dayanamaz.

---

## Doğrulama

Üç grupta beş kontrol. Doğrulama bilinçli olarak confidence'tan ayrı:
confidence pipeline'ın ne kadar emin olduğunu söylüyor, doğrulama çıktının
dokümanın kendisi hakkında iddia ettiği şeyle tutarlı olup olmadığını soruyor.
İki extractor yanlış bir sayıda anlaşabilir ve iki hücre de yüksek puan alır;
bunu sadece aritmetik yakalar.

| grup | kontrol | ne zaman tetiklenir |
|---|---|---|
| yapısal | `NOTE_PAGE_UNVERIFIED` | içindekiler ve dipnot başlığı farklı sayfa söylüyor |
| format | `VALUE_UNPARSED` | değer hücresi sayı/tire/boşluk olarak çözülmedi |
| format | `CURRENCY_MISSING` | sayfada para birimi yok |
| format | `PERIOD_LOST` | kolon başlığı yıl içeriyor ama dönem parse edilemedi |
| finansal | `SUBITEM_MISMATCH` | alt kalemler ana kaleme toplanmıyor |
| finansal | `VALUE_NOT_IN_NOTE` | dipnota referans veren özet değer dipnotta bulunmuyor |

`PERIOD_LOST` varlığı değil korunmayı kontrol ediyor: her tablonun dönemi
olmak zorunda değil (11 numaralı dipnotun tabloları varlık sınıfına göre
bölünüyor), kontrol edilen şey dokümanda yazan bir yılın hayatta kalıp
kalmadığı.

`SUBITEM_MISMATCH` ana kalemin **o kolondaki hücresine** işaretleniyor, satırın
tamamına değil — kontrol kolon bazında ve hata uzlaşmayan değere ait.

**Düşük güvenli kayıtlar çıktıda işaretli.** Her tablo, satır, hücre ve ilişki
bir `flags` listesi taşıyor: geçemediği kontrollerin kodları, artı 0.6 altında
puan aldıysa `LOW_CONFIDENCE`. Flag'ler kontrollerden ve puanlardan türetiliyor,
elle konmuyor.

---

## Yöntem Karşılaştırması

Üç yöntem, **aynı** aday kümesi (36 çift). Her biri aynı beş ilişkiyi buluyor;
sıralamada ayrışıyorlar.

### Bulunan ilişkiler

| kaynak | hedef | rules | bi-enc | cross-enc |
|---|---|---|---|---|
| Yatırım Amaçlı Gayrimenkuller | 31 Aralık 2012 kapanış bakiyesi | 0.85 | 0.915 | 0.718 |
| Yatırım Amaçlı Gayrimenkuller | 31 Aralık 2011 kapanış bakiyesi | 0.85 | 0.913 | 0.741 |
| Yatırım Amaçlı Gayrimenkuller | 1 Ocak 2012 açılış bakiyesi | 0.675 | 0.851 | 0.671 |
| …Değerleme Farkları | Makul değer…kazanç (2012) | 0.675 | 0.831 | 0.626 |
| …Değerleme Farkları | Makul değer…kazanç (2011) | 0.675 | 0.816 | 0.662 |

Beşi de savunulabilir. Bilanço satırı iki yılı da taşıyor, dolayısıyla her iki
kapanış bakiyesi de gerçek bir ilişki; 2012'nin açılış bakiyesi de 2011'in
kapanış bakiyesine eşit, yani 2011 kolonunun raporladığı aynı rakam.

### Nerede ayrışıyorlar

> **Aşağıdakilerden kullanacaklarını seç.** Hepsi doğru, hepsini yazmak gerekmez.

**(A) Bi-encoder neredeyse hiç ayrıştırmıyor.** Bilanço kaynağı için 18 adayın
tamamında puanlar **0.930 – 0.949** arasında — 0.019'luk bir aralık, kural
puanının 0.725'lik aralığına karşı. Nihai sıralamayı neredeyse tamamen kurallar
belirliyor, model sabite yakın bir offset katıyor.

Mekanizma bağlam render'ında: bir dipnotun altındaki her hedef aynı başlığı,
sayfayı ve kolon isimlerini paylaşıyor, ayrıştırıcı kısım satır etiketi, yani
token'ların belki %20'si. Bi-encoder iki tarafı bağımsız gömüyor, paylaşılan
boilerplate vektöre hakim oluyor ve farklar ortalamada kayboluyor. **Sinyal
farkta, bi-encoder ise tam olarak farkı ortalayan mimari.**

**(B) Min-max normalizasyon denendi ve kaldırıldı.** Cosine'leri aday kümesi
içinde yaymak modelin sıralamasını güçlendiriyor — gelir tablosu kaynağında bu
sıralama yanlış olduğu için zayıf bir aday kümesini mükemmel puana çıkardı.

**(C) Cross-encoder ayrıştırıyor ama yanlış eksende sıralıyor.** Aynı adaylarda
puan aralığı 0.088 — bi-encoder'ın sekiz katı, yani çifti gerçekten okuyor. Ama
**her iki kaynakta da** 2011 satırını 2012 ikizinin üstüne koyuyor. İki etiket
tek bir token'da farklı (`31 Aralık 2011` / `31 Aralık 2012`) ve o token bir
sayı. Transformer'lar sayısal token'ları ağır şekilde sıkıştırıyor. Bu satırları
ayıran tek şey, semantik benzerliğin en kötü olduğu şey.

**(D) Sadece kurallar iki kaynağı da doğru bağlıyor.** Bu görevde değer kanıtı
sinyali taşıyor — `373.992.222` dipnotta tek bir satırda geçiyor. Modelin işi
kuralların belirlediği kabul edilebilir küme *içinde* sıralama yapmak. Bu
genel beklentinin tersi ve füzyonun modele tam değer eşleşmesini ezdirmemesinin
sebebi.

**(E) Kurallar modelin çözemediği bir eşitliği kırıyor.** Gelir tablosu
kaynağında iki makul değer satırının kural puanları birebir aynı (0.675),
cross-encoder puanları 0.001 içinde. Ayıran şey `upstream` — 0.86'ya karşı 0.70
— çünkü docling 2011 satırının etiketini fazla heceyle `kaynaklananan` okumuş.
**Extraction aşamasındaki bir çapraz kontrol semantik bir eşitliği çözdü.**

**(F) Üç yöntemin katkısı farklı yerlerde.** Kurallar hangi adayların kabul
edilebilir olduğunu belirliyor, bi-encoder hiçbir şey eklemiyor, cross-encoder
gerçek bir sıralama üretiyor ama dönem körü. Hibrit yaklaşımın gerekçesi bu
dağılım.

---

## Hata Analizi

> **Görev en az 3 örnek istiyor. Aşağıda 6 tane var, 3 tanesini seç.**

### (1) Bir virgül değeri başka bir sayıya çeviriyor, ilişki kayboluyor

- **Beklenen:** `Yatırım Amaçlı Gayrimenkuller` (373.992.222) →
  `31 Aralık 2012 itibari ile net defter değeri` (aynı rakam).
- **Üretilen:** İlişki yok. Satır sıralamanın hiçbir yerinde görünmüyor, kural
  puanı 0.125 (değer eşleşmesi yok tabanı).
- **Aşama:** Extraction, normalizasyonda yüzeye çıkıyor.
- **Neden:** DeepSeek hücreyi `373,992.222` okudu. Virgül noktadan *önce*
  geliyor, bu iki konvansiyonun hiçbirinde geçerli değil.
- **İyileştirme önerisi:** Parser'ı sıkılaştırdım — ayırıcı düzeni iki
  konvansiyondan birine uymuyorsa değer `text` kalıyor ve `VALUE_UNPARSED`
  tetikleniyor. Artık üç aşamada yakalanıyor: format doğrulaması, hücre
  confidence'ı (0.18, flag eşiğinin altında), ve eksik ilişki. Sıkılaştırma
  öncesi hücre 0.92 alıyordu ve hiçbir şey flag koymuyordu — hata analizinin
  en zayıf noktası buydu.

### (2) Bi-encoder adayları birbirinden ayırt edemiyor

- **Beklenen:** Semantik bir modelin `kapanış bakiyesi` ile
  `İskonto oranı (%)` arasını ayırması.
- **Üretilen:** 18 adayda 0.930 – 0.949, yani 0.019 yayılım. Model her çifte
  sabite yakın bir sayı katıyor.
- **Aşama:** İlişkilendirme.
- **Neden:** Bağlam render'ı + bi-encoder mimarisi. Her hedef dipnot başlığını,
  sayfayı ve kolon isimlerini paylaşıyor; bağımsız gömme paylaşılan metni baskın
  hale getiriyor.
- **İyileştirme önerisi:** Hedefleri paylaşılan boilerplate'ten arındırarak
  render etmek; ya da bi-encoder'ı sadece top-K ön filtre olarak kullanıp
  sıralamayı cross-encoder'a bırakmak — mimari buna hazır.

### (3) Cross-encoder döneme kör

- **Beklenen:** Satırların anlamına göre bir sıralama.
- **Üretilen:** Her iki kaynakta da 2011 satırı 2012 ikizinin üstünde.
- **Aşama:** İlişkilendirme.
- **Neden:** `31 Aralık 2011 …` ve `31 Aralık 2012 …` tek token farklı ve o
  token bir sayı. Transformer'lar sayısal token'ları sıkıştırıyor.
- **İyileştirme önerisi:** Dönem bilgisini modelden hiç beklememek. Kural
  katmanı yılı kolon başlığından ya da satır etiketinden çıkarıyor; çözüm
  `period` ağırlığını artırmak, ya da kaynağın dönemine uyan adayları önce
  sıralayıp model sıralamasını grup içinde bırakmak.

### (4) docling görevin bağlı olduğu referansı düşürüyor

- **Beklenen:** `Yatırım Amaçlı Gayrimenkul Değerleme Farkları` dipnot
  referansı 11 taşıyor.
- **Üretilen:** docling + EasyOCR çıkarımında boş referans hücresi.
- **Aşama:** Extraction.
- **Neden:** Referans kolonu dar ve etiketle sayılar arasında sıkışıyor;
  docling'in tablo modeli onu birleştirdi ya da düşürdü.
- **Sonucu:** Bu extractor'la gelir tablosu kaynağı aday üretimine hiç
  girmiyor ve görevin tanımladığı çapraz-tablo durumu gösterilemiyor. Birincil
  extractor seçimini bu tek hücre belirledi.
- **İyileştirme önerisi:** Düzeltme bu aşamada değil — docling okuması ikinci
  görüş olarak tutuluyor ve anlaşmazlıklar hücre confidence'ında görünüyor.

### (5) Tesseract'ın confidence'ı hatalarıyla korelasyonsuz

- **Beklenen:** OCR'ın kendi güven puanının hatalı hücrelerde düşük olması.
- **Üretilen:** En kötü hata (`71.543.097` ← `77.543.097`) 0.94 confidence;
  doğru bir değer (`35.481`) 0.19.
- **Aşama:** Extraction.
- **Neden:** Tesseract'ın confidence'ı karakter sınıflandırma olasılığından
  geliyor, rakamın bağlamdaki makullüğünden değil. Bilevel 200 DPI'da `7`'nin
  diyagonali kopunca model `1`'den emin oluyor.
- **İyileştirme önerisi:** OCR confidence'ını hiç kullanmamak — projede
  kullanılmıyor. Yerine iki bağımsız extractor'ın anlaşması + aritmetik
  tutarlılık. Korelasyonlu hatalar hâlâ açık bir nokta: iki extractor aynı
  yanlış rakamda anlaşırsa sadece toplam kontrolü yakalar.

### (6) Tek ilişki varsayımı yanlıştı

- **Beklenen (ilk tasarım):** Her özet satırı için tek bir "doğru" dipnot
  satırı.
- **Üretilen:** Üçlü eşitlik — `kapanış bakiyesi`, `net defter değeri` ve 2011
  kapanış bakiyesi aynı puanı aldı, sıralama sıra numarasıyla belirlendi.
- **Aşama:** İlişkilendirme (tasarım hatası, kod hatası değil).
- **Neden:** Bilanço satırı dönem-agnostik ve iki yılı da taşıyor; birden fazla
  dipnot satırıyla gerçek ilişkisi var. "THE doğru satır" varsayımı görevin
  yapısına uymuyordu.
- **İyileştirme önerisi:** Eşiği geçen her adayı ilişki olarak yazmak — kod bu
  şekilde güncellendi. Bir sonraki adım ilişkileri tiplemek
  (`equals_closing_balance`, `equals_carrying_amount`), çünkü tipsiz haliyle üç
  ilişki çıktıda birbirinin aynısı görünüyor.

---

## Çıktı Şeması

`07_output.json`:

```json
{
  "document":     { "company": "…", "periods": [2012, 2011], "currency": "Türk Lirası (TL)" },
  "config":       { "pages": [5, 6, 7], "note": 11 },
  "note":         { "note": 11, "pages": [53, 54], "verified": true, "offset": 4 },
  "tables":       [ { "id": "p005.t0", "title": "…", "confidence": …, "flags": [] } ],
  "summary_rows": [ … ],
  "note_rows":    [ … ],
  "relations":    [ … ],
  "validation":   { "issues": [ … ], "counts": { … } }
}
```

Üç tasarım kararı:

- **Satırlar tablolara gömülü değil, düz liste.** İlişki bir satır id'sine
  işaret ediyor; düz liste bunu tek bir lookup yapıyor. Satırın ihtiyaç duyduğu
  tablo bağlamı (`table_id`, `table_title`, `page`) satırın üstünde taşınıyor.
- **Dipnotun tüm satırları çıktıda, sadece bağlananlar değil.** Onlar aday
  kümesi. Okuyucu neyin reddedildiğini neyin kabul edildiğinin yanında
  görebiliyor — eşik böylece tek başına çıktıdan denetlenebilir hale geliyor.
- **Değerler kolon id'siyle anahtarlanmış map değil, kolon başlığını ve dönemi
  taşıyan liste.** `c2` pipeline dışında bir şey ifade etmiyor.

Satır id'leri `p{pdf sayfa}.t{tablo}.r{satır}` — her zaman var olan PDF sayfa
indeksi üzerine kurulu, basılı sayfa numarası attribute olarak tutuluyor.

---

## Bilinen Eksikler

- **Gelir tablosu aritmetik olarak doğrulanmıyor.** Toplam ağacı değil, akan
  sonuç; kontrolü operatör semantiği gerektiriyor (`(-)` etiketi, değerin
  işareti). Cascade kontrolü tasarlandı, yazılmadı.
- **Yatay tablolar hiçbir extractor'da doğru çıkmıyor.** 12 numaralı dipnot
  dikey sayfaya yatay basılmış. 11 numaralı dipnotu etkilemiyor ama diğer
  dipnotlara genellemeyi etkiliyor.
- **Birleşik başlık hücreleri span yok sayma düzeltmesiyle bozuluyor.**
  `colspan`'i yok saymak DeepSeek çıktısını kullanılabilir yapan şey; bedeli
  gerçekten birleşik bir başlığın span'ini kaybetmesi. Bu dokümanda uydurma
  span'ler gerçek olanlardan çok daha yaygın, kabul edilen bir takas.
- **İlişkiler tipsiz.** Hepsi `relates_to`. Kaynak başına birden fazla ilişki
  olunca `kapanış bakiyesi`, `net defter değeri` ve 2011 kapanış bakiyesine
  giden üç ilişki çıktıda ayırt edilemiyor.
- **Kontrol kümesi iki kaynaktan oluşuyor.** Eşikler gözlenen bir dağılım
  boşluğuna konuldu, etiketli veriye fit edilmedi; yöntem karşılaştırması iki
  örneğe dayanıyor. Zaman olsa ilk yapacağım şey pipeline'ı 8 ve 12 numaralı
  dipnotlarla ve ikinci bir KAP dosyasıyla çalıştırmak olurdu.





















































-----

TODO: 
- [x] Write readme detailing findings
- [x] Try to get this out of the table using indentation from DeepSeek: ana kalem / alt kalem / toplam ilişkisi.

## PERSONAL NOTES:

- Using tesseract OCR on the PDF resulted in lots of OCR errors. EasyOCR also failed to properly extract the data. Value errors, missing footnotes...
- SmallDocling failed as a VLM. The output quality is awful.
- Qwen 2.5 VL produced awful results. Only DeepSeek OCR 2 produced acceptable results, the numbers look very clean, only some table headers are misaligned, which can be post processed. I am also out of options, so DeepSeek it is.
- Deepseek works well with post patches, but this will break some functionality, for example merged header tables get broken, but this is a tradeoff I am accepting at this stage. 

- Kept OCR from docling, as a second opinion, deepseek is considered more valuable, since it seems to work better. 
- NOTE: Sideways tables are not rendered correctly. Need global fix for all renderers for this to work.
- NOTE: MERGED HEADERS BREAK IN DEEPSEEK. Need to update postfix somehow, simplify.

A bi-encoder over row contexts produced almost no discrimination (0.019 spread over 18 candidates), because the context that makes a row interpretable is largely shared between candidates from the same note. The signal is in what differs, which is exactly what a bi-encoder averages away. Rules supplied the discrimination; the model contributed ordering that was correct for one source and wrong for the other.

Initially, I was thinking about this as finding THE relavent row, but its obvious that multiple relevant rows can exist. So I'm updating the code to accept everything above a certain threshold

after doing so I see that one OCR error, replacing . with , resulted in a relation being lost. The row and cell has low confidence in the table section, and the rule matching misses it. This is a good example of a failure. It came out at the table extraction stage. The upstream is still high because it is only tagged as a point differ, not a full miss.

The bi encoder just classified everything as the same, the rule saved it. The cross encoder produced meaningful resulst on its own, validated by the rule check.

validator checks sums, format, structure. 



**The general pipeline idea is:**
1. PDF ingestion, the goal here is to turn the PDF as is into a usable format.
2. Normalization, as described in the task description.
3. Candidate generation, this is hardcoded, no ML involved, just return the full list of rows that can be relevant to a certain summary row, using note links.
4. Scoring, here we use ML to decide which table rows are actually relevant to the summary rows, and extract relations, we will have a single relation which is relates_to (which is forced unless we use something other than embeddings, rerankers, cross encoders, etc...). Use 2 separate approaches here to see what works best and to compare. 
5. Validation, we must run structural, financial and format validations at the end. We must construct confidence for tables, relations, etc, using the validation steps and the model similarity output jointly.