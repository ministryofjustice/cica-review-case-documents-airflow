"""Parse IAM handwriting dataset XML ground truth files.

This file extracts both machine-printed (LOB corpus prompt) and handwritten
transcriptions from IAM dataset XML files and outputs a JSONL file.

Ground Truth Schema:
    - form_id: Primary key (e.g., "a01-000u")
    - writer_id: Writer identifier (e.g., "000")
    - image_path: Relative path to PNG image
    - gt_print_text: Machine-printed ground truth
    - gt_print_word_count: Word count of print text
    - gt_handwriting_text: Handwritten ground truth

Example XML structure:
    <form id="a01-000u" writer-id="000">
        <machine-printed-part>
            <machine-print-line text="A MOVE to stop Mr. Gaitskell..." />
        </machine-printed-part>
        <handwritten-part>
            <line id="a01-000u-00" text="A MOVE to stop Mr. Gaitskell from">
                <word id="a01-000u-00-00" text="A" />
            </line>
        </handwritten-part>
    </form>
"""

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path

from . import DATA_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GroundTruthRecord:
    """Ground truth record for a single IAM form."""

    form_id: str
    writer_id: str
    image_path: str
    gt_print_text: str
    gt_print_word_count: int
    gt_handwriting_text: str


def parse_single_xml(xml_path: Path) -> GroundTruthRecord:
    """Parse a single IAM XML ground truth file.

    Args:
        xml_path: Path to the XML file.

    Returns:
        GroundTruthRecord for output to JSONL.

    Raises:
        FileNotFoundError: If the XML file doesn't exist.
        ET.ParseError: If the XML is malformed.
    """
    if not xml_path.exists():
        raise FileNotFoundError(f"XML file not found: {xml_path}")

    tree = ET.parse(xml_path)
    root = tree.getroot()

    # Extract form metadata
    form_id = root.get("id", "")
    writer_id = root.get("writer-id", "")

    # Derive image path from form_id
    image_path = f"data/page_images/{form_id}.png"

    # Parse machine-printed part (LOB corpus prompt)
    machine_printed_lines = []
    machine_printed_part = root.find("machine-printed-part")
    if machine_printed_part is not None:
        for line_elem in machine_printed_part.findall("machine-print-line"):
            line_text = line_elem.get("text", "")
            if line_text:
                machine_printed_lines.append(line_text)

    gt_print_text = " ".join(machine_printed_lines)
    gt_print_word_count = len(gt_print_text.split())

    # Parse handwritten part
    handwritten_lines = []
    handwritten_part = root.find("handwritten-part")
    if handwritten_part is not None:
        for line_elem in handwritten_part.findall("line"):
            line_text = line_elem.get("text", "")
            if line_text:
                handwritten_lines.append(line_text)

    gt_handwriting_text = " ".join(handwritten_lines)

    return GroundTruthRecord(
        form_id=form_id,
        writer_id=writer_id,
        image_path=image_path,
        gt_print_text=gt_print_text,
        gt_print_word_count=gt_print_word_count,
        gt_handwriting_text=gt_handwriting_text,
    )


def parse_all_xmls(xml_dir: Path) -> list[GroundTruthRecord]:
    """Parse all XML files in a directory.

    Args:
        xml_dir: Directory containing XML ground truth files.

    Returns:
        List of GroundTruthRecord objects.
    """
    records = []
    xml_files = sorted(xml_dir.glob("*.xml"))

    for xml_path in xml_files:
        try:
            record = parse_single_xml(xml_path)
            records.append(record)
        except ET.ParseError:
            logger.exception("Failed to parse XML: %s", xml_path.name)
        except FileNotFoundError:
            logger.warning("XML file not found: %s", xml_path.name)

    logger.info("Parsed %d of %d XML files", len(records), len(xml_files))
    return records


def write_ground_truth_jsonl(records: list[GroundTruthRecord], output_path: Path) -> int:
    """Write ground truth records to a JSONL file.

    Args:
        records: List of GroundTruthRecord objects.
        output_path: Path to write the JSONL file.

    Returns:
        Number of records written.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    logger.info("Wrote %d records to %s", len(records), output_path)
    return len(records)


def main() -> None:
    """Parse all XML ground truth files and write to JSONL."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    data_dir = DATA_DIR
    xml_dir = data_dir / "ground_truth"
    output_file = data_dir / "ground_truth.jsonl"

    if not xml_dir.exists():
        logger.error("XML directory not found: %s", xml_dir)
        return

    records = parse_all_xmls(xml_dir)

    if not records:
        logger.warning("No records parsed")
        return

    write_ground_truth_jsonl(records, output_file)


if __name__ == "__main__":
    main()
