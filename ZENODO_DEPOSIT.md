# Zenodo deposit — SARAI framework

Status: **files ready, not yet deposited.**

## What gets deposited

| Item | Value |
| --- | --- |
| Repository | `github.com/WganMe/sarai-framework` (currently **private**) |
| Upload type | `software` — **not** `journal article`: Zenodo cannot describe both in one record |
| Licence | CC BY 4.0 (code only; the five datasets keep their upstream licences) |
| Version | `v1.0.0` |
| Payload | `git archive HEAD` → tracked files only |
| Metadata | `.zenodo.json` (validated) and `CITATION.cff` |
| Datasets | **Not** in this deposit — the 371 MB lives in the GitHub release `datasets-v1`. Record that fact in the description, which it already does. |

## Route: API, not the GitHub integration

The GitHub→Zenodo integration mints a DOI but **requires the repository to be
public**. The repository is private until the manuscript is accepted, so use the
API with the token in `IEEETC/.env` (`ZENODO_TOKEN`, 60 chars, scope
`deposit:write`). The two routes produce the same DOI.

## Sequence

1. **Build the payload from tracked files only.**

   ```bash
   git archive --format=tar.gz --prefix=sarai-framework-1.0.0/ \
       -o /tmp/sarai-framework-1.0.0.tar.gz HEAD
   ```

   `git archive` includes only tracked files, so the downloaded bundle and the
   derived `raw_tables/` are excluded by construction rather than by remembering.

   > **Verify, do not trust.** Whether `git archive` expands the Git-LFS files to
   > real content or emits 134-byte **pointers depends on the local LFS
   > configuration**. Measured on this machine: with LFS's filters present it
   > expands (archive 143 MB, `creditcard.csv` = 150,828,752 bytes); with
   > `filter.lfs.process` cleared it emits pointers (archive 145 KB,
   > `creditcard.csv` = 134 bytes). A depositor built from pointers is *not*
   > self-contained. So check explicitly:

   ```bash
   tar -xzOf /tmp/sarai-framework-1.0.0.tar.gz \
       '*/datasets/sources/financial/creditcard.csv' | wc -c
   # must be 150828752, not 134
   ```

   If it reports 134, run `git lfs install` and repeat.

2. **Verify the payload before uploading** (this is where the IEEETC deposit was
   saved from two mistakes — a committed build artefact and a leaked setting):

   ```bash
   tar -tzf /tmp/sarai-framework-1.0.0.tar.gz | grep -E '\.env$|\.git/|raw_tables/|\.tar\.gz$'
   # must print nothing
   ```

   Then scan the extracted tree for the token **by value**, not by filename, and
   confirm no `.git/` is present.

3. **Create the draft** and capture the reserved DOI:

   ```
   POST /api/deposit/depositions        body {}
   → metadata.prereserve_doi.doi
   ```

   Do **not** create a second draft if a later step fails; list
   `GET /api/deposit/depositions` and reuse it.

4. **Attach metadata** from `.zenodo.json`:

   ```
   PUT /api/deposit/depositions/<id>    body {"metadata": {...}}
   ```

5. **Upload the file** to `links.bucket`:

   ```
   PUT <bucket>/sarai-framework-1.0.0.tar.gz
   Content-Type: application/octet-stream     ← a JSON content type gives HTTP 415
   ```

6. **Publish**, then compare the uploaded checksum with the local one.

## Things that bit us last time

- **Uploading needs `Content-Type: application/octet-stream`.** A JSON content
  type returns `415 UNSUPPORTED MEDIA TYPE`.
- **Files are immutable after publish; metadata is not.** So get filenames, links
  and the description right *before* publishing — afterwards only metadata can be
  corrected.
- **DataCite registration lags.** The DOI can 404 at `doi.org` for hours while
  `zenodo.org` and the DOI proxy already resolve. That is registration lag, not
  bad metadata: a control DOI resolves 200 on all five endpoints. Verify with
  `curl -o /dev/null -w "%{http_code}\n" -L https://doi.org/<doi>`.
- **No `related_identifiers` to the GitHub repo while it is private.** A 404 in a
  permanent record is worse than no link. Add it by metadata edit once the
  repository is public — no new version required.
- **A guard should measure substance, not phrasing.** Two checks of mine failed on
  correct input by demanding my own wording. Test for *an addressable identifier*
  rather than a particular sentence.

## After the manuscript is accepted

1. Make `github.com/WganMe/sarai-framework` public.
2. Add `related_identifiers` pointing at the repository URL, and at the
   manuscript's DOI once it exists.
3. Tag the repository `v1.0.0` so the archived version string matches the tag.
4. Add the badge and the DOI to `README.md`, `CITATION.cff` and
   `REPRODUCIBILITY.md`.

## Open question for the author

The four creators are taken from the **submitted** Results in Engineering title
page (`ipm-titlepage.tex`), which is the authoritative record: Alnahari,
Arbaaeen, Hasanin, Jambi — each with an ORCID. The uploaded package in
`RINENG-D-26-13670/` is named `rineng-titlepage-3authors.docx`, and the R2 cover
letter is addressed only to Reviewers 2 and 3. Confirm whether all four are
creators of the *software* artefact, since a depositor list cannot be changed
after publish without minting a new version.
