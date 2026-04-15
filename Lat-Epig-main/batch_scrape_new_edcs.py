#!/usr/bin/env python3
"""
Batch scraper for the new EDCS API (https://edcs.hist.uzh.ch)
Reads a list of places and scrapes EDCS data for each place using the new API

Usage:
    python batch_scrape_new_edcs.py --places places.txt
    python batch_scrape_new_edcs.py --places-csv places.csv --csv-column PlaceName
"""

import argparse
import csv
import sys
import os
import json
import requests
from pathlib import Path
from datetime import datetime

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


def read_places_from_txt(filepath):
    """Read place names from a text file (one place per line)"""
    places = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            place = line.strip()
            if place and not place.startswith('#'):
                places.append(place)
    return places


def read_places_from_csv(filepath, column_name='place'):
    """Read place names from a CSV file"""
    places = []
    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if column_name in row and row[column_name]:
                places.append(row[column_name].strip())
    return places


def read_places_from_pleiades_mapping(filepath):
    """
    Read place names from Pleiades mapping JSON file

    Parameters:
    -----------
    filepath : str
        Path to place_pleiades_mapping.json file

    Returns:
    --------
    list
        List of place names (keys from the JSON)
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        mapping = json.load(f)

    # Extract place names (keys)
    places = list(mapping.keys())
    return places


def scrape_place_api(place, base_url="https://edcs.hist.uzh.ch", batch_size=100):
    """
    Scrape EDCS data for a single place using the new API

    Parameters:
    -----------
    place : str
        Place name to search for
    base_url : str
        Base URL for EDCS API
    batch_size : int
        Number of results to fetch per API call

    Returns:
    --------
    list
        List of inscription dictionaries
    """
    api_url = f"{base_url}/api/query"
    inscriptions = []

    # Initial query to get total count
    params = {
        'place': place,
        'start': 0,
        'length': batch_size,
        'draw': 1
    }

    print(f"Querying API for place: {place}")

    try:
        response = requests.get(api_url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        total = data.get('recordsFiltered', 0)
        print(f"  Found {total} inscriptions")

        if total == 0:
            return []

        # Fetch all results in batches
        fetched = 0
        while fetched < total:
            if fetched > 0:
                params['start'] = fetched
                params['draw'] += 1
                response = requests.get(api_url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

            results = data.get('data', [])

            for result in results:
                monument_id = result.get('monument_id')
                obj = result.get('obj', {})

                # Convert API data to TSV format
                inscription_data = convert_api_to_tsv_format(obj)
                inscriptions.append(inscription_data)

            fetched += len(results)
            print(f"  Fetched {fetched}/{total} inscriptions")

            if len(results) == 0:
                break

        return inscriptions

    except requests.exceptions.RequestException as e:
        print(f"  ✗ API Error: {e}")
        return []
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def convert_api_to_tsv_format(obj):
    """
    Convert API response object to TSV format matching the original Lat-Epig output

    Parameters:
    -----------
    obj : dict
        API response object

    Returns:
    --------
    dict
        Dictionary with TSV column names and values
    """
    edcs_id = obj.get('edcs-id', '')

    # Extract publication/citation
    belege = obj.get('belege', [])
    publication = ' | '.join([' '.join(str(x) for x in beleg) for beleg in belege]) if belege else ''

    # Province and place
    province = obj.get('provinz', '')
    place = obj.get('ort', '')

    # Dating
    datierung = obj.get('datierung')
    if datierung and isinstance(datierung, list):
        dating_from = datierung[0] if len(datierung) > 0 and datierung[0] is not None else ''
        dating_to = datierung[1] if len(datierung) > 1 and datierung[1] is not None else ''
    else:
        dating_from = ''
        dating_to = ''

    # Build raw_dating string
    if dating_from and dating_to:
        raw_dating = f"{dating_from} to {dating_to}"
    else:
        raw_dating = ''

    # Status/categories (gattungen)
    gattungen = obj.get('gattungen', [])
    status = ';  '.join(gattungen) if gattungen else ''

    # Inscriptions - the API returns a list of inscription variants
    inschriften = obj.get('inschriften', [])
    inscription = ''
    inscription_conservative_cleaning = ''
    inscription_interpretive_cleaning = ''
    language = ''

    if inschriften and len(inschriften) > 0:
        # Take the first inscription variant
        inschrift_data = inschriften[0]

        # Inscription text (index 0)
        inscription = inschrift_data[0] if len(inschrift_data) > 0 else ''

        # Language (index 2)
        langs = inschrift_data[2] if len(inschrift_data) > 2 else []
        language = ','.join(langs) if langs else ''

        # For cleaning versions, use the inscription text
        # (The old EDCS format had separate cleaned versions,
        # but the new API doesn't provide them explicitly)
        inscription_conservative_cleaning = inscription.replace('[', '').replace(']', '').replace('(', '').replace(')', '')
        inscription_interpretive_cleaning = inscription_conservative_cleaning

    # Material
    material = obj.get('material', '')

    # Coordinates
    coord = obj.get('coord')
    if coord and isinstance(coord, list):
        longitude = coord[0] if len(coord) > 0 and coord[0] is not None else ''
        latitude = coord[1] if len(coord) > 1 and coord[1] is not None else ''
    else:
        longitude = ''
        latitude = ''

    # Photo/images
    bilder = obj.get('bilder', [])
    photo = 'yes' if bilder else ''

    # Partner link (construct from EDCS ID)
    partner_link = f"https://edcs.hist.uzh.ch/inscription/{edcs_id.replace('EDCS-', '')}" if edcs_id else ''

    return {
        'EDCS-ID': edcs_id,
        'publication': publication,
        'province': province,
        'place': place,
        'dating_from': dating_from,
        'dating_to': dating_to,
        'date_not_before': dating_from,
        'date_not_after': dating_to,
        'status': status,
        'inscription': inscription,
        'inscription_conservative_cleaning': inscription_conservative_cleaning,
        'inscription_interpretive_cleaning': inscription_interpretive_cleaning,
        'material': material,
        'comment': '',
        'latitude': latitude,
        'longitude': longitude,
        'language': language,
        'photo': photo,
        'partner_link': partner_link,
        'extra_text': '',
        'extra_html': '',
        'raw_dating': raw_dating
    }


def generate_folder_name(place_name):
    """
    Generate a clean folder name from place name
    Keeps the full place name, replacing special characters with safe ones

    Parameters:
    -----------
    place_name : str
        Original place name (e.g., "Oudna, Hr. / Udhnah / Uthina")

    Returns:
    --------
    str
        Clean folder name (e.g., "Oudna_Hr_Udhnah_Uthina")
    """
    # Replace slashes with underscores
    folder_name = place_name.replace('/', '_')

    # Replace commas with underscores
    folder_name = folder_name.replace(',', '_')

    # Replace spaces with underscores
    folder_name = folder_name.replace(' ', '_')

    # Remove dots
    folder_name = folder_name.replace('.', '')

    # Remove other special characters, keep only alphanumeric and underscores
    folder_name = ''.join(c for c in folder_name if c.isalnum() or c == '_')

    # Remove consecutive underscores
    while '__' in folder_name:
        folder_name = folder_name.replace('__', '_')

    # Remove leading/trailing underscores
    folder_name = folder_name.strip('_')

    return folder_name


def save_to_tsv(inscriptions, place_name, output_filename):
    """
    Save inscriptions to TSV file in scraped_data/[place]/ directory

    Parameters:
    -----------
    inscriptions : list
        List of inscription dictionaries
    place_name : str
        Original place name
    output_filename : str
        TSV filename

    Returns:
    --------
    str
        Full path to saved TSV file
    """
    if not inscriptions:
        print(f"  No data to save")
        return None

    # Generate folder name from place name
    folder_name = generate_folder_name(place_name)

    # Get the script's directory (Lat-Epig-main)
    script_dir = Path(__file__).parent

    # Create directory structure: Lat-Epig-main/scraped_data/[place]/
    output_dir = script_dir / 'scraped_data' / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / output_filename

    # TSV column headers (matching original Lat-Epig format)
    headers = [
        'EDCS-ID', 'publication', 'province', 'place', 'dating_from', 'dating_to',
        'date_not_before', 'date_not_after', 'status', 'inscription',
        'inscription_conservative_cleaning', 'inscription_interpretive_cleaning',
        'material', 'comment', 'latitude', 'longitude', 'language', 'photo',
        'partner_link', 'extra_text', 'extra_html', 'raw_dating'
    ]

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, delimiter='\t')
        writer.writeheader()
        writer.writerows(inscriptions)

    print(f"  ✓ Saved TSV to: {output_path}")
    return str(output_path)


def convert_tsv_to_json_format(tsv_path):
    """
    Convert TSV to JSON following convert_tsv_to_json.py format

    Parameters:
    -----------
    tsv_path : str
        Path to TSV file

    Returns:
    --------
    str
        Path to created JSON file, or None if conversion failed
    """
    if not PANDAS_AVAILABLE:
        print("  Warning: pandas not available, skipping JSON conversion")
        print("  Install pandas with: pip install pandas")
        return None

    try:
        # Read TSV file
        import pandas as pd
        df = pd.read_csv(tsv_path, sep='\t')

        # Convert NaN to empty strings
        df_clean = df.fillna('')
        inscriptions = df_clean.to_dict('records')

        # Convert status field to list (split by semicolon)
        for item in inscriptions:
            if item.get('status'):
                # Split by ; and clean up spaces
                status_list = [s.strip() for s in item['status'].split(';') if s.strip()]
                item['status'] = status_list
            else:
                item['status'] = []

        # Generate output path in same directory as TSV
        json_path = tsv_path.replace('.tsv', '.json')

        # Save JSON
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(inscriptions, f, ensure_ascii=False, indent=2)

        print(f"  ✓ Saved JSON to: {json_path}")
        return json_path

    except Exception as e:
        print(f"  ✗ Error converting to JSON: {e}")
        return None


def batch_scrape_places(places, resume=False, resume_file=None):
    """
    Scrape EDCS data for a list of places using the new API

    Parameters:
    -----------
    places : list
        List of place names
    resume : bool
        Resume from a previous run
    resume_file : str
        File to track progress

    Returns:
    --------
    dict
        Dictionary mapping place names to output filenames
    """
    results = {}
    skipped = []

    # Load resume information if available
    if resume and resume_file and os.path.exists(resume_file):
        print(f"Resume mode: Loading progress from {resume_file}")
        with open(resume_file, 'r', encoding='utf-8') as f:
            for line in f:
                place = line.strip()
                if place:
                    skipped.append(place)
        print(f"Found {len(skipped)} already processed places\n")

    # Create resume file if needed
    if resume and resume_file:
        resume_f = open(resume_file, 'a', encoding='utf-8')
    else:
        resume_f = None

    total = len(places)
    processed = 0
    errors = 0

    # Use tqdm if available, otherwise use simple iteration
    if TQDM_AVAILABLE:
        places_iterator = tqdm(enumerate(places, 1), total=len(places),
                               desc="Processing places", unit="place",
                               bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]')
    else:
        places_iterator = enumerate(places, 1)

    for i, place in places_iterator:
        # Skip if already processed
        if place in skipped:
            if TQDM_AVAILABLE:
                tqdm.write(f"[{i}/{total}] Skipping {place} (already processed)")
            else:
                print(f"[{i}/{total}] Skipping {place} (already processed)")
            continue

        if TQDM_AVAILABLE:
            tqdm.write(f"\n[{i}/{total}] Processing: {place}")
            tqdm.write("=" * 80)
        else:
            print(f"\n[{i}/{total}] Processing: {place}")
            print("=" * 80)

        inscriptions = scrape_place_api(place)

        if inscriptions:
            # Create output filename
            timestamp = datetime.now().strftime('%Y-%m-%d')
            # Extract simpler place name for filename (take last part after /)
            simple_place = place.split('/')[-1].strip()
            safe_place = simple_place.replace(' ', '_').replace(',', '').replace('.', '')[:50]
            output_file = f"{timestamp}-EDCS_via_Lat_Epig-place_{safe_place}-{len(inscriptions)}.tsv"

            # Save TSV to filtered_data/[place]/ directory
            tsv_path = save_to_tsv(inscriptions, place, output_file)

            if tsv_path:
                results[place] = tsv_path
                processed += 1

                # Convert TSV to JSON using convert_tsv_to_json.py format
                json_path = convert_tsv_to_json_format(tsv_path)

                # Record progress
                if resume_f:
                    resume_f.write(f"{place}\n")
                    resume_f.flush()
        else:
            errors += 1

    if resume_f:
        resume_f.close()

    # Print summary
    print(f"\n{'=' * 80}")
    print("Batch scraping complete")
    print(f"{'=' * 80}")
    print(f"Total places: {total}")
    print(f"Successfully processed: {processed}")
    print(f"Skipped (already done): {len(skipped)}")
    print(f"Errors: {errors}")
    print(f"{'=' * 80}")

    return results


def main():
    parser = argparse.ArgumentParser(
        description='Batch scrape EDCS data for multiple places using the new EDCS API'
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--places', type=str,
                             help='Text file with place names (one per line)')
    input_group.add_argument('--places-csv', type=str,
                             help='CSV file with place names')
    input_group.add_argument('--province-csv', type=str,
                             help='CSV file from place_list directory (generated by extract_places_from_province.py)')
    input_group.add_argument('--pleiades-mapping', type=str,
                             help='JSON file with Pleiades mapping (place_pleiades_mapping.json)')

    parser.add_argument('--csv-column', type=str, default='place',
                        help='Column name in CSV containing place names (default: place, use "place_name" for province CSV files)')

    # Resume functionality
    parser.add_argument('--resume', action='store_true',
                        help='Resume from previous run, skipping already processed places')
    parser.add_argument('--resume-file', type=str, default='batch_scrape_progress_new.txt',
                        help='File to track progress (default: batch_scrape_progress_new.txt)')

    args = parser.parse_args()

    # Read places
    if args.places:
        print(f"Reading places from: {args.places}")
        places = read_places_from_txt(args.places)
    elif args.places_csv:
        print(f"Reading places from CSV: {args.places_csv}")
        places = read_places_from_csv(args.places_csv, args.csv_column)
    elif args.province_csv:
        # Read from place_list directory with default column name "place_name"
        csv_path = Path(__file__).parent / 'place_list' / args.province_csv
        print(f"Reading places from province CSV: {csv_path}")
        if not csv_path.exists():
            print(f"Error: File not found: {csv_path}")
            sys.exit(1)
        places = read_places_from_csv(str(csv_path), 'place_name')
    elif args.pleiades_mapping:
        print(f"Reading places from Pleiades mapping: {args.pleiades_mapping}")
        places = read_places_from_pleiades_mapping(args.pleiades_mapping)
    else:
        print("Error: No input file specified")
        sys.exit(1)

    print(f"Found {len(places)} places to process\n")

    if not places:
        print("Error: No places found in input file")
        sys.exit(1)

    # Batch scrape
    results = batch_scrape_places(
        places,
        resume=args.resume,
        resume_file=args.resume_file if args.resume else None
    )

    print(f"\nSuccessfully scraped {len(results)} places")


if __name__ == "__main__":
    main()
