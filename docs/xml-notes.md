# xBRL-XML instance — notes (Step 1 ground truth)

Reference for adding **xBRL-XML** as a second generation format alongside
xBRL-CSV. Sources (untracked, in `docs/reference/`):

- **`sample_instances.zip` → `xBRL-XML.zip`** — real EBA sample instances, **DPM
  4.1**, frameworks Pillar3 / MICA / PAY / ESG. Random data. **No COREP sample**
  (same gap as the CSV path — see `package-notes.md`).
- **`EBA Filing Rules v5.8_2026_02_25.pdf`** — the Filing Rules (section
  "Implementation for xBRL-XML reports", rules 2.1–2.26; filing indicators 1.6).
- **`DPM2 Database_v 4_2_20251125.accdb`** — the DPM 2.0 Access DB (release 5 =
  4.2). Context assembly is derived from here.

Every recipe below is **verified by reconstructing a real fact** from the
IRRBBDIS sample (see §7). A sample fact:

```xml
<eba_met:mi1001 contextRef="c1" unitRef="uEUR" decimals="-3">97681</eba_met:mi1001>
```

---

## 1. Overall instance structure

A single `.xbrl` file (not a package folder — one XML document), zipped for
remittance with the **same file-naming convention as CSV** (`package-notes.md`
§2) but ending `.xbrl` inside the zip, not `.zip`:

```
DUMMYLEI123456789012.CON_FR_PILLAR3010000_IRRBBDIS_2025-06-30_20250522105232518.xbrl
```

Document order (from the samples):
1. `<?xml version='1.0' encoding='UTF-8'?>`
2. `<xbrli:xbrl …>` root with the full namespace map (§6).
3. `<link:schemaRef>` (§2) — exactly one.
4. `<xbrli:unit>` declarations (§4).
5. `<xbrli:context id="cfi">` — the filing-indicator context (entity+period, **no
   scenario**).
6. `<find:fIndicators>` — the filing-indicator tuple (§5).
7. `<xbrli:context id="c1"…>` — one data context per distinct dimensional
   signature (entity + period + scenario).
8. Fact elements (§3), one per reported datapoint.

Software processing instruction (rule 2.26): a PI **after** the XML declaration,
```xml
<?instance-generator id="…" version="…" creationdate="…"?>
```
Rule 2.26 is a SHOULD (`missingOrIncorrectSoftwareInformation`) requiring at
least `id`, `version`, `creationdate`. The samples do **not** include it (it is
optional); we emit a fixed one for provenance + determinism.

---

## 2. schemaRef (rules 2.2, 2.3)

```xml
<link:schemaRef xlink:type="simple"
  xlink:href="http://www.eba.europa.eu/eu/fr/xbrl/crr/fws/{fw}/{taxo_ver}/mod/{module}.xsd"/>
```

- **Exactly one** taxonomy reference (2.3); **absolute** URL (2.2).
- Same URL as the CSV `report.json` `extends`, but `.xsd` not `.json`, and the
  module filename is `ModuleVersion.Code.lower()` with underscores preserved
  (`SEPA_IPR → sepa_ipr.xsd`, `MICA_OF → mica_of.xsd`). For LCR at 4.2:
  `…/fws/corep/4.2/mod/corep_lcr_da.xsd` (derived; no COREP sample to confirm the
  module filename — treat as derived, like the CSV entry point).

---

## 3. Fact element

```xml
<eba_met:{metricCode} contextRef="{cid}" unitRef="{uid}" decimals="{d}">{value}</eba_met:{metricCode}>
```

- **Element** = the metric, namespace `eba_met`
  (`http://www.eba.europa.eu/xbrl/crr/dict/met`), local name = the metric code
  (`mi1001`, `qCCB`). **All metrics** in the DB use the plain `eba_met` namespace
  (§7); the versioned `eba_met_3.4` / `eba_met_4.1` namespaces are declared but
  no sampled metric uses them — flag if a real COREP metric needs one.
