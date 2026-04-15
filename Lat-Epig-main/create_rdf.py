#!/usr/bin/env python3
"""
Create RDF/TTL from modified career graph data (with divinity classification and cost conversion)

This script converts enriched career graph JSON files to RDF format,
using place name to Pleiades ID mappings from CSV files in place_list directory.

Usage:
    python create_rdf_from_modified.py --model claude --place "Uthina"
    python create_rdf_from_modified.py --model claude --all
    python create_rdf_from_modified.py --model claude --place "Uthina" --output custom_output.ttl
"""

import json
import csv
import os
import argparse
from pathlib import Path
from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, XSD, OWL
from rdflib.namespace import DCTERMS, FOAF, SKOS

def load_pleiades_mapping_from_csv(place_list_dir):
    """
    Load Pleiades ID mappings from all CSV files in place_list directory

    Parameters:
    -----------
    place_list_dir : Path
        Path to place_list directory containing CSV files

    Returns:
    --------
    dict
        Mapping from place_name to Pleiades_ID
    """
    mapping = {}
    csv_files = list(place_list_dir.glob('*.csv'))

    if not csv_files:
        print(f"Warning: No CSV files found in {place_list_dir}")
        return mapping

    print(f"Loading Pleiades mappings from {len(csv_files)} CSV files...")

    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    place_name = row.get('place_name', '').strip()
                    pleiades_id = row.get('Pleiades_ID', '').strip()

                    # Only add if both place_name and Pleiades_ID exist
                    if place_name and pleiades_id:
                        mapping[place_name] = pleiades_id
        except Exception as e:
            print(f"  Warning: Failed to read {csv_file.name}: {e}")

    print(f"  Loaded {len(mapping)} place-to-Pleiades mappings")
    return mapping


