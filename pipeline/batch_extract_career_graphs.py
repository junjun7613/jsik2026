#!/usr/bin/env python3
"""
Batch process career graph extraction for all places in scraped_data.

This script:
1. Finds all JSON files in Lat-Epig-main/scraped_data/[place_name]/*.json
2. For each place, checks if career graph data exists in root career_graphs/claude/[place_name]/*.json
3. If existing career data is found (by EDCS-ID), copies it to the new output location
4. If no existing data is found, extracts career graph using LLM
5. Saves output to Lat-Epig-main/career_graphs/[place_name]/*.json

Usage:
    python batch_extract_career_graphs.py --model claude [--limit 10]
    python batch_extract_career_graphs.py --model claude --places "Place1,Place2"
"""

import json
import os
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from anthropic import Anthropic
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

# .envファイルから環境変数を読み込む
load_dotenv()

# Get script directory and project root
SCRIPT_DIR = Path(__file__).parent
SCRAPED_DATA_DIR = SCRIPT_DIR / 'scraped_data'
OUTPUT_DIR = SCRIPT_DIR / 'career_graphs'
EXISTING_CAREER_DIR = SCRIPT_DIR / 'career_graphs' / 'claude'

# Import extraction functions from extract_career_graph.py (same directory)
sys.path.insert(0, str(SCRIPT_DIR))
from extract_career_graph import extract_person_and_career, call_llm, roman_emperors


def find_existing_career_data(edcs_id):
    """
    Check if career data exists for this EDCS-ID in root career_graphs/claude/*/*.json
    Searches across ALL place folders since folder names may differ between old and new data

    Parameters:
    -----------
    edcs_id : str
        EDCS-ID to search for

    Returns:
    --------
    dict or None
        Career data if found, None otherwise
    """
    # Search in ALL subdirectories of career_graphs/claude/
    if not EXISTING_CAREER_DIR.exists():
        return None

    # Get all place directories
    for place_dir in EXISTING_CAREER_DIR.iterdir():
        if not place_dir.is_dir():
            continue

        # Search all JSON files in the place directory
        for json_file in place_dir.glob('*.json'):
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # If the file is an array of career entries
                if isinstance(data, list):
                    for entry in data:
                        if entry.get('edcs_id') == edcs_id:
                            return entry
                # If the file is a single career entry
                elif isinstance(data, dict):
                    if data.get('edcs_id') == edcs_id:
                        return data
            except (json.JSONDecodeError, IOError) as e:
                # Silently skip files that can't be read
                continue

    return None


def load_inscriptions_from_json(json_file):
    """
    Load inscription data from JSON file

    Parameters:
    -----------
    json_file : Path
        Path to JSON file

    Returns:
    --------
    list
        List of inscription dictionaries
    """
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if isinstance(data, list):
            return data
        else:
            return [data]
    except (json.JSONDecodeError, IOError) as e:
        print(f"  Error reading {json_file}: {e}")
        return []


