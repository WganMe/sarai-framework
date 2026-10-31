# Zenodo deposit — SARAI framework

Status: **published.** v1.1.0 is archived at `10.5281/zenodo.23839423`
(concept DOI `10.5281/zenodo.23839422`), 164,775 bytes, md5
`bf8ed854390f00364fe2a2d8603708a5`. The v1.0.0 record was withdrawn; the
post-mortem below is kept so the same defect is not rebuilt.

The v1.0.0 record (`10.5281/zenodo.23010102`) was deleted on 2026-10-02 and now
resolves to a tombstone (HTTP 410). The reason is recorded in the record history
as a test record, and the payload's own defect is measurable: the uploaded
archive was 152,429 bytes and its `creditcard.csv` member was a 134-byte Git-LFS
pointer. It advertised a self-contained 143 MB payload and delivered none of it.

Do not restore that DOI. Restoring it would restore the empty payload, and the
files of a published record are immutable.

## What gets deposited

| Item | Value |
| --- | --- |
| Repository | `github.com/WganMe/sarai-framework` (**public**) |
| Upload type | `software` — **not** `journal article`: Zenodo cannot describe both in one record |
| Licence | CC BY 4.0 (code only; the five datasets keep their upstream licences) |
| Version | `v1.1.0` (archived: `10.5281/zenodo.23839423`) |
| Payload | `tools/make_deposit.sh` → tracked files, data paths excluded |
| Metadata | `.zenodo.json` (validated) and `CITATION.cff` |
| Datasets | **Not** in this deposit — the 500 MB lives in the GitHub release `datasets-v1` and is enumerated in `DATA_SOURCES.md`. |

## Route: integration or API

The GitHub→Zenodo integration mints a DOI automatically when a release is
published. Use it if the repository is already connected in the Zenodo settings;
otherwise use the API with the token in `IEEETC/.env` (`ZENODO_TOKEN`, 60 chars,
scope `deposit:write`). Both routes produce a version DOI plus a concept DOI; the
concept DOI is the stable one to quote.

## Sequence

1. **Build the payload with the script, not by hand.**

   ```bash
   tools/make_deposit.sh v1.1.0
   ```

   It archives `HEAD`, refuses to run on a dirty tree, and then *fails* if the
   result contains an LFS pointer, a `.env`, a `.git/` directory or a nested
   archive. Those four checks are the ones that were missing when v1.0.0 was
   uploaded with 134-byte stubs in it.

2. **Inspect the payload before uploading.**

   ```bash
   tar -tzf dist/sarai-framework-1.1.0.tar.gz | head -40
   tar -tzf dist/sarai-framework-1.1.0.tar.gz | grep -cE '^\.env$|/\.git/'
   # must print 0
   ```

   The archive should be a few hundred KB, because the data paths are
   `export-ignore` in `.gitattributes` and `DATA_SOURCES.md` says where the data
   actually is. An archive of several hundred MB means an LFS filter expanded
   files that the deposit does not licence — do not upload either shape without
   reading it.

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
   PUT <bucket>/sarai-framework-1.1.0.tar.gz
   Content-Type: application/octet-stream     ← a JSON content type gives HTTP 415
   ```

6. **Publish**, then compare the uploaded checksum with the local one. Zenodo
   reports an md5; `md5sum dist/sarai-framework-1.1.0.tar.gz` must match it before
   you publish, not after.

7. **Write the DOI back** into `README.md`, `NOTICE.md`, `CITATION.cff`,
   `REPRODUCIBILITY.md`, the GitHub repository description and homepage, and the
   Zenodo `related_identifiers`. A DOI that appears in five places and four of
   them are wrong is how the last record ended up pointing at itself.

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
- **File size is not evidence of content.** The v1.0.0 payload was 152 KB and
  looked plausible for a code-only artefact. It was plausible *because* it was
  wrong: 37 pointers instead of 500 MB of CSVs. Check a member's byte count
  against the number the manifest promises, and check that no file begins with
  `version https://git-lfs.github.com/`.

## After the manuscript is published

The manuscript is published as Results in Engineering 32 (2026) 113508,
`10.1016/j.rineng.2026.113508`. That removes every blocker the old plan listed:

1. ~~Make the repository public.~~ Done; it is public.
2. ~~Add `related_identifiers` to the repository and the manuscript.~~ Both are
   now in `.zenodo.json`.
3. ~~Tag the repository so the version matches.~~ Tag `v1.1.0` must exist and its
   tree must be the one archived.
4. ~~Add the badge and the DOI.~~ The badge goes in once the DOI resolves. The
   manuscript itself does **not** cite a Zenodo DOI — its Code availability and
   Data availability statements name the GitHub URL only — so no erratum is
   needed for that link, and none should be offered.

## Open question for the author

The four creators are taken from the **submitted** Results in Engineering title
page (`ipm-titlepage.tex`), which is the authoritative record: Alnahari,
Arbaaeen, Hasanin, Jambi — each with an ORCID. The uploaded package in
`RINENG-D-26-13670/` is named `rineng-titlepage-3authors.docx`, and the R2 cover
letter is addressed only to Reviewers 2 and 3. Confirm whether all four are
creators of the *software* artefact, since a depositor list cannot be changed
after publish without minting a new version.
