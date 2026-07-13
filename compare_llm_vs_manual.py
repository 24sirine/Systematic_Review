import pandas as pd

LLM_FILE = "papers_llm_screened_abac_subset.xlsx"
MANUAL_FILE = "tri_papers_manuelle_subset.xlsx"

INCLUDE_COL = "INCLUS"
EXCLUDE_COL = "EXCLUS"


def get_decision(inclus, exclus):

    if pd.notna(inclus) and str(inclus).strip():
        return "include"
    if pd.notna(exclus) and str(exclus).strip():
        return "exclude"
    return "unknown"

def main():
    llm_df = pd.read_excel(LLM_FILE)
    manual_df = pd.read_excel(MANUAL_FILE)

    if len(llm_df) != len(manual_df):
        raise ValueError(
            f"Nombre de lignes différent : "
            f"LLM={len(llm_df)} / Manuel={len(manual_df)}"
        )

    total = len(llm_df)

    decision_matches = 0

    rows_detail = []

    for i in range(total):
        llm_row = llm_df.iloc[i]
        manual_row = manual_df.iloc[i]

        # Décisions
        decision_llm = get_decision(llm_row[INCLUDE_COL], llm_row[EXCLUDE_COL])
        decision_manual = get_decision(manual_row[INCLUDE_COL], manual_row[EXCLUDE_COL])

        decision_ok = decision_llm == decision_manual
        if decision_ok:
            decision_matches += 1

        rows_detail.append({
    "ligne": i + 1,

    "decision_llm": decision_llm,
    "decision_manuel": decision_manual,

    "IC_llm": llm_row[INCLUDE_COL],
    "IC_manuel": manual_row[INCLUDE_COL],

    "EC_llm": llm_row[EXCLUDE_COL],
    "EC_manuel": manual_row[EXCLUDE_COL],

    "decision_match" : decision_ok,
})

    decision_pct = (decision_matches / total) * 100

    print("\n===== COMPARAISON DECISION (SANS IC/EC) =====")
    print(f"Articles comparés : {total}")
    print(f"Correspondance décision : {decision_pct:.2f}%")



    detail_df = pd.DataFrame(rows_detail)
    detail_df.to_excel(
        "comparaison_ligne_par_ligne_llm_vs_manual.xlsx",
        index=False
    )

    print("\nFichier généré : comparaison_ligne_par_ligne_llm_vs_manual.xlsx")


if __name__ == "__main__":
    main()
