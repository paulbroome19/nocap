"""Business logic for the generation stage.

Facts + snapshot -> xBRL-CSV package (zip).

Services are plain Python and do not know HTTP exists. Per the dependency rules
they import only from `app.core` (never another stage). Empty scaffold.
"""
