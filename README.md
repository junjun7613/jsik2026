# LLM-Based Career Graph Extraction from Latin Inscriptions

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19593860.svg)](https://doi.org/10.5281/zenodo.19593860)

A pipeline for structured extraction of personal career data from Latin inscriptions using large language models (LLMs), with RDF/Linked Data output.

## Overview

This repository contains the code for a pipeline that:

1. Scrapes Latin inscription data from EDCS via Lat-Epig
2. Extracts structured career information (persons, offices, benefactions) using Claude (Anthropic)
3. Validates and normalizes the extracted JSON against a controlled schema
4. Converts the validated data to RDF/Turtle using a custom ontology (`epig:`)
5. Evaluates extraction accuracy against external authority databases (EDH)

## Repository Structure

| Path | Description |
|------|-------------|
| `pipeline/` | Core pipeline scripts |
| `pipeline/batch_extract_career_graphs.py` | LLM-based structured extraction |
| `pipeline/batch_scrape_new_edcs.py` | EDCS scraper via Lat-Epig |
| `pipeline/extract_career_graph.py` | Single-inscription extraction utility |
| `pipeline/prompt_template.py` | Extraction prompt shared by the above |
| `pipeline/validation/validate_career_graphs.py` | JSON schema validation |
| `pipeline/validation/fix_and_export.py` | Schema normalization and export |
| `pipeline/evaluation/` | Accuracy evaluation against external databases |
| `pipeline/place_pleiades_mapping.json` | Place → Pleiades ID mapping |
| `docs/` | GitHub Pages viewers for the evaluation results |
| `prompt_sample.json` | Example LLM prompt |
| `pipeline.mmd` | Pipeline diagram (Mermaid) |

## Evaluation

Extraction accuracy is measured against external authority data:

| Path | Evaluated against | Target |
|------|-------------------|--------|
| `pipeline/evaluation/name_components/` | EDH (Epigraphic Database Heidelberg) | praenomen / nomen / cognomen / gender |
| `pipeline/evaluation/status_components/` | EDH | social status labels |

Each directory contains a `WORKFLOW.md` describing the procedure. Results can be
browsed at https://junjun7613.github.io/jsik2026/evaluation/

## Data Model

The extracted data covers the following entity types:

| Entity | Key Properties |
|--------|---------------|
| Inscription | EDCS ID, text, date, material, place |
| Person | Name, status, gender, ethnicity, career path, benefactions |
| Career Position | Title, rank, location, date |
| Benefaction | Type, recipient, amount |
| Community | Name, type |

## Ontology Design

The pipeline uses a custom `epig:` namespace alongside standard vocabularies:

- `epig:PersonReference` — a person as attested in a single inscription (not a real-world entity)
- `epig:Inscription`, `epig:CareerPosition`, `epig:Benefaction`, `epig:Community`
- `skos:closeMatch` — for linking persons to Wikidata entries (interpretive correspondence)
- `owl:sameAs` — for linking places to Pleiades (same geographical entity)

## Requirements

```
anthropic
rdflib
openpyxl
requests
beautifulsoup4
```

Install with:

```bash
pip install -r pipeline/requirements.txt
```

## Quick Start

```bash
# Set API key
export ANTHROPIC_API_KEY='your-api-key'

# Extract career graphs for a place
python pipeline/batch_extract_career_graphs.py --places "Dougga_Thugga"

# Validate
python pipeline/validation/validate_career_graphs.py --target modified

# Fix and export
python pipeline/validation/fix_and_export.py
```

RDF conversion is performed by a separate script that is not distributed in this
repository; the resulting RDF graphs are published via Zenodo (see below).

## Data Availability

The full dataset (validated career graphs and RDF output) is available on Zenodo:

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19593860.svg)](https://doi.org/10.5281/zenodo.19593860)

## License

- **Code** (`*.py`): MIT License — see [`LICENSE`](LICENSE)
- **Data** (evaluation datasets, mappings, ontology, viewers): CC BY 4.0 — see [`LICENSE-DATA`](LICENSE-DATA)

Data derived from EDH, EDCS, Trismegistos and Pleiades remain subject to the
terms of those databases; see [`LICENSE-DATA`](LICENSE-DATA) for details.

## Citation

If you use this code or data, please cite:

```bibtex
@misc{jsik2026,
  author    = {Gawa, Junjun},
  title     = {LLM-Based Career Graph Extraction from Latin Inscriptions},
  year      = {2026},
  doi       = {10.5281/zenodo.19593860},
  url       = {https://doi.org/10.5281/zenodo.19593860}
}
```
