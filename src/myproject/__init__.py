"""myproject — bridge package satisfying the course-pinned package name.

The course grading scaffold expects source code to live under
``src/myproject/``.  This package re-exports everything from the real
implementation modules so that:

  * Normal ``pytest`` (PYTHONPATH=.) resolves ``myproject.*`` imports here,
    which delegate to the real ``src.*`` implementation.
  * Spec-regeneration tests (PYTHONPATH=regenerated/src:...) resolve
    ``myproject.*`` imports from the LLM-generated code instead, which is
    the behaviour the rubric requires.
"""

__version__ = "0.1.0"
