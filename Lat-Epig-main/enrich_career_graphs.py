#!/usr/bin/env python3
"""
Enrich career graph data with cost conversion and divinity classification.

This script:
1. Reads career graph JSON files from Lat-Epig-main/career_graphs/[model]/[place]/*.json
2. Converts benefaction costs from natural language to numeric values
3. Classifies persons as divinities (gods/goddesses) or humans
4. Saves enriched data to Lat-Epig-main/modified_career_graphs/[model]/[place]/*.json

Usage:
    python enrich_career_graphs.py --model claude [--places "Place1,Place2"]
    python enrich_career_graphs.py --model claude --limit 10
    python enrich_career_graphs.py --model claude --skip-cost  # Skip cost conversion
    python enrich_career_graphs.py --model claude --skip-divinity  # Skip divinity classification
"""

import json
import os
import sys
import argparse
import re
from pathlib import Path
from anthropic import Anthropic
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Get script directory and project root
SCRIPT_DIR = Path(__file__).parent
CAREER_GRAPHS_DIR = SCRIPT_DIR / 'career_graphs'
OUTPUT_DIR = SCRIPT_DIR / 'modified_career_graphs'


def call_claude(prompt, client):
    """
    Call Claude API

    Parameters:
    -----------
    prompt : str
        The prompt
    client : Anthropic
        Anthropic API client

    Returns:
    --------
    str
        Claude's response text
    """
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=512,
        temperature=0,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


def extract_numeric_cost(cost_text, benefaction_text, inscription_text, client):
    """
    Convert cost from natural language to numeric value using LLM

    Parameters:
    -----------
    cost_text : str
        Current cost text (natural language)
    benefaction_text : str
        Benefaction evidence text
    inscription_text : str
        Full inscription text
    client : Anthropic
        Anthropic API client

    Returns:
    --------
    dict
        {
            'cost_numeric': int or None,
            'cost_unit': str or None,
            'reasoning': str
        }
    """

    prompt = f"""You are an expert in Roman epigraphy and ancient Roman monetary systems.

Given the following information from a Roman inscription:
- Cost description: "{cost_text}"
- Benefaction evidence text: "{benefaction_text}"
- Full inscription text: "{inscription_text}"

Please extract the cost as a numeric value in its ORIGINAL currency unit.

IMPORTANT RULES:
1. Extract costs in sesterces (HS, sestertii, sestertius, sestertiis) as numeric value with unit "sesterces"
2. Extract costs in denarii as numeric value with unit "denarii" (DO NOT CONVERT to sesterces)
3. DO NOT convert costs in other currencies (aureus, as, etc.) - return null for those
4. If the cost is per person/per capita, DO NOT calculate total - return null
5. If the amount is unclear or ambiguous, return null
6. Return ONLY a JSON object, no additional text
7. For Roman numerals: L=50, X=10, V=5, I=1, C=100, D=500, M=1000
8. "milia" or "m(ilia)" means "thousand" - multiply the number by 1000

Return your answer as a JSON object with this exact format:
{{
    "cost_numeric": <integer value in original currency, or null>,
    "cost_unit": "sesterces" or "denarii" or null,
    "reasoning": "<brief explanation of your extraction or why it cannot be converted>"
}}

Examples:
- "HS 50000" → {{"cost_numeric": 50000, "cost_unit": "sesterces", "reasoning": "Direct value: 50,000 sesterces"}}
- "HS L milia (50,000 sesterces)" → {{"cost_numeric": 50000, "cost_unit": "sesterces", "reasoning": "L milia = 50 × 1000 = 50,000 sesterces"}}
- "600 denarii" → {{"cost_numeric": 600, "cost_unit": "denarii", "reasoning": "Direct value: 600 denarii"}}
- "denarii terni per person" → {{"cost_numeric": null, "cost_unit": null, "reasoning": "Per person cost - total unknown"}}
- "sumptibus suis" → {{"cost_numeric": null, "cost_unit": null, "reasoning": "No specific amount mentioned"}}
"""

    try:
        response = call_claude(prompt, client)

        # Remove markdown code blocks if present
        response = re.sub(r'^```json\s*\n', '', response, flags=re.MULTILINE)
        response = re.sub(r'\n```\s*$', '', response, flags=re.MULTILINE)
        response = response.strip()

        # Parse JSON response
        result = json.loads(response)

        return {
            'cost_numeric': result.get('cost_numeric'),
            'cost_unit': result.get('cost_unit'),
            'cost_original': cost_text,
            'reasoning': result.get('reasoning', '')
        }
    except Exception as e:
        return {
            'cost_numeric': None,
            'cost_unit': None,
            'cost_original': cost_text,
            'reasoning': f'Error: {str(e)}'
        }


