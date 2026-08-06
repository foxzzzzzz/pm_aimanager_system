import json
import re
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "lyra-template-v1"
WORKBOOK = FIXTURE_DIR / "lyra_v1_sanitized.xlsx"
EXPECTED = FIXTURE_DIR / "expected.json"


def test_fixture_manifest_defines_mvp_baseline() -> None:
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))

    assert expected["template"] == {
        "id": "lyra_project_spec",
        "version": "1.0",
    }
    assert expected["project"]["code"] == "ZPD1322"
    assert expected["project"]["name"] == "Lyra Pro"
    assert len(expected["team_roles"]) == 22
    assert len(expected["milestones"]) == 24
    assert expected["active_plan_name"] == "变更计划2（两次试产）"


def test_fixture_contains_no_mainland_mobile_number() -> None:
    mobile_pattern = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")

    with ZipFile(WORKBOOK) as workbook:
        xml_text = "\n".join(
            workbook.read(name).decode("utf-8", errors="ignore")
            for name in workbook.namelist()
            if name.endswith(".xml")
        )

    assert mobile_pattern.search(xml_text) is None
