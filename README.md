# Systematic Literature Review Pipeline

# Overview
This repository contains the scripts and results of a semi-automated pipeline for conducting Systematic Literature Review. The proposed workflow is designed to be domain-independent and can be applied to any research topic or domain. <br>
As a case of study, the pipeline has been applied to the **Attribute-Based Access Control (ABAC)**.

# Pipeline Overview

The complete workflow consists of the following main steps:
<img width="921" height="201" alt="ABAC_WORKFLOW_ANG" src="https://github.com/user-attachments/assets/e46dfe91-da90-4314-802c-bd5479fc1142" />

1. Multi-source literature collection
2. Data merging and deduplication
3. Manual abstract completion
4. LLM-based pre-screening
5. LLM performance evaluation
6. Manual validation and final selection
   
---

# 1. Multi-source Literature Collection
To minimize the risk of missing relevant studies, the pipeline integrates multiple bibliographic databases:
- Semantic Scholar
- OpenAlex
- DBLP <br>
Dedicated scripts were developed to automatically retrieve publications using their respective APIs.
The collected publications are filtered using keyword-based matching on titles and abstracts and stored as CSV files containing the main metadata.

## Semantic Scholar Retrieval
**Script:** s2_fetch_clean_csv.py <br>
**Example execution:**
python s2_fetch_clean_csv.py \
--query "(\"attribute based access control\" | \"attribute-based access control\" | ABAC) + (\"access control\")" \
--terms "attribute based access control,attribute-based access control,abac,access control" \
--mode any \
--year "1995-" \
--out abac_s2.csv <br>
**Output:** abac_s2.csv

## OpenAlex Retrieval
**Script:** openalex_fetch_clean_csv.py <br>
**Example execution:**
python openalex_fetch_clean_csv.py \
--search "attribute based access control attribute-based access control ABAC access control" \
--terms "attribute based access control,attribute-based access control,abac,access control" \
--mode any \
--from-year 1995 \
--to-year 2026 \
--no-cs-only \
--out abac_openalex.csv <br>
**Output:** abac_openalex.csv

## DBLP Retrieval
**Script:** dblp_fetch_clean_csv.py <br>
**Example execution:** python dblp_fetch_clean_csv.py abac_dblp <br>
**Output:** abac_dblp.csv


# 2. Data merging and deduplication
Since the same publication may appear across multiple bibliographic sources with slightly different metadata, a data fusion strategy is applied to consolidate all retrieved records into a single dataset. Duplicate detection is primarily performed through DOI matching whenever a DOI is available. For publications without DOI information, records are compared using normalized titles and publication years. When duplicate entries are identified with inconsistent publication years, the most recent version of the publication is retained.

**Script:** merge_all_clean_csv.py <br>
**Example execution:** python merge_all_clean_csv.py --basename abac <br>
**Output:** abac_merged.xlsx

# 3. Manual abstract completion
Abstract information is retrieved whenever available through Semantic Scholar and OpenAlex APIs. However, some publications do not provide abstracts through public APIs. These missing abstracts were manually completed by consulting the original publications.

**Result:** abac_merged_completed.xlsx

# 4. LLM-based pre-screening
To accelerate the screening process, an automated filtering step base on Large Language Models (LLMs) was integrated. The script uses the ollama API to evaluate candidate publications according to predefined inlusion and exclusion criteria.
For each article, the LLM generates : the inclusion/exlusion decision , the triggered criteria and a short justification.<br>
This script communicates with a locally running ollama server, which is configured to use the cloud-hosted deepseek-v3.1:671b-cloud model. <br>
**Important:** This step requires Ollama to be installed and running locally on your machine, you can follow the instructions on the official website : https://ollama.com/

**Script:** llm_filtering.py <br>
**Execution:** python llm_filtering.py --input abac_merged_completed.xlsx --output paper_screened_final_abac.xlsx <br>
**Output:** paper_screened_final_abac.xlsx

# 5. LLM performance evaluation
# 6. Manual validation and final selection
Although LLM-based filtering significantly reduces the screening workload, manual validation remains necessary. This final review step consists of : checking inaccessible papers, removing informal publications and confirming relevance according to research objectives.
