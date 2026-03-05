# main.py

import pandas as pd
import json
import logging
from extraction_pipeline import ExtractionPipeline


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


INPUT_FILE = "/home/maaz-rafiq/work/phd_thesis_tanveer/CamelMedAgents-RAG/dataset/patient_description_sir_Suffian/PI-PD-20_consolidated_enriched_with_catogries.tsv"
OUTPUT_FILE = "structured_queries.jsonl"


def main():
    df = pd.read_csv(INPUT_FILE, sep="\t")

    pipeline = ExtractionPipeline()

    total = len(df)
    logger.info(f"Total queries to process: {total}")

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:

        for idx, row in df.iterrows():
            logger.info("=" * 80)
            logger.info(f"Processing query {idx + 1}/{total}")
            logger.info(f"Label: {row['Label']}")
            logger.info(f"Category: {row['Category']}")
            logger.info(f"Query Text: {row['Discussion']}")

            try:
                structured = pipeline.process(
                    text=row["Discussion"],
                    label=row["Label"],
                    category=row["Category"]
                )

                # Save immediately (JSON Lines format)
                f.write(json.dumps(structured, ensure_ascii=False) + "\n")
                f.flush()

                logger.info("💾 Saved result successfully")

            except Exception as e:
                logger.error(f"❌ Failed processing query {idx + 1}: {str(e)}")

    logger.info("🎉 All queries processed")


if __name__ == "__main__":
    main()