# Cognitive Agentic AI Digital Twin for Smart Cities — Data Layer

Companion repository for the DA1 report (`DA1_Report.pdf`). This repo contains
dataset-loading code for the four data modalities used by the proposed
architecture (see Figure 2 of the report):

| Script | Modality | Dataset(s) |
|---|---|---|
| `data/load_traffic.py` | IoT / traffic time series | METR-LA, PeMS-Bay |
| `data/load_flood.py` | Rainfall–inundation time series | Public rainfall-runoff CSVs, with a synthetic fallback generator |
| `data/load_video.py` | CCTV / video anomaly | UCF-Crime, ShanghaiTech (manual download required — see script) |
| `data/load_kg.py` | Urban knowledge graph | OpenStreetMap, via `osmnx` |

## Status

This is the **DA1 milestone**: each script loads/previews its dataset and
returns a standard object (pandas DataFrame, PyG `Data`, or an RDF graph) so
that later milestones (DA2/DA3) can plug in model training directly. No model
training code lives here yet — see the report's §4.4 "Planned experimental
setup" for what's next.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Some scripts need extra one-time setup (API keys, manual downloads, large
file pulls). Each script's docstring says exactly what's required and prints
a clear error if a prerequisite is missing — it will not silently fail.

## Repo layout

```
data/            # one loader script per modality, runnable standalone
notebooks/       # exploratory notebooks (empty for now — add as you go)
docs/            # architecture diagrams copied from the DA1 report
requirements.txt
```

## Team

See the Contribution Matrix in §6 of `DA1_Report.pdf`.
