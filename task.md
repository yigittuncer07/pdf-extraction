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


---


# ASSIGNMENT
Linking Financial Statements to Footnotes

## Objective
You are expected to extract, in structured form, the summary financial statements from a KAP financial report, and to link the line items in those statements to the related footnote tables at the row level.

Source document:
https://kap.org.tr/tr/api/file/download/33E83438337C023CE0530A4A622B5826

## Scope
Identify the summary financial statements on pages 5, 6 and 7 of the document and extract the following information: table title, row and column headers, footnote references, period information, numeric values, and the main item / sub-item / total relationships between line items.

When parsing numeric values, figures in parentheses are treated as negative, and the period is the thousands separator. A dash, an empty cell, and a zero are three distinct cases.

Next, identify the line items in the summary statements that reference footnote number 11, automatically locate the page on which that footnote appears within the document, read the tables under the footnote, and establish relationships between the summary statement line items and the rows in the footnote table.

Line items from more than one summary statement may link to the same footnote. For example, an item in the balance sheet and an item in the statement of comprehensive income may relate to the same footnote.

The target page range and the footnote number must come from configuration; the solution must not be hard-coded for a single page or a single footnote.

## Method
An NLP or machine learning component must be used for inference during the linking stage. Model training is not expected; an off-the-shelf language model, embedding model, cross-encoder or reranker may be used. A hybrid approach is also acceptable.

Exact text matching alone is not sufficient. The wording of a line item in the summary statement and the wording of the rows in the footnote table differ substantially.

Converting the entire document to JSON directly with a single model call will not be accepted. The solution is expected to be divided into separate stages such as page detection, table extraction, normalization, candidate generation, linking, and validation.

For every stage where a model is used, the README must explain the following: which task the model was chosen for and why, how the model input is constructed, what context is provided during inference, how long documents and large tables are chunked, how candidate matches are generated and ranked, how the decision threshold is determined, and the fallback that takes over when the model fails.

## Confidence
A confidence value between 0 and 1 must be produced at the table, row, cell and relationship level. Fixed or random values are not acceptable.

Using the similarity or probability value produced by the model on its own as the final confidence will not be considered sufficient.

A limited number of control examples extracted from the document may be used for threshold setting or weighting.

## Validation
The solution must include a validation stage that checks its own output. This stage must contain at least the following three groups of checks:
- **Structural:** Tables matched to the correct page, period columns not mixed up, footnote references linked to the correct row.
- **Format:** Numeric parsing rules, preservation of period and currency information.
- **Financial:** Consistency within and across tables, comparison of summary statement values against footnote table values.

Low-confidence records must be flagged in the output.

## Output
Results must be produced as JSON or JSONL. The candidate designs the data model; the rationale for the choice must be explained in the README.

The schema must cover document information (company, period, currency), summary statement line items and their values, the rows of the footnote tables, the relationships established, the confidence values, and the validation results.

## Comparison and Error Analysis
At least two different linking approaches must be implemented and compared. The comparison must address not only the final success rate but also the examples on which the methods diverge.

At least three low-confidence or incorrect examples must be explained. For each example, the expected result, the produced result, the stage at which the error occurred, the likely cause, and a suggested improvement are sufficient.

## Deliverables
- Source code
- The generated JSON or JSONL output
- README: installation and execution steps, summary of the approach, models used and inference settings, confidence methodology, validation results, method comparison, and error analysis

Python and off-the-shelf PDF, OCR, table extraction or document processing libraries may be used freely.

## Evaluation
A complete production-grade solution is not expected. The primary criteria are how the problem is broken down into stages, how models and rules are used together, how the results are validated, how uncertainty is managed, and the reproducibility of the code.