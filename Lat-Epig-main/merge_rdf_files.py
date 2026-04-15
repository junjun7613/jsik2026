#!/usr/bin/env python3
"""
Merge multiple RDF/TTL files into a single file.

This script combines all TTL files from different places within a model directory
into a single consolidated TTL file.

Usage:
    python merge_rdf_files.py --model claude
    python merge_rdf_files.py --model claude --output custom_all.ttl
    python merge_rdf_files.py --model claude --format xml
"""

import argparse
import sys
from pathlib import Path
from rdflib import Graph

def merge_rdf_files(model_dir, output_path, output_format='turtle'):
    """
    Merge all RDF files in a model directory into a single file

    Parameters:
    -----------
    model_dir : Path
        Path to model directory containing place subdirectories with RDF files
    output_path : Path
        Output file path for merged RDF
    output_format : str
        RDF serialization format ('turtle', 'xml', 'n3', 'nt', 'json-ld')

    Returns:
    --------
    tuple
        (number of files merged, total triples)
    """
    # Create combined graph
    combined_graph = Graph()

    # Find all RDF files
    rdf_files = []
    for place_dir in model_dir.iterdir():
        if place_dir.is_dir():
            rdf_files.extend(place_dir.glob('*.ttl'))
            rdf_files.extend(place_dir.glob('*.rdf'))
            rdf_files.extend(place_dir.glob('*.n3'))
            rdf_files.extend(place_dir.glob('*.nt'))
            rdf_files.extend(place_dir.glob('*.jsonld'))

    if not rdf_files:
        print(f"No RDF files found in {model_dir}")
        return 0, 0

    print(f"Found {len(rdf_files)} RDF files to merge")
    print()

    # Merge all files
    files_merged = 0
    for rdf_file in sorted(rdf_files):
        try:
            # Determine format from file extension
            file_format = 'turtle'
            if rdf_file.suffix == '.rdf':
                file_format = 'xml'
            elif rdf_file.suffix == '.n3':
                file_format = 'n3'
            elif rdf_file.suffix == '.nt':
                file_format = 'nt'
            elif rdf_file.suffix == '.jsonld':
                file_format = 'json-ld'

            print(f"  Merging: {rdf_file.parent.name}/{rdf_file.name}")

            # Parse and merge into combined graph
            temp_graph = Graph()
            temp_graph.parse(str(rdf_file), format=file_format)

            # Copy namespace bindings from the first file
            if files_merged == 0:
                for prefix, namespace in temp_graph.namespaces():
                    combined_graph.bind(prefix, namespace)

            # Add all triples to combined graph
            for triple in temp_graph:
                combined_graph.add(triple)

            files_merged += 1

        except Exception as e:
            print(f"  Error parsing {rdf_file.name}: {e}")

    # Get total triples
    total_triples = len(combined_graph)

    print()
    print(f"Total files merged: {files_merged}")
    print(f"Total triples: {total_triples}")
    print()

    # Serialize combined graph
    print(f"Writing merged RDF to {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined_graph.serialize(destination=str(output_path), format=output_format)
    print(f"  ✓ Merged RDF saved to: {output_path}")

    return files_merged, total_triples


def main():
    parser = argparse.ArgumentParser(
        description="Merge multiple RDF/TTL files into a single file"
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        required=True,
        help='Model directory to process (e.g., claude, gemini, gpt)'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        default=None,
        help='Output file path (default: rdf_output/[model]/all.ttl)'
    )
    parser.add_argument(
        '--format', '-f',
        type=str,
        default='turtle',
        choices=['turtle', 'xml', 'n3', 'nt', 'json-ld'],
        help='RDF output format (default: turtle)'
    )

    args = parser.parse_args()

    # Setup paths
    script_dir = Path(__file__).parent
    rdf_output_dir = script_dir / 'rdf_output'
    model_dir = rdf_output_dir / args.model

    # Check if model directory exists
    if not model_dir.exists():
        print(f"Error: Model directory not found: {model_dir}")
        print(f"Please ensure RDF files have been generated for model '{args.model}'")
        return 1

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        # Determine extension from format
        extension = {
            'turtle': '.ttl',
            'xml': '.rdf',
            'n3': '.n3',
            'nt': '.nt',
            'json-ld': '.jsonld'
        }[args.format]

        output_filename = f"all{extension}"
        output_path = model_dir / output_filename

    print("="*80)
    print("RDF File Merger")
    print("="*80)
    print(f"Model: {args.model}")
    print(f"Input directory: {model_dir}")
    print(f"Output file: {output_path}")
    print(f"Output format: {args.format}")
    print()

    # Merge files
    try:
        files_merged, total_triples = merge_rdf_files(
            model_dir,
            output_path,
            args.format
        )

        if files_merged == 0:
            print("\nNo files were merged")
            return 1

        # Show file size
        file_size = output_path.stat().st_size
        if file_size > 1024 * 1024:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        elif file_size > 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size} bytes"

        print()
        print("="*80)
        print("Merge complete!")
        print("="*80)
        print(f"Files merged: {files_merged}")
        print(f"Total triples: {total_triples:,}")
        print(f"Output file: {output_path}")
        print(f"File size: {size_str}")
        print("="*80)

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
