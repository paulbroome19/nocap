# Vendored eurofiling.info core files

The EBA XBRL taxonomy imports core schemas/linkbases from
`http://www.eurofiling.info/...` that are **not** bundled in the EBA taxonomy
packages. These files (public eurofiling architecture) are vendored here so
formula validation runs **fully offline** — the Arelle adapter remaps the
`http://www.eurofiling.info/` prefix to this directory at load time.

Fetched from eurofiling.info during the feasibility spike; ~88 KB, stable.