def create_rdf_graph(json_path, output_path, pleiades_mapping, format='turtle'):
    """
    Create RDF graph from modified career graph JSON file

    Parameters:
    -----------
    json_path : Path
        Input JSON file path
    output_path : Path
        Output RDF file path
    pleiades_mapping : dict
        Mapping from place_name to Pleiades_ID
    format : str
        RDF serialization format ('turtle', 'xml', 'n3', 'nt', 'json-ld')
    """
    # Define namespaces
    BASE = Namespace("http://example.org/inscription/")
    EPIG = Namespace("http://example.org/epigraphy/")
    PERSON = Namespace("http://example.org/person/")
    CAREER = Namespace("http://example.org/career/")
    REL = Namespace("http://example.org/relationship/")
    STATUS = Namespace("http://example.org/status/")
    BENEF = Namespace("http://example.org/benefaction/")
    PLACE = Namespace("http://example.org/place/")
    PROVINCE = Namespace("http://example.org/province/")
    RELTYPE = Namespace("http://example.org/relationship-type/")
    COMMUNITY = Namespace("http://example.org/community/")
    COMMTYPE = Namespace("http://example.org/community-type/")
    PRAENOMEN = Namespace("http://example.org/praenomen/")
    NOMEN = Namespace("http://example.org/nomen/")
    COGNOMEN = Namespace("http://example.org/cognomen/")
    DIVINITY = Namespace("http://example.org/divinity/")
    COST = Namespace("http://example.org/cost/")

    # Create graph
    g = Graph()
    g.bind("base", BASE)
    g.bind("epig", EPIG)
    g.bind("person", PERSON)
    g.bind("career", CAREER)
    g.bind("rel", REL)
    g.bind("status", STATUS)
    g.bind("benef", BENEF)
    g.bind("place", PLACE)
    g.bind("province", PROVINCE)
    g.bind("reltype", RELTYPE)
    g.bind("community", COMMUNITY)
    g.bind("commtype", COMMTYPE)
    g.bind("praenomen", PRAENOMEN)
    g.bind("nomen", NOMEN)
    g.bind("cognomen", COGNOMEN)
    g.bind("divinity", DIVINITY)
    g.bind("cost", COST)
    g.bind("dcterms", DCTERMS)
    g.bind("foaf", FOAF)
    g.bind("skos", SKOS)

    # Load JSON data
    print(f"Loading JSON data: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"  Loaded {len(data)} inscriptions")

    # Process each inscription
    for item in data:
        edcs_id = item.get('edcs_id', 'Unknown')

        # Create inscription URI
        inscription_uri = BASE[edcs_id]

        # Basic inscription information
        g.add((inscription_uri, RDF.type, EPIG.Inscription))
        g.add((inscription_uri, DCTERMS.identifier, Literal(edcs_id)))

        # Get additional information from original_data
        original_data = item.get('original_data', {})

        if original_data.get('province'):
            province_name = original_data['province']
            province_name_iri = province_name.replace(' ', '_').replace('/', '_')
            province_uri = PROVINCE[province_name_iri]
            g.add((inscription_uri, EPIG.province, province_uri))
            g.add((province_uri, RDF.type, EPIG.Province))
            g.add((province_uri, RDFS.label, Literal(province_name)))

        if original_data.get('place'):
            place_name = original_data['place']
            place_name_iri = place_name.replace(' ', '_').replace('/', '_')
            place_uri = PLACE[place_name_iri]
            g.add((inscription_uri, EPIG.place, place_uri))
            g.add((place_uri, RDF.type, EPIG.Place))
            g.add((place_uri, RDFS.label, Literal(place_name)))

            # Add Pleiades ID if available in mapping
            if place_name in pleiades_mapping:
                pleiades_id = pleiades_mapping[place_name]
                pleiades_uri = URIRef(f"https://pleiades.stoa.org/places/{pleiades_id}")
                g.add((place_uri, OWL.sameAs, pleiades_uri))
                g.add((inscription_uri, EPIG.pleiadesId, Literal(pleiades_id)))

        if original_data.get('dating_from'):
            g.add((inscription_uri, EPIG.datingFrom, Literal(int(original_data['dating_from']), datatype=XSD.integer)))

        if original_data.get('dating_to'):
            g.add((inscription_uri, EPIG.datingTo, Literal(int(original_data['dating_to']), datatype=XSD.integer)))

        if original_data.get('inscription'):
            g.add((inscription_uri, EPIG.text, Literal(original_data['inscription'])))

        if original_data.get('publication'):
            g.add((inscription_uri, DCTERMS.bibliographicCitation, Literal(original_data['publication'])))

        # Process persons
        persons = item.get('persons', [])

        for person_data in persons:
            person_name = person_data.get('person_name', 'Unknown')
            person_id = person_data.get('person_id', 0)

            # Skip Parse Error, Error, No Text
            if person_name in ['Parse Error', 'Error', 'No Text']:
                continue

            # Create person URI
            person_uri = PERSON[f"{edcs_id}_person_{person_id}"]

            # Basic person information
            g.add((person_uri, RDF.type, EPIG.PersonReference))
            g.add((person_uri, FOAF.name, Literal(person_name)))
            g.add((inscription_uri, EPIG.mentions, person_uri))
            g.add((inscription_uri, EPIG.mainSubject, person_uri))

            # === NEW: Divinity classification ===
            divinity = person_data.get('divinity')
            if divinity is not None:
                g.add((person_uri, EPIG.isDivinity, Literal(divinity, datatype=XSD.boolean)))

                if divinity:
                    # This is a divinity
                    g.add((person_uri, RDF.type, EPIG.Divinity))

                    divinity_type = person_data.get('divinity_type')
                    if divinity_type:
                        divinity_type_iri = divinity_type.replace(' ', '_')
                        divinity_uri = DIVINITY[divinity_type_iri]
                        g.add((person_uri, EPIG.divinityType, divinity_uri))
                        g.add((divinity_uri, RDF.type, EPIG.DivinityType))
                        g.add((divinity_uri, RDFS.label, Literal(divinity_type)))

                divinity_reasoning = person_data.get('divinity_classification_reasoning')
                if divinity_reasoning:
                    g.add((person_uri, EPIG.divinityClassificationReasoning, Literal(divinity_reasoning)))

            # Gender
            gender = person_data.get('gender')
            if gender and gender != 'unknown':
                g.add((person_uri, FOAF.gender, Literal(gender)))
                gender_evidence = person_data.get('gender_evidence', '')
                if gender_evidence:
                    g.add((person_uri, EPIG.genderEvidence, Literal(gender_evidence)))

            # Readable name
            person_name_readable = person_data.get('person_name_readable')
            if person_name_readable:
                g.add((person_uri, RDFS.label, Literal(person_name_readable)))

            # Tria nomina
            praenomen = person_data.get('praenomen')
            if praenomen:
                praenomen_iri = praenomen.replace(' ', '_')
                praenomen_uri = PRAENOMEN[praenomen_iri]
                g.add((person_uri, EPIG.praenomen, praenomen_uri))
                g.add((praenomen_uri, RDF.type, EPIG.Praenomen))
                g.add((praenomen_uri, RDFS.label, Literal(praenomen)))

            nomen = person_data.get('nomen')
            if nomen:
                nomen_iri = nomen.replace(' ', '_')
                nomen_uri = NOMEN[nomen_iri]
                g.add((person_uri, EPIG.nomen, nomen_uri))
                g.add((nomen_uri, RDF.type, EPIG.Nomen))
                g.add((nomen_uri, RDFS.label, Literal(nomen)))

            cognomen = person_data.get('cognomen')
            if cognomen:
                cognomen_iri = cognomen.replace(' ', '_')
                cognomen_uri = COGNOMEN[cognomen_iri]
                g.add((person_uri, EPIG.cognomen, cognomen_uri))
                g.add((cognomen_uri, RDF.type, EPIG.Cognomen))
                g.add((cognomen_uri, RDFS.label, Literal(cognomen)))

            # Normalized name and Wikidata link
            person_name_normalized = person_data.get('person_name_normalized')
            if person_name_normalized:
                g.add((person_uri, EPIG.normalizedName, Literal(person_name_normalized)))

            person_name_link = person_data.get('person_name_link')
            if person_name_link:
                wikidata_uri = URIRef(f"http://www.wikidata.org/entity/{person_name_link}")
                g.add((person_uri, EPIG.wikidataEntity, wikidata_uri))
                g.add((person_uri, SKOS.closeMatch, wikidata_uri))

            # Social status
            social_status = person_data.get('social_status')
            if social_status:
                status_iri = social_status.replace(' ', '_')
                status_uri = STATUS[status_iri]
                g.add((person_uri, EPIG.socialStatus, status_uri))
                g.add((status_uri, RDF.type, EPIG.SocialStatus))
                g.add((status_uri, RDFS.label, Literal(social_status)))

            # Ethnicity
            ethnicity = person_data.get('ethnicity', '')
            if ethnicity:
                g.add((person_uri, EPIG.ethnicity, Literal(ethnicity)))
                ethnicity_evidence = person_data.get('ethnicity_evidence', '')
                if ethnicity_evidence:
                    g.add((person_uri, EPIG.ethnicityEvidence, Literal(ethnicity_evidence)))

            # Age at death
            age_at_death = person_data.get('age_at_death', '')
            if age_at_death:
                try:
                    age_int = int(age_at_death)
                    g.add((person_uri, EPIG.ageAtDeath, Literal(age_int, datatype=XSD.integer)))
                except (ValueError, TypeError):
                    # If not convertible to integer, save as string
                    g.add((person_uri, EPIG.ageAtDeath, Literal(age_at_death)))

                age_at_death_evidence = person_data.get('age_at_death_evidence', '')
                if age_at_death_evidence:
                    g.add((person_uri, EPIG.ageAtDeathEvidence, Literal(age_at_death_evidence)))

            # Career path
            has_career = person_data.get('has_career', False)
            if has_career:
                career_path = person_data.get('career_path', [])

                # Sort by order if career items are dictionaries
                if career_path and isinstance(career_path[0], dict):
                    career_path_sorted = sorted(career_path, key=lambda x: x.get('order', 0))
                else:
                    # If career_path is simple strings, convert to dict format
                    career_path_sorted = [{'position': pos, 'order': idx} for idx, pos in enumerate(career_path)]

                previous_career_uri = None

                for career_item in career_path_sorted:
                    if isinstance(career_item, dict):
                        position = career_item.get('position', '')
                        order = career_item.get('order', 0)
                    else:
                        # Fallback for simple string format
                        position = str(career_item)
                        order = career_path_sorted.index(career_item)

                    career_uri = CAREER[f"{edcs_id}_person_{person_id}_career_{order}"]

                    g.add((career_uri, RDF.type, EPIG.CareerPosition))
                    g.add((person_uri, EPIG.hasCareerPosition, career_uri))

                    if position:
                        g.add((career_uri, EPIG.position, Literal(position)))

                    if isinstance(career_item, dict):
                        position_normalized = career_item.get('position_normalized', '')
                        if position_normalized:
                            g.add((career_uri, EPIG.positionNormalized, Literal(position_normalized)))

                        position_abstract = career_item.get('position_abstract', '')
                        if position_abstract:
                            g.add((career_uri, EPIG.positionAbstract, Literal(position_abstract)))

                        position_type = career_item.get('position_type', '')
                        if position_type:
                            g.add((career_uri, EPIG.positionType, Literal(position_type)))

                        position_description = career_item.get('position_description', '')
                        if position_description:
                            g.add((career_uri, DCTERMS.description, Literal(position_description, lang='en')))

                    g.add((career_uri, EPIG.order, Literal(order, datatype=XSD.integer)))

                    # Connect to previous career position (in order)
                    if previous_career_uri is not None:
                        g.add((previous_career_uri, EPIG.nextPosition, career_uri))
                        g.add((career_uri, EPIG.previousPosition, previous_career_uri))

                    previous_career_uri = career_uri

            # Relationships (within person object - simple format)
            relationships = person_data.get('relationships', [])
            for rel_idx, rel in enumerate(relationships):
                rel_uri = REL[f"{edcs_id}_person_{person_id}_rel_{rel_idx}"]
                g.add((person_uri, EPIG.hasRelationship, rel_uri))
                g.add((rel_uri, RDF.type, EPIG.Relationship))

                rel_type = rel.get('relationship_type')
                if rel_type:
                    rel_type_iri = rel_type.replace(' ', '_')
                    rel_type_uri = RELTYPE[rel_type_iri]
                    g.add((rel_uri, EPIG.relationshipType, rel_type_uri))
                    g.add((rel_type_uri, RDF.type, EPIG.RelationshipType))
                    g.add((rel_type_uri, RDFS.label, Literal(rel_type)))

                related_person_name = rel.get('related_person_name')
                if related_person_name:
                    g.add((rel_uri, EPIG.relatedPersonName, Literal(related_person_name)))

                # Additional relationship fields
                rel_property = rel.get('property', '')
                if rel_property:
                    g.add((rel_uri, EPIG.relationshipProperty, Literal(rel_property)))

                property_text = rel.get('property_text', '')
                if property_text:
                    g.add((rel_uri, EPIG.evidence, Literal(property_text)))

                notes = rel.get('notes', '')
                if notes:
                    g.add((rel_uri, RDFS.comment, Literal(notes)))

            # Benefactions
            benefactions = person_data.get('benefactions', [])
            for benef_idx, benef in enumerate(benefactions, 1):
                benef_uri = BENEF[f"{edcs_id}_person_{person_id}_benef_{benef_idx}"]
                g.add((person_uri, EPIG.hasBenefaction, benef_uri))
                g.add((benef_uri, RDF.type, EPIG.Benefaction))
                g.add((inscription_uri, EPIG.mentions, benef_uri))

                benefaction_text = benef.get('benefaction', '')
                if benefaction_text:
                    g.add((benef_uri, RDFS.label, Literal(benefaction_text)))

                benefaction_type = benef.get('benefaction_type')
                if benefaction_type:
                    g.add((benef_uri, EPIG.benefactionType, Literal(benefaction_type)))

                # Object information
                obj = benef.get('object', '')
                if obj:
                    g.add((benef_uri, EPIG.object, Literal(obj)))

                object_type = benef.get('object_type', '')
                if object_type:
                    g.add((benef_uri, EPIG.objectType, Literal(object_type)))

                obj_description = benef.get('object_description', '')
                if obj_description:
                    g.add((benef_uri, DCTERMS.description, Literal(obj_description, lang='en')))

                benefaction_text_evidence = benef.get('benefaction_text', '')
                if benefaction_text_evidence:
                    g.add((benef_uri, EPIG.evidence, Literal(benefaction_text_evidence)))

                # Cost information (original text)
                cost = benef.get('cost')
                if cost:
                    g.add((benef_uri, EPIG.cost, Literal(cost)))

                # Numeric cost (in original currency unit)
                cost_numeric = benef.get('cost_numeric')
                if cost_numeric is not None:
                    try:
                        cost_int = int(cost_numeric)
                        g.add((benef_uri, EPIG.costNumeric, Literal(cost_int, datatype=XSD.integer)))
                    except (ValueError, TypeError):
                        pass

                # Cost unit (sesterces or denarii)
                cost_unit = benef.get('cost_unit', '')
                if cost_unit:
                    g.add((benef_uri, EPIG.costUnit, Literal(cost_unit)))

                cost_original = benef.get('cost_original')
                if cost_original:
                    g.add((benef_uri, EPIG.costOriginalText, Literal(cost_original)))

                cost_reasoning = benef.get('cost_conversion_reasoning')
                if cost_reasoning:
                    g.add((benef_uri, EPIG.costConversionReasoning, Literal(cost_reasoning)))

                # Notes
                benef_notes = benef.get('notes', '')
                if benef_notes:
                    g.add((benef_uri, RDFS.comment, Literal(benef_notes)))

                # Recipient
                recipient_type = benef.get('recipient_type')
                if recipient_type:
                    g.add((benef_uri, EPIG.recipientType, Literal(recipient_type)))

                recipient_name = benef.get('recipient_name')
                if recipient_name:
                    recipient_iri = recipient_name.replace(' ', '_').replace('/', '_')
                    recipient_uri = COMMUNITY[recipient_iri]
                    g.add((benef_uri, EPIG.recipient, recipient_uri))
                    g.add((recipient_uri, RDFS.label, Literal(recipient_name)))

                    if recipient_type:
                        comm_type_iri = recipient_type.replace(' ', '_')
                        comm_type_uri = COMMTYPE[comm_type_iri]
                        g.add((recipient_uri, RDF.type, comm_type_uri))
                        g.add((comm_type_uri, RDFS.label, Literal(recipient_type)))

        # Communities information (top-level)
        communities = item.get('communities', [])
        for community_data in communities:
            community_id = community_data.get('community_id', 0)
            community_name = community_data.get('community_name', '')

            if not community_name:
                continue

            # Create community URI
            community_uri = COMMUNITY[f"{edcs_id}_community_{community_id}"]

            # Basic community information
            g.add((community_uri, RDF.type, EPIG.Community))
            g.add((community_uri, RDFS.label, Literal(community_name)))
            g.add((inscription_uri, EPIG.mentions, community_uri))

            # Normalized name
            community_name_normalized = community_data.get('community_name_normalized', '')
            if community_name_normalized:
                g.add((community_uri, EPIG.normalizedName, Literal(community_name_normalized)))

            # Community type
            community_type = community_data.get('community_type', '')
            if community_type:
                community_type_iri = community_type.replace(' ', '_')
                comm_type_uri = COMMTYPE[community_type_iri]
                g.add((community_uri, EPIG.communityType, comm_type_uri))
                g.add((comm_type_uri, RDF.type, EPIG.CommunityType))
                g.add((comm_type_uri, RDFS.label, Literal(community_type)))

            # Description
            community_description = community_data.get('community_description', '')
            if community_description:
                g.add((community_uri, DCTERMS.description, Literal(community_description, lang='en')))

            # Evidence
            evidence = community_data.get('evidence', '')
            if evidence:
                g.add((community_uri, EPIG.evidence, Literal(evidence)))

        # Person relationships (top-level, more detailed format)
        person_relationships = item.get('person_relationships', item.get('relationships', []))

        for idx, rel_item in enumerate(person_relationships, 1):
            rel_type = rel_item.get('type', '')
            rel_property = rel_item.get('property', '')

            # Get source and target IDs
            source_person_id = rel_item.get('source_person_id')
            target_person_id = rel_item.get('target_person_id')
            target_community_id = rel_item.get('target_community_id')

            # Backward compatibility
            if source_person_id is None:
                source_person_id = rel_item.get('source_person_index', 0)
            if target_person_id is None:
                target_person_id = rel_item.get('target_person_index')

            # Source person URI
            source_person_uri = PERSON[f"{edcs_id}_person_{source_person_id}"]

            # Determine target URI
            target_uri = None

            # Target is a community (affiliation)
            if target_community_id is not None:
                target_uri = COMMUNITY[f"{edcs_id}_community_{target_community_id}"]
            # Target is a person (person-to-person)
            elif target_person_id is not None:
                target_uri = PERSON[f"{edcs_id}_person_{target_person_id}"]
            else:
                # Old format: create new resource from target_person_name
                target_person_name = rel_item.get('target_person_name', rel_item.get('person_name', ''))
                if not target_person_name:
                    continue

                target_uri = PERSON[f"{edcs_id}_rel_{idx}"]
                g.add((target_uri, RDF.type, EPIG.PersonReference))
                g.add((target_uri, FOAF.name, Literal(target_person_name)))

                # Additional target person information
                target_person_readable = rel_item.get('target_person_name_readable', rel_item.get('person_name_readable', ''))
                if target_person_readable:
                    g.add((target_uri, RDFS.label, Literal(target_person_readable)))

                target_person_normalized = rel_item.get('target_person_name_normalized', rel_item.get('person_name_normalized'))
                if target_person_normalized:
                    g.add((target_uri, EPIG.normalizedName, Literal(target_person_normalized)))

                target_person_link = rel_item.get('target_person_name_link', rel_item.get('person_name_link'))
                if target_person_link:
                    wikidata_uri = URIRef(f"http://www.wikidata.org/entity/{target_person_link}")
                    g.add((target_uri, EPIG.wikidataEntity, wikidata_uri))
                    g.add((target_uri, SKOS.exactMatch, wikidata_uri))

                target_status = rel_item.get('social_status', '')
                if target_status:
                    target_status_iri = target_status.replace(' ', '_')
                    target_status_uri = STATUS[target_status_iri]
                    g.add((target_uri, EPIG.socialStatus, target_status_uri))
                    g.add((target_status_uri, RDF.type, EPIG.SocialStatus))
                    g.add((target_status_uri, RDFS.label, Literal(target_status)))

                    target_status_evidence = rel_item.get('social_status_evidence', '')
                    if target_status_evidence:
                        g.add((target_status_uri, EPIG.evidence, Literal(target_status_evidence)))

                g.add((inscription_uri, EPIG.mentions, target_uri))

            # Create relationship URI
            relationship_uri = REL[f"{edcs_id}_rel_{idx}"]

            g.add((relationship_uri, RDF.type, EPIG.Relationship))

            # Relationship type as URI
            if rel_type:
                rel_type_iri = rel_type.replace(' ', '_')
                rel_type_uri = RELTYPE[rel_type_iri]
                g.add((relationship_uri, EPIG.relationshipType, rel_type_uri))
                g.add((rel_type_uri, RDF.type, EPIG.RelationshipType))
                g.add((rel_type_uri, RDFS.label, Literal(rel_type)))

            g.add((relationship_uri, EPIG.relationshipProperty, Literal(rel_property)))

            # Inscription and relationship connection
            g.add((inscription_uri, EPIG.mentions, relationship_uri))

            # Relationship direction
            g.add((relationship_uri, EPIG.source, source_person_uri))
            g.add((relationship_uri, EPIG.target, target_uri))

            # Direct relationships based on property
            if rel_type == 'family':
                # Family relationship direct link (person-to-person only)
                if target_person_id is not None and rel_property in ['father', 'mother', 'son', 'daughter', 'brother', 'sister']:
                    relation_property = EPIG[f"has{rel_property.capitalize()}"]
                    g.add((source_person_uri, relation_property, target_uri))
            elif rel_type == 'affiliation':
                # Affiliation relationship direct link (person-to-community)
                if target_community_id is not None:
                    g.add((source_person_uri, EPIG.affiliatedWith, target_uri))

            property_text = rel_item.get('property_text', '')
            if property_text:
                g.add((relationship_uri, EPIG.evidence, Literal(property_text)))

            notes = rel_item.get('notes', '')
            if notes:
                g.add((relationship_uri, RDFS.comment, Literal(notes)))

        # Overall notes
        notes = item.get('notes', '')
        if notes:
            g.add((inscription_uri, RDFS.comment, Literal(notes)))

    # Serialize graph
    print(f"Serializing to {format} format...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    g.serialize(destination=str(output_path), format=format)
    print(f"  ✓ RDF saved to: {output_path}")

    return len(data)


def main():
    parser = argparse.ArgumentParser(
        description="Create RDF/TTL from modified career graph data"
    )
    parser.add_argument(
        '--model', '-m',
        type=str,
        default='claude',
        help='Model directory to process (default: claude)'
    )
    parser.add_argument(
        '--place', '-p',
        type=str,
        help='Specific place name to process'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all places'
    )
    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (default: rdf_output/[model]/[place].ttl)'
    )
    parser.add_argument(
        '--format', '-f',
        type=str,
        default='turtle',
        choices=['turtle', 'xml', 'n3', 'nt', 'json-ld'],
        help='RDF serialization format (default: turtle)'
    )

    args = parser.parse_args()

    # Setup paths
    script_dir = Path(__file__).parent
    modified_dir = script_dir / 'validated_career_graphs' / args.model
    place_list_dir = script_dir / 'place_list'
    output_base_dir = script_dir / 'rdf_output_modified' / args.model

    # Check directories
    if not modified_dir.exists():
        print(f"Error: Modified career graphs directory not found: {modified_dir}")
        return 1

    if not place_list_dir.exists():
        print(f"Warning: Place list directory not found: {place_list_dir}")
        print("Proceeding without Pleiades ID mappings...")
        pleiades_mapping = {}
    else:
        # Load Pleiades mappings from CSV files
        pleiades_mapping = load_pleiades_mapping_from_csv(place_list_dir)

    print("="*80)
    print("RDF Creation from Modified Career Graphs")
    print("="*80)
    print(f"Model: {args.model}")
    print(f"Modified graphs directory: {modified_dir}")
    print(f"Pleiades mappings: {len(pleiades_mapping)} places")
    print()

    # Determine which places to process
    if args.place:
        places_to_process = [args.place]
    elif args.all:
        place_dirs = [d for d in modified_dir.iterdir() if d.is_dir()]
        places_to_process = [d.name for d in place_dirs]
    else:
        print("Error: Please specify either --place or --all")
        return 1

    if not places_to_process:
        print("No places to process")
        return 1

    print(f"Processing {len(places_to_process)} place(s)...")
    print()

    total_inscriptions = 0

    for place_name in places_to_process:
        print(f"[{place_name}]")

        place_dir = modified_dir / place_name
        if not place_dir.exists():
            print(f"  Warning: Directory not found, skipping")
            continue

        # Find JSON files
        json_files = list(place_dir.glob('*.json'))
        if not json_files:
            print(f"  Warning: No JSON files found, skipping")
            continue

        for json_file in json_files:
            # Determine output path
            if args.output and len(places_to_process) == 1 and len(json_files) == 1:
                output_path = Path(args.output)
            else:
                output_filename = json_file.stem + '.ttl'
                output_path = output_base_dir / place_name / output_filename

            # Create RDF
            count = create_rdf_graph(json_file, output_path, pleiades_mapping, args.format)
            total_inscriptions += count

        print()

    print("="*80)
    print("Conversion complete!")
    print("="*80)
    print(f"Total inscriptions processed: {total_inscriptions}")
    print(f"Output directory: {output_base_dir}")
    print("="*80)


if __name__ == "__main__":
    import sys
    sys.exit(main() or 0)