- **contextRef** → a `<xbrli:context>` id; **unitRef** → a `<xbrli:unit>` id.
- **decimals** — per rule 2.17 use `@decimals` (never `@precision`).
- **Numeric facts only** carry `unitRef`/`decimals`. Non-numeric (string / enum /
  boolean / date) facts carry `contextRef` only, no unit/decimals (XBRL standard;
  the sampled modules were all-numeric so this is the standard rule, not
  sample-confirmed).

---

## 4. Units (rules 2.21–2.24)

Only two unit shapes appear across all samples:

```xml
<xbrli:unit id="uEUR"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>
<xbrli:unit id="uPURE"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
```

- **Monetary** datapoints → the currency unit `iso4217:{baseCurrency}`.
- **Percentage / decimal / ratio** → `xbrli:pure`.
- **Integer** → `xbrli:pure` (numeric, unitless-but-pure).
- **Non-numeric** → no unit.
- No duplicate units (2.21); no unused units (2.22) — emit only units actually
  referenced.

---

## 5. Contexts + filing indicators

### Entity + period (rules 2.8, 2.9, 2.10)
```xml
<xbrli:entity>
  <xbrli:identifier scheme="https://eurofiling.info/eu/rs">{LEI}.{scope}</xbrli:identifier>
</xbrli:entity>
<xbrli:period><xbrli:instant>{referenceDate}</xbrli:instant></xbrli:period>
```
Scheme is the neutral eurofiling RS URI (rule 5.2). Value = `{LEI}.{scope}` (e.g.
`DUMMYLEI123456789012.CON`) — identical to the CSV `entityID` minus the `rs:`
prefix. Single subject per report (2.9); instant period (LCR is instant/`Stock`).

### Scenario (rules 2.14, 2.15) — dimensions go in **scenario**, never segment
```xml
<xbrli:scenario>
  <xbrldi:explicitMember dimension="eba_dim_3.4:PRP">eba_PL:x11</xbrldi:explicitMember>
  …
</xbrli:scenario>
```
`xbrli:segment` is prohibited (2.14). Typed dimensions (open tables, `xbrldi:typedMember`
with `eba_typ:*`) do not appear in the closed-template samples → **v2**, same as
the CSV open-table gap.

### Filing indicators (rule 1.6)
```xml
<xbrli:context id="cfi">…entity + period, no scenario…</xbrli:context>
<find:fIndicators>
  <find:filingIndicator contextRef="cfi" find:filed="true">K_00.04</find:filingIndicator>
  <find:filingIndicator contextRef="cfi" find:filed="false">C_73.00</find:filingIndicator>
</find:fIndicators>
```
- `find` = `http://www.eurofiling.info/xbrl/ext/filing-indicators`.
- One `<find:filingIndicator>` per template, text = the **DB-form template code**
  (`K_00.04`, `C_73.00`) — the same value the CSV `FilingIndicators.csv` carries.
- **`find:filed`** — `"true"` (positive / Required or Optional-with-facts) or
  `"false"` (negative / Not required). The attribute is present-and-`true` in
  some samples and omitted in others (omitted ⇒ true). We emit it explicitly:
  `true` for reported, `false` for not-reported. This maps 1:1 to our
  `run.filing_indicators` `{template_code, reported}` — `reported → find:filed`.
- Rule 1.6 requires a **positive** indicator for every intentionally-reported
  template (`missingPositiveFilingIndicator`), and **negative** indicators for
  "expected but not filed" templates — our Not-required declaration.

---

## 6. Namespaces (root)

Fixed core: `xbrli, xbrldi, xlink, xsi, link, iso4217, find`
(`…/ext/filing-indicators`), plus **derived** EBA namespaces:

