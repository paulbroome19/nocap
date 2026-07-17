"""Business logic for the validation stage.

Structural checks (v1); the Arelle adapter slots in here in v2.

Services are plain Python and do not know HTTP exists. Per the dependency rules
they import only from `app.core` (never another stage). Empty scaffold.
"""