def classify_divinity(person_name, inscription_text, client):
    """
    Classify if a person is a divinity (god/goddess) using LLM

    Parameters:
    -----------
    person_name : str
        The person's name
    inscription_text : str
        The full inscription text
    client : Anthropic
        Anthropic API client

    Returns:
    --------
    dict
        {
            'divinity': bool,
            'divinity_type': str or None,
            'reasoning': str
        }
    """

    prompt = f"""You are an expert in Roman epigraphy and Roman religion.

Given the following information from a Roman inscription:
- Person name: "{person_name}"
- Full inscription text: "{inscription_text}"

Please determine if this person is a DIVINITY (god, goddess, or deified concept) or a HUMAN.

IMPORTANT RULES:
1. Roman/Greek gods and goddesses are divinities (e.g., Iuppiter, Mercurius, Venus, Apollo, Diana, Minerva, etc.)
2. Deified emperors with "divus" or "diva" are divinities (e.g., "Divus Hadrianus")
3. Abstract deified concepts are divinities (e.g., Genius, Fortuna, Victoria, Salus)
4. Epithets like "Augustus/Augusta" attached to deity names indicate divinities (e.g., "Mercurius Augustus", "Iuno Augusta")
5. Regular humans, even with imperial titles like "Augustus", are NOT divinities unless explicitly deified
6. If the name is clearly a deity, return the MAIN deity name without epithets

Return your answer as a JSON object with this exact format:
{{
    "divinity": true or false,
    "divinity_type": "deity name" or null,
    "reasoning": "<brief explanation>"
}}

Examples:
- "Iuppiter Augustus" → {{"divinity": true, "divinity_type": "Iuppiter", "reasoning": "Roman supreme god Jupiter with imperial epithet"}}
- "Mercurius Augustus" → {{"divinity": true, "divinity_type": "Mercurius", "reasoning": "Roman god Mercury with imperial epithet"}}
- "Marcus Aurelius" → {{"divinity": false, "divinity_type": null, "reasoning": "Roman emperor, human"}}
- "Divus Hadrianus" → {{"divinity": true, "divinity_type": "Hadrianus", "reasoning": "Deified emperor"}}
- "Genius coloniae" → {{"divinity": true, "divinity_type": "Genius", "reasoning": "Deified protective spirit"}}

IMPORTANT: Return ONLY the JSON object, no additional text.
"""

    try:
        response = call_claude(prompt, client)

        # Remove markdown code blocks if present
        response = re.sub(r'^```json\s*\n', '', response, flags=re.MULTILINE)
        response = re.sub(r'\n```\s*$', '', response, flags=re.MULTILINE)
        response = response.strip()

        # Parse JSON response
        result = json.loads(response)

        return {
            'divinity': result.get('divinity', False),
            'divinity_type': result.get('divinity_type'),
            'reasoning': result.get('reasoning', '')
        }
    except Exception as e:
        return {
            'divinity': False,
            'divinity_type': None,
            'reasoning': f'Error: {str(e)}'
        }