| prefix | URI | for |
|---|---|---|
| `eba_met` | `…/crr/dict/met` | all metric elements |
| `eba_dim_{ver}` | `…/crr/dict/dim/{ver}` | dimensions, per introduction version |
| `eba_{DOMAIN}` | `…/crr/dict/dom/{DOMAIN}` | domain members (unversioned) |
| `eba_typ` | `…/crr/dict/typ` | typed-dimension values (v2) |

Only the namespaces actually used need declaring; declare deterministically
(sorted).

---

## 7. **The context-assembly recipe (the hard part) — DPM → XML**

Everything below is derived from the DPM Access DB and **verified** by
reconstructing the IRRBBDIS `mi1001 @ c1` fact exactly.

### The core model discovered
- A DPM **`Property`** is a *metric* (`IsMetric = -1`/true) or a *dimension*
  (`IsMetric = 0`).
- **Every Property has a counterpart `Item` with `ItemID == PropertyID`** in
  `Category 1002` (code `_PR`, "Properties"). That item's row in **`ItemCategory`**
  gives its **`Code`** (`mi1001`, `PRP`) and **`StartReleaseID`**.
- **`PropertyCategory`** maps a *dimension* Property → its **domain** `Category`.
- **Members** are ordinary `Item`s in a domain `Category`; their
  **`ItemCategory.Signature`** is the ready-made XBRL member QName
  (`eba_PL:x11`, `eba_qAI:qx2025`).
- A datapoint's dimensional signature is **`Context`** →
  **`ContextComposition(ContextID, PropertyID, ItemID)`** rows =
  `(dimension-Property, member-Item)` pairs.

### From a resolved datapoint (`VariableVID`) to XML

`VariableVersion` row (release-scoped by the usual `Start/EndReleaseID`
predicate) gives **`PropertyID`** (the metric) and **`ContextID`** (the
dimensional context).

**Metric element:**
```sql
SELECT Code FROM ItemCategory WHERE ItemID = {VariableVersion.PropertyID} AND CategoryID = 1002;
-- → mi1001   ⇒  <eba_met:mi1001 …>
```

**Scenario members** (one explicitMember per row):
```sql
SELECT dic.Code                               AS dim_code,      -- PRP
       dr.Code                                AS dim_version,   -- 3.4  (namespace suffix)
       mic.Signature                          AS member_qname   -- eba_PL:x11
FROM ContextComposition cc
JOIN ItemCategory dic ON dic.ItemID = cc.PropertyID AND dic.CategoryID = 1002   -- dimension
JOIN Release      dr  ON dr.ReleaseID = dic.StartReleaseID                       -- intro release
JOIN ItemCategory mic ON mic.ItemID = cc.ItemID                                  -- member
WHERE cc.ContextID = {VariableVersion.ContextID};
```
Each row →
```xml
<xbrldi:explicitMember dimension="eba_dim_{dim_version}:{dim_code}">{member_qname}</xbrldi:explicitMember>
```
- **Dimension QName** = `eba_dim_{Release.Code(dimension.StartReleaseID)}:{Code}`.
  The version namespace is the **introduction release** of the dimension (3.4
  dims stay `eba_dim_3.4` even in a 4.2 report), not the report's release.
- **Member QName** = the member's `ItemCategory.Signature` verbatim.
- `ContextComposition.PropertyID` is the composite `10124{00}{PropertyID}` form
  (`10124` class prefix + the 5-digit Property id); it equals the dimension
  Property's PK directly, so the join on `ItemID = cc.PropertyID` is exact.

**Unit** — from the datapoint's datatype (already returned by `resolve`):
monetary → `iso4217:{ccy}`; percentage/decimal/integer → `xbrli:pure`;
non-numeric → none.

### Verified worked example (IRRBBDIS, DPM 4.1)
Sample fact `<eba_met:mi1001 contextRef="c1" unitRef="uEUR" decimals="-3">97681</…>`,
context `c1` scenario (verbatim from the sample):

