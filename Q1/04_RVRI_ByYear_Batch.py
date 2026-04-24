from __future__ import annotations

from pathlib import Path

from importlib.util import module_from_spec, spec_from_file_location


def load_validation_module():
    module_path = Path(__file__).resolve().parent / "03_RVRI_Advanced_Validation.py"
    spec = spec_from_file_location("annual_validation", module_path)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main() -> None:
    validation = load_validation_module()
    report = validation.run_validation_by_year()
    print("Q1 annual by-year validation finished.")
    print(f"Generated year folders: {report['years']}")
    print("Saved summary to: Q1/output/by_year/by_year_summary.json")


if __name__ == "__main__":
    main()
