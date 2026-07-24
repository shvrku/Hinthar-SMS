# Walkthrough - Unique Code Identity & Exam Candidate Number Implementation

All requested features and edge cases for human-readable unique codes (`unique_code`) and student exam candidate numbers (`exam_candidate_number`) have been fully implemented, migrated, and verified.

---

## 1. Summary of Changes

### Key Features Implemented
1. **Model Updates ([people/models.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/people/models.py))**:
   - `Student`: Added indexed `unique_code` (`unique=True`, `editable=False`), `school_code`, and `exam_candidate_number` (`null=True`, `blank=True`, `unique=True`).
   - `Teacher`: Added indexed `unique_code` (`unique=True`, `editable=False`), `school_code`, and `join_date` (`DateField`).
   - `Staff`: Added indexed `unique_code` (`unique=True`, `editable=False`), `school_code`, and `join_date` (`DateField`).
   - `Subject`: Excluded as requested.

2. **Atomic Code Generator ([people/utils.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/people/utils.py))**:
   - `generate_unique_code(instance)`:
     - Formats:
       - **Student**: `{SchoolCode}{EntryYear}-{Sequence:05d}` (e.g. `HIS24-00143` or `SPD24-00143`)
       - **Teacher**: `{SchoolCode}T{JoinYear}-{Sequence:05d}` (e.g. `HIST22-00007`)
       - **Staff**: `{SchoolCode}S{JoinYear}-{Sequence:05d}` (e.g. `HISS24-00001`)
     - Cohort sequence derived from MAX value + 1 (never reuses gaps).
     - Atomic lock: Uses `transaction.atomic()` with `select_for_update()` to prevent race conditions during concurrent creations.

3. **Schema & Data Migrations**:
   - **`0008_add_unique_code_fields.py`**: Creates non-null fields with initial `null=True`.
   - **`0009_backfill_unique_codes.py`**: Chronologically backfills all pre-existing `Student`, `Teacher`, and `Staff` records using actual historical entry/join years, verifying 0 null records remain before completing.

4. **DRF Serializers & Admin ([people/serializers.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/people/serializers.py), [people/admin.py](file:///d:/SchoolClubActivity/Hinthar-SMS/Hinthar-SMS/people/admin.py))**:
   - Exposed `unique_code` (as `read_only`), `school_code`, `join_date`, and `exam_candidate_number` across serializers and Django Admin interfaces.
   - Enforced `editable=False` and `read_only=True` to prevent manual edit collisions.

---

## 2. Verification & Automated Tests

All 18 tests in the `people` test suite executed successfully:

```
Found 18 test(s).
System check identified no issues (0 silenced).
..................
----------------------------------------------------------------------
Ran 18 tests in 20.594s

OK
```

### Verified Scenarios:
- **Format Verification**: `HIS26-00001` (Student), `HIST26-00001` (Teacher), `HISS26-00001` (Staff).
- **Sequential Increment**: Multiple creations within same entry year yield incremental 5-digit zero-padded numbers (`00001`, `00002`).
- **Gap & Re-import Resilience**: Deleting `00001` when `00002` exists results in `00003` (MAX + 1).
- **Save Idempotency**: Calling `.save()` multiple times on existing record preserves `unique_code`.
- **Exam Candidate Number**: Remains `None` during creation and populates correctly when assigned.
