# Every model module must be imported (and its class re-exported) here so it
# registers on Base.metadata — this is what alembic/env.py imports to build
# target_metadata for autogenerate. A model defined but not imported here is
# invisible to `alembic revision --autogenerate`.
#
# Example, once a model module exists:
<<<<<<< HEAD
# from .term import Term
=======
#   from .term import Term
>>>>>>> origin/main
#
# __all__ = ["Term"]