def process_place(place_name, place_dir, output_base_dir, client, model_type, limit=None):
    """
    Process all inscriptions for a single place

    Parameters:
    -----------
    place_name : str
        Name of the place
    place_dir : Path
        Path to place directory in scraped_data
    output_base_dir : Path
        Base output directory for career graphs
    client : object
        API client for LLM
    model_type : str
        Model type ('claude', 'gemini', 'gpt')
    limit : int, optional
        Maximum number of inscriptions to process per place

    Returns:
    --------
    dict
        Statistics about processing (processed, copied, extracted, errors)
    """
    stats = {
        'place': place_name,
        'total': 0,
        'processed': 0,
        'copied_from_existing': 0,
        'extracted_new': 0,
        'errors': 0,
        'skipped': 0
    }

    # Find all JSON files in place directory
    json_files = list(place_dir.glob('*.json'))

    if not json_files:
        print(f"  No JSON files found in {place_dir}")
        return stats

    # Combine all inscriptions from all JSON files
    all_inscriptions = []
    for json_file in json_files:
        inscriptions = load_inscriptions_from_json(json_file)
        all_inscriptions.extend(inscriptions)

    stats['total'] = len(all_inscriptions)

    if stats['total'] == 0:
        print(f"  No inscriptions found")
        return stats

    # Limit processing if specified
    if limit:
        all_inscriptions = all_inscriptions[:limit]
        print(f"  Limited to {limit} inscriptions")

    # Create output directory for this place (with model subdirectory)
    output_dir = output_base_dir / model_type / place_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Output file path
    output_file = output_dir / f"{place_name}_career.json"

    # Load existing output if it exists
    existing_results = []
    processed_ids = set()

    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
                processed_ids = {item.get('edcs_id') for item in existing_results}
                print(f"  Found existing output: {len(processed_ids)} already processed")
        except (json.JSONDecodeError, IOError):
            print(f"  Warning: Could not read existing output file")

    results = existing_results.copy()

    # Process each inscription
    checkpoint_interval = 10

    for i, inscription in enumerate(tqdm(all_inscriptions, desc=f"  {place_name}", leave=False), 1):
        edcs_id = inscription.get('EDCS-ID', 'Unknown')

        # Skip if already processed
        if edcs_id in processed_ids:
            stats['skipped'] += 1
            continue

        # Check if career data exists in root career_graphs (searches all place folders)
        existing_career = find_existing_career_data(edcs_id)

        if existing_career:
            # Copy existing career data
            results.append(existing_career)
            stats['copied_from_existing'] += 1
            stats['processed'] += 1
        else:
            # Extract new career data using LLM
            inscription_text = inscription.get('inscription', '')

            if not inscription_text or inscription_text.strip() == "?":
                # Skip inscriptions with no text
                results.append({
                    "edcs_id": edcs_id,
                    "person_name": "No Text",
                    "person_name_readable": "No Text",
                    "has_career": False,
                    "career_path": [],
                    "notes": "No inscription text",
                    "original_data": inscription
                })
                stats['errors'] += 1
                stats['processed'] += 1
            else:
                try:
                    # Get dating information
                    dating_from = inscription.get('dating_from')
                    dating_to = inscription.get('dating_to')

                    # Extract career using LLM
                    result = extract_person_and_career(
                        inscription_text,
                        edcs_id,
                        client,
                        model_type,
                        dating_from=dating_from,
                        dating_to=dating_to
                    )

                    # Check for errors
                    if 'error' in result:
                        stats['errors'] += 1
                        print(f"    Error processing {edcs_id}: {result.get('notes', 'Unknown error')}")
                    else:
                        result['original_data'] = inscription
                        results.append(result)
                        stats['extracted_new'] += 1
                        stats['processed'] += 1

                except Exception as e:
                    print(f"    Exception processing {edcs_id}: {e}")
                    stats['errors'] += 1

        # Save checkpoint
        if i % checkpoint_interval == 0 or i == len(all_inscriptions):
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

    # Final save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Saved {len(results)} career entries to {output_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Batch extract career graphs from scraped_data"
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='claude',
        choices=['claude', 'gemini', 'gpt'],
        help='LLM model to use (default: claude)'
    )
    parser.add_argument(
        '--api-key', '-k',
        type=str,
        default=None,
        help='API key (if not set, will use environment variable)'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Maximum number of inscriptions to process per place (for testing)'
    )
    parser.add_argument(
        '--places', '-p',
        type=str,
        default=None,
        help='Comma-separated list of place names to process (default: all)'
    )

    args = parser.parse_args()

    # Check API key
    api_key = args.api_key
    if not api_key:
        if args.model == 'claude':
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            env_var_name = 'ANTHROPIC_API_KEY'
        elif args.model == 'gemini':
            api_key = os.environ.get('GEMINI_API_KEY')
            env_var_name = 'GEMINI_API_KEY'
        elif args.model == 'gpt':
            api_key = os.environ.get('OPENAI_API_KEY')
            env_var_name = 'OPENAI_API_KEY'

        if not api_key:
            print(f"Error: {env_var_name} not set")
            print(f"\nSet API key with one of:")
            print(f"1. Environment variable: export {env_var_name}='your-api-key'")
            print(f"2. Command line: python batch_extract_career_graphs.py --model {args.model} --api-key your-api-key")
            sys.exit(1)

    # Initialize API client
    if args.model == 'claude':
        client = Anthropic(api_key=api_key) if api_key else Anthropic()
    elif args.model == 'gemini':
        genai.configure(api_key=api_key)
        client = genai
    elif args.model == 'gpt':
        client = OpenAI(api_key=api_key) if api_key else OpenAI()
    else:
        raise ValueError(f"Unknown model: {args.model}")

    # Check if scraped_data directory exists
    if not SCRAPED_DATA_DIR.exists():
        print(f"Error: scraped_data directory not found at {SCRAPED_DATA_DIR}")
        sys.exit(1)

    # Get list of place directories
    place_dirs = [d for d in SCRAPED_DATA_DIR.iterdir() if d.is_dir()]

    if not place_dirs:
        print(f"No place directories found in {SCRAPED_DATA_DIR}")
        sys.exit(1)

    # Filter places if specified
    if args.places:
        place_names = [p.strip() for p in args.places.split(',')]
        place_dirs = [d for d in place_dirs if d.name in place_names]

        if not place_dirs:
            print(f"No matching places found: {args.places}")
            sys.exit(1)

    print("=" * 80)
    print("Batch Career Graph Extraction")
    print("=" * 80)
    print(f"Model: {args.model}")
    print(f"Scraped data directory: {SCRAPED_DATA_DIR}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Existing career data: {EXISTING_CAREER_DIR}")
    print(f"Places to process: {len(place_dirs)}")
    if args.limit:
        print(f"Limit per place: {args.limit} inscriptions")
    print()

    # Process each place
    all_stats = []

    for place_dir in tqdm(place_dirs, desc="Processing places"):
        place_name = place_dir.name

        print(f"\n[{place_name}]")

        try:
            stats = process_place(
                place_name,
                place_dir,
                OUTPUT_DIR,
                client,
                args.model,
                limit=args.limit
            )
            all_stats.append(stats)
        except Exception as e:
            print(f"  Error processing {place_name}: {e}")
            all_stats.append({
                'place': place_name,
                'total': 0,
                'processed': 0,
                'copied_from_existing': 0,
                'extracted_new': 0,
                'errors': 1,
                'skipped': 0
            })

    # Print summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    total_inscriptions = sum(s['total'] for s in all_stats)
    total_processed = sum(s['processed'] for s in all_stats)
    total_copied = sum(s['copied_from_existing'] for s in all_stats)
    total_extracted = sum(s['extracted_new'] for s in all_stats)
    total_errors = sum(s['errors'] for s in all_stats)
    total_skipped = sum(s['skipped'] for s in all_stats)

    print(f"Places processed: {len(all_stats)}")
    print(f"Total inscriptions: {total_inscriptions}")
    print(f"Processed: {total_processed}")
    print(f"  - Copied from existing: {total_copied}")
    print(f"  - Extracted new: {total_extracted}")
    print(f"Skipped (already done): {total_skipped}")
    print(f"Errors: {total_errors}")
    print()

    # Show top places by inscription count
    sorted_stats = sorted(all_stats, key=lambda x: x['total'], reverse=True)
    print("Top 10 places by inscription count:")
    print("-" * 80)
    for i, stat in enumerate(sorted_stats[:10], 1):
        print(f"{i:2d}. {stat['place']:<40} {stat['total']:>6} inscriptions "
              f"(copied: {stat['copied_from_existing']}, new: {stat['extracted_new']}, errors: {stat['errors']})")

    print("=" * 80)


if __name__ == "__main__":
    main()
