"""The onetrace console: every run in one place.

**The run folder is the unit of truth and this package never computes a verdict.** It
stores the bytes an emitter wrote, keeps the reports the verifier and the verbs produced
over them, and reads those reports. If the console and the offline file ever disagree,
the file is right and the console has a defect.
"""
__all__ = ["__version__"]

__version__ = "0.1.1"