def enrich_career_graph_file(input_path, output_path, client, skip_cost=False, skip_divinity=False,
                             save_interval=10, force_reprocess=False):
    """
    Enrich a career graph JSON file with cost conversion and divinity classification

    Parameters:
    -----------
    input_path : Path
        Input JSON file path
    output_path : Path
        Output JSON file path
    client : Anthropic
        Anthropic API client
    skip_cost : bool
        Skip cost conversion
    skip_divinity : bool
        Skip divinity classification
    save_interval : int
        Save intermediate results every N inscriptions
    force_reprocess : bool
        Force reprocessing of already processed inscriptions

    Returns:
    --------
    dict
        Statistics about processing
    """
    print(f"  Processing: {input_path.name}")

    # Load input JSON file
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Load existing output file if it exists (for resume functionality)
    existing_data = {}
    processed_edcs_ids = set()

    if output_path.exists() and not force_reprocess:
        print(f"    Found existing output file, loading processed inscriptions...")
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_output = json.load(f)

            # Build a map of EDCS-ID to existing data
            for item in existing_output:
                edcs_id = item.get('edcs_id', 'Unknown')
                existing_data[edcs_id] = item
                processed_edcs_ids.add(edcs_id)

            print(f"    Loaded {len(processed_edcs_ids)} already processed inscriptions")
        except Exception as e:
            print(f"    Warning: Could not load existing output file: {e}")
            existing_data = {}
            processed_edcs_ids = set()

    stats = {
        'total_inscriptions': len(data),
        'skipped_inscriptions': 0,
        'processed_inscriptions': 0,
        'total_persons': 0,
        'total_benefactions': 0,
        'costs_converted': 0,
        'divinities_found': 0,
        'humans_found': 0,
        'errors': 0
    }

    # Note: We don't pre-populate output_data from existing_data here.
    # Instead, we'll process each inscription from input and merge with existing data if available.
    # This ensures the output follows the same order as input.
    output_data = []

    # Process each inscription
    for inscription_idx, inscription in enumerate(tqdm(data, desc=f"    {input_path.stem}", leave=False)):
        edcs_id = inscription.get('edcs_id', 'Unknown')

        # Check if this inscription is fully processed
        # An inscription is considered "fully processed" if:
        # 1. It exists in the output file (by EDCS-ID), AND
        # 2. All persons have divinity fields (if not skip_divinity), AND
        # 3. All benefactions with costs have cost_numeric fields (if not skip_cost)

        is_fully_processed = False
        if edcs_id in processed_edcs_ids and not force_reprocess:
            existing_item = existing_data.get(edcs_id)
            if existing_item:
                # Check if all required fields are present
                fully_enriched = True

                # Check divinity fields
                if not skip_divinity:
                    persons = existing_item.get('persons', [])
                    for person in persons:
                        if 'divinity' not in person:
                            fully_enriched = False
                            break

                # Check cost fields
                if fully_enriched and not skip_cost:
                    persons = existing_item.get('persons', [])
                    for person in persons:
                        benefactions = person.get('benefactions', [])
                        for benef in benefactions:
                            if benef.get('cost', '') and 'cost_numeric' not in benef:
                                fully_enriched = False
                                break
                        if not fully_enriched:
                            break

                is_fully_processed = fully_enriched

        if is_fully_processed:
            stats['skipped_inscriptions'] += 1
            # Use existing processed data
            output_data.append(existing_data[edcs_id])
            continue

        stats['processed_inscriptions'] += 1
        inscription_text = inscription.get('original_data', {}).get('inscription', '')

        # Process persons in 'persons' array
        persons = inscription.get('persons', [])
        for person in persons:
            stats['total_persons'] += 1

            # === DIVINITY CLASSIFICATION ===
            if not skip_divinity and 'divinity' not in person:
                person_name = person.get('person_name', 'Unknown')

                try:
                    result = classify_divinity(person_name, inscription_text, client)

                    # Add fields to person data
                    person['divinity'] = result['divinity']
                    person['divinity_type'] = result['divinity_type']
                    person['divinity_classification_reasoning'] = result['reasoning']

                    if result['divinity']:
                        stats['divinities_found'] += 1
                    else:
                        stats['humans_found'] += 1

                except Exception as e:
                    stats['errors'] += 1
                    person['divinity'] = False
                    person['divinity_type'] = None
                    person['divinity_classification_reasoning'] = f'Error: {str(e)}'
            elif 'divinity' in person:
                # Already processed
                if person.get('divinity'):
                    stats['divinities_found'] += 1
                else:
                    stats['humans_found'] += 1

            # === COST CONVERSION ===
            if not skip_cost:
                benefactions = person.get('benefactions', [])
                for benef in benefactions:
                    cost = benef.get('cost', '')

                    if cost:
                        stats['total_benefactions'] += 1

                        # Skip if already processed
                        if 'cost_numeric' in benef:
                            if benef['cost_numeric'] is not None:
                                stats['costs_converted'] += 1
                            continue

                        benefaction_text = benef.get('benefaction_text', '')

                        try:
                            # Convert cost to numeric
                            result = extract_numeric_cost(
                                cost,
                                benefaction_text,
                                inscription_text,
                                client
                            )

                            # Add fields to benefaction data
                            benef['cost_numeric'] = result['cost_numeric']
                            benef['cost_unit'] = result['cost_unit']
                            benef['cost_original'] = result['cost_original']
                            benef['cost_conversion_reasoning'] = result['reasoning']

                            if result['cost_numeric'] is not None:
                                stats['costs_converted'] += 1

                        except Exception as e:
                            stats['errors'] += 1
                            benef['cost_numeric'] = None
                            benef['cost_unit'] = None
                            benef['cost_original'] = cost
                            benef['cost_conversion_reasoning'] = f'Error: {str(e)}'
            else:
                # When skipping cost conversion, still count existing benefactions for stats
                benefactions = person.get('benefactions', [])
                for benef in benefactions:
                    if benef.get('cost', ''):
                        stats['total_benefactions'] += 1
                        if benef.get('cost_numeric') is not None:
                            stats['costs_converted'] += 1

        # Process persons in 'main_persons' array (if exists)
        main_persons = inscription.get('main_persons', [])
        for person in main_persons:
            # Only process divinity if not already done
            if not skip_divinity and 'divinity' not in person:
                person_name = person.get('person_name', 'Unknown')

                try:
                    result = classify_divinity(person_name, inscription_text, client)

                    person['divinity'] = result['divinity']
                    person['divinity_type'] = result['divinity_type']
                    person['divinity_classification_reasoning'] = result['reasoning']

                except Exception as e:
                    person['divinity'] = False
                    person['divinity_type'] = None
                    person['divinity_classification_reasoning'] = f'Error: {str(e)}'

        # Add processed inscription to output_data
        output_data.append(inscription)
        processed_edcs_ids.add(edcs_id)

        # Intermediate save
        if (stats['processed_inscriptions']) % save_interval == 0:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Final save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Saved to: {output_path}")
    if stats['skipped_inscriptions'] > 0:
        print(f"    Skipped {stats['skipped_inscriptions']} already processed inscriptions")

    return stats


