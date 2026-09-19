# yapikredi-pdf-extraction


## PERSONAL NOTES:

- Using tesseract OCR on the PDF resulted in lots of OCR errors. EasyOCR also failed to properly extract the data.
- SmallDocling failed as a VLM. The output quality is not good enough. 


**The general pipeline idea is:**
1. PDF ingestion, the goal here is to turn the PDF as is into a usable format.
2. Normalization, as described in the task description.
3. Candidate generation, this is hardcoded, no ML involved, just return the full list of rows that can be relevant to a certain summary row, using note links.
4. Scoring, here we use ML to decide which table rows are actually relevant to the summary rows, and extract relations, we will have a single relation which is relates_to (which is forced unless we use something other than embeddings, rerankers, cross encoders, etc...). Use 2 separate approaches here to see what works best and to compare. 
5. Validation, we must run structural, financial and format validations at the end. We must construct confidence for tables, relations, etc, using the validation steps and the model similarity output jointly.