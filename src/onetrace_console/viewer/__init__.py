"""onetrace's viewer: the answer view and the case view, generated from a run's record.

Specified by the viewer's specification (019), and kept in its own package (022 §2). Static
HTML, no backend, no network at view time. The page cannot verify; it shows a verification
that ran when the page was generated, and the command that repeats it without us.

Nothing in this package imports from `canary/`, and nothing in `canary/` imports from it,
so that it can move to the SDK repository with one `git mv`.

    python -m onetrace_console.viewer generate RUN_FOLDER --cli --out OUT_FOLDER
    python -m onetrace_console.viewer fingerprint OUT_FOLDER/answer.html
"""
