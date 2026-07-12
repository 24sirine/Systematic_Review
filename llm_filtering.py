import pandas as pd
import requests
import json
import time
import re
import argparse


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-v3.1:671b-cloud"

PROMPT_TEMPLATE = """
You are assisting a systematic literature review on access control models.

Task:
Given the title and abstract of a scientific publication,
determine whether it should be INCLUDED or EXCLUDED
according to the inclusion and exclusion criteria below.

Inclusion Criteria (IC):

IC1 – Verification and Validation (V&V):
Studies addressing verification or validation of access control models,
including conflict detection between rules, policy consistency or completeness
checking, and compliance with security requirements.

IC2 – Formalization and Standardization:
Studies proposing a formal or standardized specification of access control models,
such as mathematical or logical models, formal semantics, constraints,
or policy languages / domain-specific languages (DSLs).

IC3 – Tools and Implementation (Tooling):
Studies proposing generic tools for access control
(e.g., frameworks, libraries, analysis tools, code generation tools,
visualization tools), independent of a specific application domain
(not dedicated exclusively to IoT, blockchain, healthcare, cloud, etc.).

IC4 – Hybrid Access Control Models:
Studies proposing hybrid models explicitly combining two or more
fundamental access control paradigms
(e.g., RBAC–ABAC, ABAC–OrBAC, RBAC–OrBAC).

IC5 – Artificial Intelligence applied to Access Control:
Studies using artificial intelligence techniques to assist, automate,
or improve access control, including supervised learning,
unsupervised learning, or deep learning approaches.

Exclusion Criteria (EC):

EC1 – Language:
The paper is not written in English or is of very poor translation quality.

EC2 – Superficial or Ambiguous Mention:
The paper mentions an access control paradigm only as background, example, or application context,
without making any contribution that satisfies the Inclusion Criteria,
or uses the same acronym with a different meaning
(e.g., ABAC not referring to Attribute-Based Access Control).

EC3 – Non-Relevance and Domain-Specific Applications:
Exclude studies that do not contribute to the defined research questions or
that propose access control models/tools dedicated to a specific domain
(e.g., IoT, blockchain, cloud computing, ABE, healthcare, or any other specific domain).
Only generic or domain-independent models/tools should be included.
Studies focusing on a specific access control model (e.g., ABAC, RBAC, OrBAC, TBAC)
are not considered domain-specific and must not be excluded for this reason.

EC4 – Extensions and Variants:
Studies focusing on extensions or variants of the main paradigms
(e.g., Administrative RBAC, contextual ABAC, OrBAC extensions,
workflow-based TBAC). Such studies should be excluded in order
to focus on the fundamental paradigms.

Decision rules:
- INCLUDE if at least one IC clearly applies and no EC clearly applies
- EXCLUDE if any EC clearly applies

Respond ONLY in valid JSON using this format:

{{
  "decision": "INCLUDE | EXCLUDE",
  "matched_IC": ["ICx"],
  "matched_EC": ["ECx"],
  "justification": "Short justification"
}}

Title:
{title}

Abstract:
{abstract}
"""


def query_ollama(prompt: str, retries: int = 3, pause: float = 1.5) -> dict | None:
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
         "options": {
            "temperature": 0,
            "top_k": 1,
            "top_p": 1,
            "seed": 42,
            "num_ctx": 10000,
            "repeat_penalty": 1
        }
    }

    for attempt in range(1, retries + 1):
        try:
            r = requests.post(OLLAMA_URL, json=payload, timeout=120)
            r.raise_for_status()
            response = r.json()["response"]

            match = re.search(r"\{.*\}", response, re.DOTALL)
            if match:
                return json.loads(match.group())
            else:
                print("No JSON found in LLM response, retrying...")
                time.sleep(pause)

        except Exception as e:
            print(f"Ollama attempt {attempt} failed: {e}")
            time.sleep(pause)

    print("Failed to get valid JSON from Ollama after retries")
    return None


def main():
    parser = argparse.ArgumentParser(description="Screen papers with LLM using inclusion/exclusion criteria.")
    parser.add_argument("--input", required=True, help="Input Excel file")
    parser.add_argument("--output", required=True, help="Output Excel file")
    args = parser.parse_args()

    input_xlsx = args.input
    output_xlsx = args.output

    df = pd.read_excel(input_xlsx)

    required_cols = {"Titre", "ABSTRACT"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"Le fichier Excel doit contenir : {required_cols}")

    print(f"{len(df)} articles chargés")
    print(f"Modèle LLM : {MODEL}\n")

    new_inclus = []
    new_exclus = []

    for i, row in df.iterrows():
        title = str(row["Titre"])
        abstract = str(row["ABSTRACT"])

        print(f"[{i+1}/{len(df)}] Processing: {title[:70]}...")

        prompt = PROMPT_TEMPLATE.format(title=title, abstract=abstract)
        result = query_ollama(prompt)

        if result is None:
            new_inclus.append("")
            new_exclus.append("")
            continue

        decision = result.get("decision", "")
        ic = ", ".join(result.get("matched_IC", []))
        ec = ", ".join(result.get("matched_EC", []))
        justification = result.get("justification", "")

        if decision == "INCLUDE":
            new_inclus.append(ic)
            new_exclus.append("")
        else:
            new_inclus.append("")
            new_exclus.append(ec)

        print(decision)
        print(f"Justification: {justification}")
        time.sleep(1.0)

    df_out = df.copy()
    df_out["INCLUS"] = new_inclus
    df_out["EXCLUS"] = new_exclus

    df_out.to_excel(output_xlsx, index=False)
    print(f"\nFichier généré : {output_xlsx}")


if __name__ == "__main__":
    main()
