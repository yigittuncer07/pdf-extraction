# ÖDEV
Finansal Tablo ve Dipnot İlişkilendirme

## Amaç
Bir KAP finansal raporundaki özet finansal tabloların yapılandırılmış olarak çıkarılması ve
bu tablolardaki kalemlerin ilgili dipnot tablolarıyla satır seviyesinde ilişkilendirilmesi
beklenmektedir.

Kaynak doküman:
https://kap.org.tr/tr/api/file/download/33E83438337C023CE0530A4A622B5826

## Kapsam
Dokümanın 5, 6 ve 7. sayfalarındaki özet finansal tabloları tespit edin ve şu bilgileri çıkarın:
tablo başlığı, satır ve sütun başlıkları, dipnot referansları, dönem bilgileri, sayısal değerler
ve kalemler arasındaki ana kalem / alt kalem / toplam ilişkisi.

Sayısal değerlerin ayrıştırılmasında parantez içindeki değerler negatif kabul edilir, nokta
binlik ayırıcıdır. Tire, boş hücre ve sıfır birbirinden ayrı durumlardır.

Ardından özet tablolarda 11 numaralı dipnota referans veren kalemleri belirleyin, bu
dipnotun bulunduğu sayfayı doküman içinde otomatik olarak tespit edin, dipnot altındaki
tabloları okuyun ve özet tablo kalemleriyle dipnot tablosundaki satırlar arasında ilişki
kurun.

Birden fazla özet tablodaki kalem aynı dipnota bağlanabilir. Örneğin bilançodaki bir kalem
ile kapsamlı gelir tablosundaki bir kalem aynı dipnotla ilişkili olabilir.
Hedef sayfa aralığı ve dipnot numarası konfigürasyondan gelmelidir; çözüm tek bir sayfa
veya tek bir dipnot için hard-code edilmemelidir.

## Yöntem
İlişkilendirme aşamasında bir NLP veya makine öğrenmesi bileşeni inference amacıyla
kullanılmalıdır. Model eğitimi beklenmemektedir; hazır bir dil modeli, embedding modeli,
cross-encoder veya reranker kullanılabilir. Hibrit bir yaklaşım da tercih edilebilir.

Birebir metin eşleşmesi tek başına yeterli değildir. Özet tablodaki bir kalem ile dipnot
tablosundaki satırların ifade biçimi büyük ölçüde farklıdır.

Tüm dokümanın tek bir model çağrısıyla doğrudan JSON'a dönüştürülmesi kabul
edilmeyecektir. Çözümün sayfa tespiti, tablo çıkarımı, normalizasyon, aday üretimi,
ilişkilendirme ve doğrulama gibi ayrı aşamalara bölünmesi beklenmektedir.

README'de model kullanılan her aşama için şunlar açıklanmalıdır: modelin hangi görev
için ve neden seçildiği, model girdisinin nasıl oluşturulduğu, inference sırasında hangi 
bağlamın verildiği, uzun doküman ve büyük tabloların nasıl parçalandığı, aday eşleşmelerin
nasıl üretilip sıralandığı, karar eşiğinin nasıl belirlendiği ve model başarısız olduğunda
devreye giren fallback.

## Confidence
Tablo, satır, hücre ve ilişki seviyesinde 0 ile 1 arasında bir confidence üretilmelidir. Sabit
veya rastgele değer kabul edilmez.
Modelin ürettiği similarity veya probability değerinin tek başına nihai confidence olarak
kullanılması yeterli görülmeyecektir.
Dokümandan çıkarılan sınırlı sayıda kontrol örneği eşik belirleme veya ağırlıklandırma için
kullanılabilir.

## Doğrulama
Çözüm, kendi çıktısını kontrol eden bir doğrulama aşaması içermelidir. Bu aşamada en az
şu üç grup kontrol bulunmalıdır:
- Yapısal: Tabloların doğru sayfayla eşleştirilmesi, dönem sütunlarının karıştırılmaması,
dipnot referanslarının doğru satıra bağlanması.
- Format: Sayısal ayrıştırma kuralları, dönem ve para birimi bilgisinin korunması.
- Finansal: Tablo içi ve tablolar arası tutarlılık, özet tablo değerleriyle dipnot tablosu
değerlerinin karşılaştırılması.

Düşük güvenli kayıtlar çıktıda işaretlenmelidir.

## Çıktı
Sonuçlar JSON veya JSONL olarak üretilmelidir. Veri modelini aday tasarlar; tercihin
gerekçesi README'de açıklanmalıdır.
Şema doküman bilgilerini (şirket, dönem, para birimi), özet tablo kalemlerini ve değerlerini,
dipnot tablolarının satırlarını, kurulan ilişkileri, confidence değerlerini ve doğrulama
sonuçlarını kapsamalıdır.

Karşılaştırma ve Hata Analizi
En az iki farklı ilişkilendirme yaklaşımı uygulanmalı ve karşılaştırılmalıdır. Karşılaştırmada
yalnızca nihai başarı değil, yöntemlerin hangi örneklerde ayrıştığı da ele alınmalıdır.

En az üç düşük güvenli veya hatalı örnek açıklanmalıdır. Her örnek için beklenen sonuç,
üretilen sonuç, hatanın oluştuğu aşama, olası neden ve iyileştirme önerisi yeterlidir.

## Teslimatlar
- Kaynak kod
- Üretilen JSON veya JSONL çıktısı
- README: kurulum ve çalıştırma adımları, yaklaşımın özeti, kullanılan modeller ve
inference ayarları, confidence yöntemi, doğrulama sonuçları, yöntem karşılaştırması ve
hata analizi
Python ve hazır PDF, OCR, tablo çıkarma veya doküman işleme kütüphaneleri serbestçe
kullanılabilir.

## Değerlendirme
Üretim seviyesinde eksiksiz bir çözüm beklenmemektedir. Öncelikli olarak problemin nasıl
aşamalara ayrıldığı, model ve kuralların birlikte nasıl kullanıldığı, sonuçların nasıl
doğrulandığı, belirsizliğin nasıl yönetildiği ve kodun tekrar çalıştırılabilirliği
değerlendirilecektir.