| sample explicitMember | DPM reconstruction |
|---|---|
| `eba_dim_3.4:PRP` → `eba_PL:x11` | Property/Item `1012400510` `_PR.Code=PRP`, `StartRelease 1→3.4`, domain `PL(320)`; member Item `2575` `Signature=eba_PL:x11` |
| `eba_dim_3.4:TRI` → `eba_TR:x9` | `1012400170` `TRI`, 3.4, domain `TR(370)`; member `2701 eba_TR:x9` |
| `eba_dim_3.4:CSC` → `eba_CS:x98` | `1012400770` `CSC`, 3.4, domain `CS(500)`; member `10901 eba_CS:x98` |
| `eba_dim_4.0:qCAA` → `eba_qAI:qx2025` | `1012403340` `qCAA`, `StartRelease 3→4.0`, domain `qAI(1007)` |
| `eba_dim_4.0:qBEG` → `eba_qRF:qx2054` | `1012404531` `qBEG`, 4.0, domain `qRF(1034)` |
| metric `eba_met:mi1001` | Item `10848` `_PR.Code=mi1001`, `Property.IsMetric=-1` |

Every element reconstructs exactly. The same mechanism was run for a **COREP LCR**
datapoint (`C_67.00.a r0020 c0060`, `VariableVID 5426985` → `PropertyID 1012404319`
metric `qCCB`, `ContextID 1669608` dims `qBDE→eba_qOI:qx2010`, `qMHI→eba_qAZ:qx2002`)
— it resolves cleanly, but there is **no COREP XML sample to cross-check the fact
against** (identical known gap to the CSV entry-point).

---

## 8. Implications for our snapshot (Step 2 scope)

**Not a wall — a clean, bounded extension.** The recipe is fully DPM-derivable;
nothing needs guessing. But it requires data our per-snapshot SQLite does **not**
currently project:

1. **Ingestion**: extend `DPM_TABLES` (taxonomy/service) to also project
   `Item, ItemCategory, Property, PropertyCategory, Context, ContextComposition,
   Category` (`Release` is already projected). Re-ingest. These are modest except
   `ContextComposition` (~1.7M rows) and `Context` (~245k) — index
   `ContextComposition(ContextID)` and `ItemCategory(ItemID, CategoryID)`.
2. **Resolver**: today `resolve(t,r,c)` returns `{datapoint_id (VariableID),
   datatype_code, …}`. Add the XML signature — either fields on the existing
   result (`property_id`, `context_id`) or a dedicated
   `resolve_xml_signature(datapoint) → {metric_qname, [(dim_qname, member_qname)…], unit, decimals}`.
   `VariableVersion.PropertyID` and `.ContextID` are the only new columns needed
   from the row already being fetched.
3. Everything else (facts, filing indicators, parameters, entity, release
   binding) is reused untouched.

---

## 9. XML structural check-set (Step 2 validation dispatch)

The CSV "extras" checks (CRLF, header, field-count, OIM special values, decimals
suffix, key columns) are **CSV-only** and must not run against XML. The XML
format gets its own set, derived from the rules confirmed above:

| check | rule | what |
|---|---|---|
| single absolute schemaRef | 2.2, 2.3 | exactly one `link:schemaRef`, absolute `.xsd` |
| no forbidden constructs | 2.1, 2.4, 2.14 | no `xml:base`, `link:linkbaseRef`, `xbrli:segment` |
| context hygiene | 2.7 | no unused or duplicated `xbrli:context` |
| single subject | 2.9 | one entity identifier value |
| period valid | 2.10, 2.13 | instant present, consistent |
| dimensions in scenario | 2.15 | members under `xbrli:scenario` only |
| no duplicate facts | 2.16, 2.16.1 | S-Equal element + C-Equal context ⇒ duplicate; no multi-unit set |
| decimals not precision | 2.17, 2.18 | `@decimals` present, no `@precision` |
| unit hygiene | 2.21, 2.22 | no duplicate/unused units |
| short ids | 2.6 | `@id` limited to necessary chars (our `c1`,`u…` non-semantic ids) |
| software info | 2.26 | generating-software processing instruction present |
| positive filing indicator | 1.6 | reported templates have a positive `find:filingIndicator` |

