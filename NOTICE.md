# Licence scope and attribution

The licence for this repository is **Creative Commons Attribution 4.0
International (CC BY 4.0)**, held in [`LICENSE`](LICENSE). That file is the
verbatim legal code and nothing else, so that licence detection tools recognise
it. This file explains what the licence covers here, and what it does not.

## Covered

Everything produced by this work: the framework code under `framework/`, the
verification and assertion tools under `tools/`, the manifests
(`docker-compose.yml`, `reproduce.sh`), the metadata under `datasets/metadata/`,
and the documentation.

Under CC BY 4.0 you may share and adapt all of the above, **including
commercially**, provided you give appropriate credit, link to the licence, and
indicate whether changes were made.

## Source data licences

The five public datasets this work federates over are **not** redistributed
under the licence above. They are fetched separately and keep their own terms:

| Domain | Source | Licence |
| --- | --- | --- |
| E-Commerce | Kaggle `olistbr/brazilian-ecommerce` | CC BY-NC-SA 4.0 |
| Healthcare | Kaggle `prasad22/healthcare-dataset` | CC0-1.0 |
| Retail | UCI dataset 352 `online+retail` | CC BY 4.0 |
| Financial | Kaggle `mlg-ulb/creditcardfraud` | DbCL-1.0 |
| Supply Chain | Kaggle `shashwatwork/dataco-smart-supply-chain-for-big-data-analysis` | CC BY-NC-SA 4.0 |

Note the two non-commercial sources: this repository's CC BY 4.0 licence applies
to the code, not to those datasets.

## Third-party components the deployment uses

PrestoDB, PostgreSQL, MariaDB, Ollama and the dashboard platform are separate
projects under their own licences and are not distributed here; they are pulled
as container images or installed separately.

## A note on why CC BY and not a software licence

The content here is mixed: Python tooling, YAML manifests, JSON metadata and
documentation. Creative Commons and the Free Software Foundation both observe
that CC licences are written for content rather than for source code, and a
software licence (MIT, Apache-2.0) would be the conventional choice for
`framework/` and `tools/`.

CC BY 4.0 was chosen deliberately for two reasons:

1. **It is not `-NC`.** A NonCommercial clause would forbid commercial
   laboratories from running the verification suite to check the paper's
   results, which contradicts the paper's own claim that every number is
   reproducible from this repository.
2. **It covers the mixed content uniformly.** A single licence over the code,
   the manifests and the documentation avoids a per-path split.

If you want to reuse *only* the code under a software licence instead, open an
issue and a per-directory `LICENSE` can be added — dual licensing as CC BY 4.0
**and** MIT is compatible, since both permit sublicensing.

## Citation

If you use the code or the measured outputs, please cite the archived artifact.
The DOI names this exact file set:

> Alnahari, W., Arbaaeen, A., Hasanin, T., and Jambi, S. (2026).
> *SARAI: Sovereignty-Aware Risk Assessment Infrastructure for Reliable Federated
> Business Intelligence* (Version 1.0.0) [Computer software]. Zenodo.
> <https://doi.org/10.5281/zenodo.23010102>

Machine-readable metadata is in [`CITATION.cff`](CITATION.cff). This repository
is the living copy; the archive at that DOI is the immutable version of record,
which is why the verification assertions are quoted against it.
