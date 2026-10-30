# Test fixtures

Fake data only. Nothing here may belong to a real person.

| File | Contents |
|---|---|
| `fake_identities.py` | Fictional people with reserved-domain emails, `fake_` usernames and fictional NANP numbers |
| `fake_ro.py` | Romanian data generated at test time: phones from `phonenumbers` example numbers, CNPs born 1800-1899, ID series `XX`, fictional names with diacritics |

## How `phonenumbers` classifies the fake numbers

Checked with `phonenumbers` 9.0.42. `tests/unit/test_fixture_phone_classes.py` re-checks this,
so a library update that changes it fails a test instead of silently changing behaviour.

| Number | `is_possible_number` | `is_valid_number` | `number_type` |
|---|---|---|---|
| `+1 202 555 0143`, `+1 415 555 0123` (fictional NANP, 555-0100..0199) | yes | **yes** | `FIXED_LINE_OR_MOBILE` |
| Romanian example mobile (`example_number_for_type("RO", MOBILE)`) | yes | yes | `MOBILE` |
| Romanian example fixed line (`example_number_for_type("RO", FIXED_LINE)`) | yes | yes | `FIXED_LINE` |

Consequences:
- Phone-enricher tests can treat the fictional NANP numbers as valid, but must not expect a
  `MOBILE` or `FIXED_LINE` type for them.
- Because they are valid, the identifier checker exempts the 555-0100..0199 range explicitly;
  other 555 numbers are not exempt.
- Romanian example numbers are valid, so the identifier checker blocks them if anyone writes one
  into a file. Generate them in the test instead.

## How the identifier checker uses `phonenumbers`

- National formats are matched with `Leniency.VALID` for RO, MD, US, GB, FR, ES, HU, BG and UA.
  DE and IT are left out: their plans accept almost any 6-13 digit run, so CNP-shaped numbers
  and timestamps would match. National matches of 13+ digits are skipped (CNP territory).
- International forms (`+...`, `00...`) are matched with `Leniency.POSSIBLE` for every country,
  so numbers in ranges the metadata doesn't know yet are still caught.
- `00`-prefixed international numbers are rewritten to `+` before that pass, since region `ZZ`
  only recognises `+`.
- A bare `0[237]` + 8 digits run is checked even when glued to letters (`tel07...`).
- Any phone or CNP match inside a hex run of 32+ characters containing a letter is ignored
  (hashes in lockfiles and URLs).