Pre-generation fact checks (resolution, datatype, percentage-ratio, duplicate
datapoint, open-table) are **format-agnostic and unchanged**.

---

## 10. Determinism

Same as CSV: fixed zip entry timestamps; entries in sorted order; **sorted
contexts, units, facts**; canonical short non-semantic ids assigned in first-seen
sorted order (`c1, c2, …`, `uEUR, uPURE`); creation timestamp is a run input; the
software PI is a fixed literal. "Byte-identical" = run-to-run stable, not
identical to EBA's sample whitespace.

---

## 11. Step 3 — proof (COREP LCR through Arelle)

The recipe (§1–§7) was derived and reconstruction-verified on the Pillar 3
IRRBBDIS sample. Step 3 closes the stated COREP gap by putting a generated COREP
LCR instance through the same Arelle oracle that caught the three CSV bugs. This
is pinned as `tests/validation/test_formula_guard_xml.py` (the XML twin of the
CSV `test_formula_guard.py`).

**Setup.** C_72.00.a + C_76.00.a/b of `COREP_LCR_DA` against the real EBA 4.2
DPM + taxonomy package; every closed cell filed with value `0`; the instance
generated the app's way (`build_xml_instance` + the real `_make_xml_resolver`
combining `resolve` with `xml_signature`, real filing-indicator collapse), then
the bare `.xbrl` loaded into Arelle via `--file` (no `--reportPackage`).

**Result — it binds.**

- 182 closed C_72/C_76 cells; **175 produced an XML signature**, 169 facts after
  scenario de-duplication.
- Arelle: **loaded, `unknownPropertyGroup = 0`**, 330 assertions loaded,
  **52 assertions evaluated** against generated facts (51 satisfied; one
  `v7596_m` unsatisfied — `{C_76.00.a,r0030,c0010} >= 1` fails because we filed
  `0`, i.e. the rule *bound to our fact and fired*, which is the point).

**Versioned-metric-namespace question — resolved by real data.** A real COREP
metric goes through as `eba_met:qCBB` in the **un-versioned** metric namespace
`http://www.eba.europa.eu/xbrl/crr/dict/met`; the **dimensions** carry the
release version — `eba_dim_4.0:qCAA = eba_qAI:qx2017`, etc. Arelle accepted the
QNames with zero unknown-property-group / unresolved-member errors, confirming
metric = un-versioned, dimension = `eba_dim_{release code}` (§3). No change
needed.

**The 7 unsignable cells** (C_72.00.a r0030/r0485/r0580/r0590 × c0030/c0040)
resolve to a datapoint but carry **no metric property** (`property_id` is null),
so `xml_signature` returns `None` and they are excluded rather than written as
malformed facts — the airtight behaviour, identical to the CSV path's treatment
of unresolvable cells.

**Projection cost (Step-2 condition 1).** Projecting `ItemCategory` + `Context`
alongside the existing tables — parsing `Context.Signature` instead of
materialising the 1.7M-row `ContextComposition` — costs **+4.6 s ingestion
(≈10 s total) and +45 MB (84 → 129 MB)** on the real release; `Context` is
244,993 rows, not 1.7M. The signature lookup reads `Context` by primary key
(`ContextID`) and `ItemCategory` by `(ItemID, StartReleaseID)`, both indexed by
the existing keys. Eager projection is therefore kept (no lazy/on-demand path
needed).

**Operational note.** A snapshot ingested *before* the dimensional projection
was added has a `dpm.sqlite` without `ItemCategory`/`Context`; it must be
re-ingested to gain XML capability. The guard re-projects from the stored
`source.accdb` when it finds a legacy DB, so the proof runs today; the running
app gains it on the next ingestion of the release.
