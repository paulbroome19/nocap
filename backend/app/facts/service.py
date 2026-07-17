"""Business logic for the facts stage.

XLSX fact ingestion + filing indicators + parameters files.

Services are plain Python and do not know HTTP exists. Per the dependency rules
they import only from `app.core` (never another stage). Empty scaffold.
"""
