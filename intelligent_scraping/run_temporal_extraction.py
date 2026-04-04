import json
import logging
from llm.structured_extractor import StructuredExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)

INPUT_FILE = "structured_queries_symptoms.jsonl"
OUTPUT_FILE = "structured_queries_symptoms_temporal.jsonl"


def load_processed(output_file):
    processed = set()

    try:
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                obj = json.loads(line)
                processed.add(obj["original_text"])
    except FileNotFoundError:
        pass

    return processed


def main():

    extractor = StructuredExtractor()

    processed = load_processed(OUTPUT_FILE)

    logger.info(f"Already processed: {len(processed)}")

    with open(INPUT_FILE, "r", encoding="utf-8") as fin, \
         open(OUTPUT_FILE, "a", encoding="utf-8") as fout:

        for idx, line in enumerate(fin):

            obj = json.loads(line)

            text = obj["original_text"]

            if text in processed:
                logger.info(f"Skipping already processed {idx}")
                continue

            symptoms = obj["symptoms"]

            logger.info("=" * 70)
            logger.info(f"Processing query {idx}")
            logger.info(f"Query: {text}")

            try:

                temporal = extractor.extract_temporal(
                    text=text,
                    symptoms=symptoms
                )

                # merge temporal results
                obj.update(temporal)

                fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
                fout.flush()

                logger.info("Saved temporal extraction")

            except Exception as e:
                logger.error(f"Failed processing query {idx}: {e}")


if __name__ == "__main__":
    main()