def process_place(place_name, place_dir, output_base_dir, client, model_type,
                  skip_cost=False, skip_divinity=False, limit=None, force_reprocess=False):
    """
    Process all career graph files for a single place

    Parameters:
    -----------
    place_name : str
        Name of the place
    place_dir : Path
        Path to place directory in career_graphs
    output_base_dir : Path
        Base output directory
    client : Anthropic
        Anthropic API client
    model_type : str
        Model type (claude, gemini, gpt)
    skip_cost : bool
        Skip cost conversion
    skip_divinity : bool
        Skip divinity classification
    limit : int, optional
        Maximum number of files to process
    force_reprocess : bool
        Force reprocessing of already processed inscriptions

    Returns:
    --------
    dict
        Statistics about processing
    """
    stats = {
        'place': place_name,
        'files_processed': 0,
        'total_inscriptions': 0,
        'skipped_inscriptions': 0,
        'processed_inscriptions': 0,
        'total_persons': 0,
        'total_benefactions': 0,
        'costs_converted': 0,
        'divinities_found': 0,
        'humans_found': 0,
        'errors': 0
    }

    # Find all JSON files in place directory
    json_files = list(place_dir.glob('*.json'))

    if not json_files:
        print(f"  No JSON files found in {place_dir}")
        return stats

    # Limit files if specified
    if limit:
        json_files = json_files[:limit]

    # Create output directory
    output_dir = output_base_dir / model_type / place_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # Process each JSON file
    for json_file in json_files:
        output_file = output_dir / json_file.name

        try:
            file_stats = enrich_career_graph_file(
                json_file,
                output_file,
                client,
                skip_cost=skip_cost,
                skip_divinity=skip_divinity,
                force_reprocess=force_reprocess
            )

            stats['files_processed'] += 1
            stats['total_inscriptions'] += file_stats['total_inscriptions']
            stats['skipped_inscriptions'] += file_stats['skipped_inscriptions']
            stats['processed_inscriptions'] += file_stats['processed_inscriptions']
            stats['total_persons'] += file_stats['total_persons']
            stats['total_benefactions'] += file_stats['total_benefactions']
            stats['costs_converted'] += file_stats['costs_converted']
            stats['divinities_found'] += file_stats['divinities_found']
            stats['humans_found'] += file_stats['humans_found']
            stats['errors'] += file_stats['errors']

        except Exception as e:
            print(f"  Error processing {json_file.name}: {e}")
            stats['errors'] += 1

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Enrich career graph data with cost conversion and divinity classification"
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='claude',
        choices=['claude', 'gemini', 'gpt'],
        help='Model directory to process (default: claude)'
    )
    parser.add_argument(
        '--places', '-p',
        type=str,
        default=None,
        help='Comma-separated list of place names to process (default: all)'
    )
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=None,
        help='Maximum number of files to process per place (for testing)'
    )
    parser.add_argument(
        '--api-key', '-k',
        type=str,
        default=None,
        help='API key (if not set, will use environment variable)'
    )
    parser.add_argument(
        '--skip-cost',
        action='store_true',
        help='Skip cost conversion'
    )
    parser.add_argument(
        '--skip-divinity',
        action='store_true',
        help='Skip divinity classification'
    )
    parser.add_argument(
        '--force-reprocess',
        action='store_true',
        help='Force reprocessing of already processed inscriptions (by default, skips inscriptions already in output)'
    )

    args = parser.parse_args()

    # Check API key
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("Error: ANTHROPIC_API_KEY not set")
        print("\nSet API key with one of:")
        print("1. Environment variable: export ANTHROPIC_API_KEY='your-api-key'")
        print("2. Command line: python enrich_career_graphs.py --api-key your-api-key")
        sys.exit(1)

    # Initialize API client
    client = Anthropic(api_key=api_key)

    # Check if career_graphs directory exists
    model_dir = CAREER_GRAPHS_DIR / args.model
    if not model_dir.exists():
        print(f"Error: Model directory not found at {model_dir}")
        sys.exit(1)

    # Get list of place directories
    place_dirs = [d for d in model_dir.iterdir() if d.is_dir()]

    if not place_dirs:
        print(f"No place directories found in {model_dir}")
        sys.exit(1)

    # Filter places if specified
    if args.places:
        place_names = [p.strip() for p in args.places.split(',')]
        place_dirs = [d for d in place_dirs if d.name in place_names]

        if not place_dirs:
            print(f"No matching places found: {args.places}")
            sys.exit(1)

    print("=" * 80)
    print("Career Graph Enrichment")
    print("=" * 80)
    print(f"Model: {args.model}")
    print(f"Input directory: {model_dir}")
    print(f"Output directory: {OUTPUT_DIR / args.model}")
    print(f"Places to process: {len(place_dirs)}")
    if args.limit:
        print(f"Limit per place: {args.limit} files")
    if args.skip_cost:
        print("Cost conversion: SKIPPED")
    if args.skip_divinity:
        print("Divinity classification: SKIPPED")
    if args.force_reprocess:
        print("Mode: FORCE REPROCESS (will reprocess all inscriptions)")
    else:
        print("Mode: INCREMENTAL (will skip already processed inscriptions)")
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
                skip_cost=args.skip_cost,
                skip_divinity=args.skip_divinity,
                limit=args.limit,
                force_reprocess=args.force_reprocess
            )
            all_stats.append(stats)
        except Exception as e:
            print(f"  Error processing {place_name}: {e}")
            all_stats.append({
                'place': place_name,
                'files_processed': 0,
                'total_inscriptions': 0,
                'total_persons': 0,
                'total_benefactions': 0,
                'costs_converted': 0,
                'divinities_found': 0,
                'humans_found': 0,
                'errors': 1
            })

    # Print summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    total_files = sum(s['files_processed'] for s in all_stats)
    total_inscriptions = sum(s['total_inscriptions'] for s in all_stats)
    total_skipped = sum(s.get('skipped_inscriptions', 0) for s in all_stats)
    total_processed = sum(s.get('processed_inscriptions', 0) for s in all_stats)
    total_persons = sum(s['total_persons'] for s in all_stats)
    total_benefactions = sum(s['total_benefactions'] for s in all_stats)
    total_costs_converted = sum(s['costs_converted'] for s in all_stats)
    total_divinities = sum(s['divinities_found'] for s in all_stats)
    total_humans = sum(s['humans_found'] for s in all_stats)
    total_errors = sum(s['errors'] for s in all_stats)

    print(f"Places processed: {len(all_stats)}")
    print(f"Files processed: {total_files}")
    print(f"Total inscriptions: {total_inscriptions}")
    if total_skipped > 0:
        print(f"  - Skipped (already processed): {total_skipped}")
        print(f"  - Newly processed: {total_processed}")
    print(f"Total persons: {total_persons}")

    if not args.skip_divinity:
        print(f"  - Divinities: {total_divinities}")
        print(f"  - Humans: {total_humans}")

    if not args.skip_cost:
        print(f"Total benefactions: {total_benefactions}")
        print(f"Costs converted: {total_costs_converted}")
        if total_benefactions > 0:
            print(f"Conversion rate: {total_costs_converted/total_benefactions*100:.1f}%")

    print(f"Errors: {total_errors}")
    print()

    # Show top places
    if not args.skip_divinity:
        sorted_stats = sorted(all_stats, key=lambda x: x['divinities_found'], reverse=True)
        print("Top 10 places by divinity count:")
        print("-" * 80)
        for i, stat in enumerate(sorted_stats[:10], 1):
            print(f"{i:2d}. {stat['place']:<40} "
                  f"Divinities: {stat['divinities_found']:>4}, "
                  f"Humans: {stat['humans_found']:>4}")

    print("=" * 80)


if __name__ == "__main__":
    main()
