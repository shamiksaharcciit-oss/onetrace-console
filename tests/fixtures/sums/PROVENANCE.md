Two sums files over the committed run folder `tests/fixtures/r11/two-minimal-nodes/`, written by
the real `sha256sum` (GNU coreutils 8.32, as Git for Windows ships it), run from inside that folder
over its five files in sorted order:

- `default.SHA256SUMS`: `sha256sum <files>`, with no mode flag. Git for Windows writes the binary
  form, `<hash> *<path>`. It is the form the end-to-end check of 30 September was refused on.
- `text.SHA256SUMS`: `sha256sum --text <files>`, the text form, `<hash>  <path>`.

They are data, not source, and are kept byte for byte as the tool wrote them. `tests/test_sums_forms.py`
reads them.
