import argparse
from collections import Counter

from app.data.semester_iii_2025 import SEMESTER_III_SUBJECTS
from app.database.connection import SessionLocal
from app.services.academic_syllabus_import import (
    format_import_report,
    import_semester_iii,
    validate_import_data,
)


def _static_dry_run_report() -> dict:
    validate_import_data()
    return {
        "mode": "dry-run",
        "database_touched": False,
        "planned": dict(
            Counter(
                {
                    "academic_hierarchy": 4,
                    "subjects": len(SEMESTER_III_SUBJECTS),
                    "branch_offerings": len(SEMESTER_III_SUBJECTS),
                    "elective_options": 3,
                    "syllabus_versions": len(SEMESTER_III_SUBJECTS),
                    "units": sum(len(subject["units"]) for subject in SEMESTER_III_SUBJECTS),
                    "topics": sum(
                        len(unit["topics"])
                        for subject in SEMESTER_III_SUBJECTS
                        for unit in subject["units"]
                    ),
                    "subtopics": sum(
                        len(topic.get("subtopics", ()))
                        for subject in SEMESTER_III_SUBJECTS
                        for unit in subject["units"]
                        for topic in unit["topics"]
                    ),
                }
            )
        ),
        "note": "No database connection or write was made. Pass --apply to import.",
    }


def seed(*, apply: bool = False) -> dict:
    if not apply:
        return _static_dry_run_report()
    with SessionLocal() as db:
        return import_semester_iii(db, apply=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Import source-linked RVCE Semester III syllabus metadata.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the idempotent import to the configured database.",
    )
    args = parser.parse_args()
    report = seed(apply=args.apply)
    print(format_import_report(report))
    return 1 if report.get("conflicts") else 0


if __name__ == "__main__":
    raise SystemExit(main())
