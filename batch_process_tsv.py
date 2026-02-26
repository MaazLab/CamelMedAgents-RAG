import json
import pandas as pd
from tqdm import tqdm

from query_reformulation.pipeline import LLMQueryProcessingPipeline


INPUT_PATH = "/home/maaz-rafiq/work/phd_thesis_tanveer/CamelMedAgents-RAG/dataset/patient_description_sir_Suffian/PI-PD-20 consolidated.tsv"
OUTPUT_PATH = "/home/maaz-rafiq/work/phd_thesis_tanveer/CamelMedAgents-RAG/dataset/patient_description_sir_Suffian/PI-PD-20_consolidated_enriched.tsv"


def serialize(obj):
    return json.dumps(obj, ensure_ascii=False)


def main():

    print("Loading TSV file...")
    df = pd.read_csv(INPUT_PATH, sep="\t")

    if "Discussion" not in df.columns:
        raise ValueError("Column 'Discussion' not found in TSV file.")

    pipeline = LLMQueryProcessingPipeline()

    # Create output file and write header
    output_columns = list(df.columns) + [
        "intent_separation",
        "symptom_extraction",
        "structured_representation",
        "retrieval_queries"
    ]

    print("Creating output file...")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\t".join(output_columns) + "\n")

    print("Processing rows...")

    for index, row in tqdm(df.iterrows(), total=len(df)):

        discussion = row["Discussion"]

        if pd.isna(discussion) or not str(discussion).strip():
            intent_json = None
            symptom_json = None
            structured_json = None
            retrieval_json = None
        else:
            try:
                result = pipeline.run(str(discussion))

                intent_json = serialize(result.get("intent_separation"))
                symptom_json = serialize(result.get("symptom_extraction"))
                structured_json = serialize(result.get("structured_representation"))
                retrieval_json = serialize(result.get("retrieval_queries"))

            except Exception as e:
                print(f"Error at row {index}: {e}")
                intent_json = None
                symptom_json = None
                structured_json = None
                retrieval_json = None

        # Prepare full row for writing
        new_row = row.tolist() + [
            intent_json,
            symptom_json,
            structured_json,
            retrieval_json
        ]

        # Append immediately
        with open(OUTPUT_PATH, "a", encoding="utf-8") as f:
            f.write("\t".join(
                "" if v is None else str(v).replace("\n", " ")
                for v in new_row
            ) + "\n")

    print(f"Done. File saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()