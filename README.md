# LLM-Based Career Graph Extraction from Latin Inscriptions

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19593861.svg)](https://doi.org/10.5281/zenodo.19593861)

A pipeline for structured extraction of personal career data from Latin inscriptions using large language models (LLMs), with RDF/Linked Data output.

## Overview

This repository contains the code for a pipeline that:

1. Scrapes Latin inscription data from EDCS via Lat-Epig
2. Extracts structured career information (persons, offices, benefactions) using Claude (Anthropic)
3. Validates and normalizes the extracted JSON against a controlled schema
4. Converts the validated data to RDF/Turtle using a custom ontology (`epig:`)

## Repository Structure

| Path | Description |
|------|-------------|
| `pipeline/` | Core pipeline scripts and ontology |
| `pipeline/batch_extract_career_graphs.py` | LLM-based structured extraction |
| `pipeline/batch_scrape_new_edcs.py` | EDCS scraper via Lat-Epig |
| `pipeline/validation/validate_career_graphs.py` | JSON schema validation |
| `pipeline/validation/fix_and_export.py` | Schema normalization and export |
| `pipeline/create_rdf.py` | RDF/Turtle conversion |
| `pipeline/epig_ontology.ttl` | Custom ontology definition |
| `extract_career_graph.py` | Single-inscription extraction utility |
| `pipeline/place_pleiades_mapping.json` | Place → Pleiades ID mapping |
| `prompt_sample.json` | Example LLM prompt |
| `schema_properties.xlsx` | JSON schema property reference |
| `pipeline.mmd` | Pipeline diagram (Mermaid) |

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

# Convert to RDF
python pipeline/create_rdf.py
```

## Data Availability

The full dataset (validated career graphs and RDF output) is available on Zenodo:

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19593861.svg)](https://doi.org/10.5281/zenodo.19593861)

## License

Code: MIT License  
Data: CC BY 4.0

## Citation

If you use this code or data, please cite:

```bibtex
@misc{jsik2026,
  author    = {Gawa, Junjun},
  title     = {LLM-Based Career Graph Extraction from Latin Inscriptions},
  year      = {2026},
  doi       = {10.5281/zenodo.19593861},
  url       = {https://doi.org/10.5281/zenodo.19593861}
}
```
