"""Business logic for the taxonomy stage.

DPM release upload, snapshot registry, datapoint lookup.

Services are plain Python and do not know HTTP exists. Per the dependency rules
they import only from `app.core` (never another stage). Empty scaffold.
"""
