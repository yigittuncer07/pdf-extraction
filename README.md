# yapikredi-pdf-extraction


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

**The general pipeline idea is:**
1. PDF ingestion, the goal here is to turn the PDF as is into a usable format.
2. Normalization, as described in the task description.
3. Candidate generation, this is hardcoded, no ML involved, just return the full list of rows that can be relevant to a certain summary row, using note links.
4. Scoring, here we use ML to decide which table rows are actually relevant to the summary rows, and extract relations, we will have a single relation which is relates_to (which is forced unless we use something other than embeddings, rerankers, cross encoders, etc...). Use 2 separate approaches here to see what works best and to compare. 
5. Validation, we must run structural, financial and format validations at the end. We must construct confidence for tables, relations, etc, using the validation steps and the model similarity output jointly.