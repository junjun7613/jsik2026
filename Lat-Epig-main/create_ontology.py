#!/usr/bin/env python3
"""
Build an OWL ontology from existing RDF data in rdf_output/.

This script introspects the actual data in all.ttl (or individual TTL files)
and generates a formal ontology (epig_ontology.ttl) that declares:
  - Classes (owl:Class) for every epig: type found in the data
  - Object properties and datatype properties inferred from usage
  - rdfs:label, rdfs:comment, rdfs:domain, rdfs:range annotations
  - Controlled-vocabulary individuals (status:, reltype:, commtype:, divinity:)

Usage:
    python create_ontology.py
    python create_ontology.py --ttl rdf_output/claude/all.ttl
    python create_ontology.py --ttl rdf_output/claude/all.ttl --output epig_ontology.ttl
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

try:
    from rdflib import (
        OWL, RDF, RDFS, XSD, Graph, Literal, Namespace, URIRef
    )
    from rdflib.namespace import SKOS, DCTERMS
except ImportError:
    print("Error: rdflib is required.  Install with: pip install rdflib")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Namespaces
# ---------------------------------------------------------------------------
EPIG     = Namespace("http://example.org/epigraphy/")
FOAF     = Namespace("http://xmlns.com/foaf/0.1/")
BASE     = Namespace("http://example.org/inscription/")
PERSON   = Namespace("http://example.org/person/")
PLACE_NS = Namespace("http://example.org/place/")
PROV_NS  = Namespace("http://example.org/province/")
STATUS   = Namespace("http://example.org/status/")
RELTYPE  = Namespace("http://example.org/relationship-type/")
COMMTYPE = Namespace("http://example.org/community-type/")
DIVINITY = Namespace("http://example.org/divinity/")
CAREER_NS = Namespace("http://example.org/career/")
BENEF_NS = Namespace("http://example.org/benefaction/")
REL_NS   = Namespace("http://example.org/relationship/")
COMMUNITY_NS = Namespace("http://example.org/community/")

SCRIPT_DIR = Path(__file__).parent
DEFAULT_TTL = SCRIPT_DIR / "rdf_output" / "claude" / "all.ttl"
DEFAULT_OUTPUT = SCRIPT_DIR / "epig_ontology.ttl"

# ---------------------------------------------------------------------------
# Class definitions with labels and comments
# ---------------------------------------------------------------------------
CLASS_META = {
    EPIG.Inscription: {
        "label": "Inscription",
        "comment": "A Latin epigraphic inscription from the EDCS corpus.",
    },
    FOAF.Person: {
        "label": "Person",
        "comment": "A person mentioned in one or more inscriptions.",
    },
    EPIG.CareerPosition: {
        "label": "Career Position",
        "comment": "A single office or position held during a person's career.",
    },
    EPIG.Benefaction: {
        "label": "Benefaction",
        "comment": "An act of public generosity (construction, donation, games, etc.) recorded in an inscription.",
    },
    EPIG.Community: {
        "label": "Community",
        "comment": "A social, political, military, or religious group mentioned in an inscription.",
    },
    EPIG.Relationship: {
        "label": "Relationship",
        "comment": "A directed social relationship between two entities (persons or communities).",
    },
    EPIG.Place: {
        "label": "Place",
        "comment": "A geographical location where an inscription was found.",
    },
    EPIG.Province: {
        "label": "Province",
        "comment": "A Roman administrative province.",
    },
    EPIG.SocialStatus: {
        "label": "Social Status",
        "comment": "A controlled-vocabulary term for a person's social rank or civic role.",
    },
    EPIG.RelationshipType: {
        "label": "Relationship Type",
        "comment": "A high-level category of social relationship (family, patronage, etc.).",
    },
    EPIG.CommunityType: {
        "label": "Community Type",
        "comment": "A category of community or collective body (city, legion, collegium, etc.).",
    },
    EPIG.DivinityType: {
        "label": "Divinity Type",
        "comment": "A deity or deified figure referenced in inscriptions.",
    },
    EPIG.Nomen: {
        "label": "Nomen",
        "comment": "A Roman gentilicial name (family name).",
    },
    EPIG.Cognomen: {
        "label": "Cognomen",
        "comment": "A Roman personal cognomen.",
    },
    EPIG.Praenomen: {
        "label": "Praenomen",
        "comment": "A Roman praenomen (first name).",
    },
}

# ---------------------------------------------------------------------------
# Property definitions
# ---------------------------------------------------------------------------
# Each entry: (type, label, comment, domain, range)
# type: "object" | "datatype" | "annotation"
PROPERTY_META = {
    # --- Inscription properties ---
    EPIG.text: (
        "datatype", "inscription text",
        "The transcribed Latin text of the inscription.",
        EPIG.Inscription, XSD.string,
    ),
    EPIG.datingFrom: (
        "datatype", "dating from",
        "Earliest possible date of the inscription (year CE, negative = BCE).",
        EPIG.Inscription, XSD.integer,
    ),
    EPIG.datingTo: (
        "datatype", "dating to",
        "Latest possible date of the inscription (year CE, negative = BCE).",
        EPIG.Inscription, XSD.integer,
    ),
    EPIG.pleiadesId: (
        "datatype", "Pleiades ID",
        "Pleiades gazetteer identifier for the find-spot.",
        EPIG.Inscription, XSD.string,
    ),
    EPIG.place: (
        "object", "place",
        "The place where the inscription was found.",
        EPIG.Inscription, EPIG.Place,
    ),
    EPIG.province: (
        "object", "province",
        "The Roman province in which the inscription was found.",
        EPIG.Inscription, EPIG.Province,
    ),
    EPIG.mainSubject: (
        "object", "main subject",
        "The principal person(s) commemorated or named in the inscription.",
        EPIG.Inscription, FOAF.Person,
    ),
    EPIG.mentions: (
        "object", "mentions",
        "Any entity (person, community, relationship) directly referenced in the inscription.",
        EPIG.Inscription, None,
    ),

    # --- Person properties ---
    EPIG.praenomen: (
        "object", "praenomen",
        "The Roman praenomen of the person.",
        FOAF.Person, EPIG.Praenomen,
    ),
    EPIG.nomen: (
        "object", "nomen",
        "The Roman nomen gentilicium of the person.",
        FOAF.Person, EPIG.Nomen,
    ),
    EPIG.cognomen: (
        "object", "cognomen",
        "The Roman cognomen of the person.",
        FOAF.Person, EPIG.Cognomen,
    ),
    EPIG.socialStatus: (
        "object", "social status",
        "The social rank or civic role of the person.",
        FOAF.Person, EPIG.SocialStatus,
    ),
    EPIG.genderEvidence: (
        "datatype", "gender evidence",
        "Textual evidence used to determine the person's gender.",
        FOAF.Person, XSD.string,
    ),
    EPIG.ethnicity: (
        "datatype", "ethnicity",
        "Ethnic or cultural origin inferred for the person.",
        FOAF.Person, XSD.string,
    ),
    EPIG.ethnicityEvidence: (
        "datatype", "ethnicity evidence",
        "Textual evidence used to infer the person's ethnic origin.",
        FOAF.Person, XSD.string,
    ),
    EPIG.ageAtDeath: (
        "datatype", "age at death",
        "The age of the person at time of death, as recorded in the inscription.",
        FOAF.Person, XSD.integer,
    ),
    EPIG.ageAtDeathEvidence: (
        "datatype", "age at death evidence",
        "Textual evidence for the recorded age at death.",
        FOAF.Person, XSD.string,
    ),
    EPIG.isDivinity: (
        "datatype", "is divinity",
        "True if the person is a deity or deified figure rather than a historical human.",
        FOAF.Person, XSD.boolean,
    ),
    EPIG.divinityType: (
        "object", "divinity type",
        "The specific deity or deified figure this person represents.",
        FOAF.Person, EPIG.DivinityType,
    ),
    EPIG.divinityClassificationReasoning: (
        "datatype", "divinity classification reasoning",
        "Explanation for why this person was classified as a divinity.",
        FOAF.Person, XSD.string,
    ),
    EPIG.normalizedName: (
        "datatype", "normalized name",
        "A standardised form of the person's name for disambiguation.",
        FOAF.Person, XSD.string,
    ),
    EPIG.wikidataEntity: (
        "datatype", "Wikidata entity",
        "Wikidata QID for this person.",
        FOAF.Person, XSD.anyURI,
    ),
    EPIG.hasCareerPosition: (
        "object", "has career position",
        "Links a person to one of their career positions.",
        FOAF.Person, EPIG.CareerPosition,
    ),
    EPIG.hasBenefaction: (
        "object", "has benefaction",
        "Links a person to a benefaction they performed.",
        FOAF.Person, EPIG.Benefaction,
    ),
    EPIG.hasFather: (
        "object", "has father",
        "Direct father–child relationship.",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.hasMother: (
        "object", "has mother",
        "Direct mother–child relationship.",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.hasSon: (
        "object", "has son",
        "Direct parent–son relationship.",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.hasDaughter: (
        "object", "has daughter",
        "Direct parent–daughter relationship.",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.hasBrother: (
        "object", "has brother",
        "Sibling relationship (brother).",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.hasSister: (
        "object", "has sister",
        "Sibling relationship (sister).",
        FOAF.Person, FOAF.Person,
    ),
    EPIG.affiliatedWith: (
        "object", "affiliated with",
        "Affiliation relationship between a person and a community.",
        FOAF.Person, EPIG.Community,
    ),

    # --- CareerPosition properties ---
    EPIG.position: (
        "datatype", "position",
        "The position title as it appears in the inscription.",
        EPIG.CareerPosition, XSD.string,
    ),
    EPIG.positionNormalized: (
        "datatype", "position normalized",
        "A normalised form of the position title.",
        EPIG.CareerPosition, XSD.string,
    ),
    EPIG.positionAbstract: (
        "datatype", "position abstract",
        "A high-level, abstract label for this type of office (e.g. 'consul', 'flamen').",
        EPIG.CareerPosition, XSD.string,
    ),
    EPIG.positionType: (
        "datatype", "position type",
        "Broad category of the office (military, imperial-administration, priesthood, etc.).",
        EPIG.CareerPosition, XSD.string,
    ),
    EPIG.order: (
        "datatype", "order",
        "The sequence number of this position within the person's career.",
        EPIG.CareerPosition, XSD.integer,
    ),
    EPIG.nextPosition: (
        "object", "next position",
        "The career position held after this one.",
        EPIG.CareerPosition, EPIG.CareerPosition,
    ),
    EPIG.previousPosition: (
        "object", "previous position",
        "The career position held before this one.",
        EPIG.CareerPosition, EPIG.CareerPosition,
    ),

    # --- Benefaction properties ---
    EPIG.benefactionType: (
        "datatype", "benefaction type",
        "The category of benefaction (construction, donation, games, etc.).",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.object: (
        "datatype", "object",
        "The physical object or service provided in the benefaction.",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.objectType: (
        "datatype", "object type",
        "The category of the benefaction object (building, statue, etc.).",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.objectDescription: (
        "datatype", "object description",
        "A description of the benefaction object.",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.benefactionText: (
        "datatype", "benefaction text",
        "The relevant passage from the inscription describing the benefaction.",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.cost: (
        "datatype", "cost",
        "The cost of the benefaction as stated in the inscription.",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.costNumeric: (
        "datatype", "cost numeric",
        "The cost converted to a numeric value in sesterces.",
        EPIG.Benefaction, XSD.decimal,
    ),
    EPIG.costUnit: (
        "datatype", "cost unit",
        "The monetary unit used for the cost (sestertius, denarius, etc.).",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.costConversionReasoning: (
        "datatype", "cost conversion reasoning",
        "Explanation of how the cost was converted to the numeric value.",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.recipientType: (
        "datatype", "recipient type",
        "The type of recipient of the benefaction (community, deity, individual, etc.).",
        EPIG.Benefaction, XSD.string,
    ),
    EPIG.recipientName: (
        "datatype", "recipient name",
        "The name of the specific recipient of the benefaction.",
        EPIG.Benefaction, XSD.string,
    ),

    # --- Community properties ---
    EPIG.communityType: (
        "object", "community type",
        "The type or category of the community.",
        EPIG.Community, EPIG.CommunityType,
    ),

    # --- Relationship properties ---
    EPIG.relationshipType: (
        "object", "relationship type",
        "The high-level category of the relationship.",
        EPIG.Relationship, EPIG.RelationshipType,
    ),
    EPIG.relationshipProperty: (
        "datatype", "relationship property",
        "The specific relationship role (e.g. 'father', 'patron', 'soldier').",
        EPIG.Relationship, XSD.string,
    ),
    EPIG.source: (
        "object", "source",
        "The entity from which the relationship originates.",
        EPIG.Relationship, None,
    ),
    EPIG.target: (
        "object", "target",
        "The entity to which the relationship points.",
        EPIG.Relationship, None,
    ),

    # --- Shared ---
    EPIG.evidence: (
        "datatype", "evidence",
        "The Latin text passage that provides evidence for this assertion.",
        None, XSD.string,
    ),
    EPIG.notes: (
        "datatype", "notes",
        "Free-text notes or remarks about this entity.",
        None, XSD.string,
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def collect_vocab_individuals(data_graph: Graph, namespace: Namespace) -> list[URIRef]:
    """Return all URIs in data_graph that belong to the given namespace."""
    prefix = str(namespace)
    individuals = set()
    for s, p, o in data_graph:
        for node in (s, o):
            if isinstance(node, URIRef) and str(node).startswith(prefix):
                individuals.add(node)
    return sorted(individuals)


def get_label_from_uri(uri: URIRef) -> str:
    """Extract a human-readable label from the local name of a URI."""
    local = str(uri).rsplit("/", 1)[-1].rsplit("#", 1)[-1]
    return local.replace("_", " ").replace("---", " / ").strip()


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------
def build_ontology(data_graph: Graph) -> Graph:
    onto = Graph()

    # Bind namespaces
    onto.bind("epig",     EPIG)
    onto.bind("foaf",     FOAF)
    onto.bind("owl",      OWL)
    onto.bind("rdfs",     RDFS)
    onto.bind("xsd",      XSD)
    onto.bind("skos",     SKOS)
    onto.bind("dcterms",  DCTERMS)
    onto.bind("status",   STATUS)
    onto.bind("reltype",  RELTYPE)
    onto.bind("commtype", COMMTYPE)
    onto.bind("divinity", DIVINITY)

    # Ontology header
    onto_uri = URIRef("http://example.org/epigraphy/ontology")
    onto.add((onto_uri, RDF.type, OWL.Ontology))
    onto.add((onto_uri, RDFS.label, Literal("Epigraphic Inscription Ontology", lang="en")))
    onto.add((onto_uri, RDFS.comment, Literal(
        "OWL ontology for Latin epigraphic inscriptions, derived from the "
        "LLM-enriched EDCS career-graph dataset.", lang="en"
    )))
    onto.add((onto_uri, OWL.versionInfo, Literal("1.0")))

    # ------------------------------------------------------------------
    # 1. Classes
    # ------------------------------------------------------------------
    for cls_uri, meta in CLASS_META.items():
        onto.add((cls_uri, RDF.type, OWL.Class))
        onto.add((cls_uri, RDFS.label, Literal(meta["label"], lang="en")))
        onto.add((cls_uri, RDFS.comment, Literal(meta["comment"], lang="en")))
        onto.add((cls_uri, RDFS.isDefinedBy, onto_uri))

    # foaf:Person is from an external ontology – mark it as imported
    onto.add((FOAF.Person, OWL.equivalentClass, FOAF.Person))  # keep reference
    onto.add((onto_uri, OWL.imports, URIRef("http://xmlns.com/foaf/0.1/")))

    # ------------------------------------------------------------------
    # 2. Properties
    # ------------------------------------------------------------------
    for prop_uri, (ptype, label, comment, domain, rng) in PROPERTY_META.items():
        if ptype == "object":
            onto.add((prop_uri, RDF.type, OWL.ObjectProperty))
        else:
            onto.add((prop_uri, RDF.type, OWL.DatatypeProperty))

        onto.add((prop_uri, RDFS.label,   Literal(label, lang="en")))
        onto.add((prop_uri, RDFS.comment, Literal(comment, lang="en")))
        onto.add((prop_uri, RDFS.isDefinedBy, onto_uri))

        if domain:
            onto.add((prop_uri, RDFS.domain, domain))
        if rng:
            onto.add((prop_uri, RDFS.range, rng))

    # ------------------------------------------------------------------
    # 3. Controlled vocabulary individuals
    #    – inferred directly from the data
    # ------------------------------------------------------------------

    # 3a. SocialStatus individuals
    print("  Collecting status: individuals…")
    for uri in collect_vocab_individuals(data_graph, STATUS):
        label = get_label_from_uri(uri)
        onto.add((uri, RDF.type, EPIG.SocialStatus))
        onto.add((uri, RDF.type, OWL.NamedIndividual))
        onto.add((uri, RDFS.label, Literal(label, lang="en")))

    # 3b. RelationshipType individuals
    print("  Collecting reltype: individuals…")
    for uri in collect_vocab_individuals(data_graph, RELTYPE):
        label = get_label_from_uri(uri)
        onto.add((uri, RDF.type, EPIG.RelationshipType))
        onto.add((uri, RDF.type, OWL.NamedIndividual))
        onto.add((uri, RDFS.label, Literal(label, lang="en")))

    # 3c. CommunityType individuals
    print("  Collecting commtype: individuals…")
    for uri in collect_vocab_individuals(data_graph, COMMTYPE):
        label = get_label_from_uri(uri)
        onto.add((uri, RDF.type, EPIG.CommunityType))
        onto.add((uri, RDF.type, OWL.NamedIndividual))
        onto.add((uri, RDFS.label, Literal(label, lang="en")))

    # 3d. DivinityType individuals
    print("  Collecting divinity: individuals…")
    for uri in collect_vocab_individuals(data_graph, DIVINITY):
        label = get_label_from_uri(uri)
        onto.add((uri, RDF.type, EPIG.DivinityType))
        onto.add((uri, RDF.type, OWL.NamedIndividual))
        onto.add((uri, RDFS.label, Literal(label, lang="en")))

    # 3e. Place individuals (with Pleiades links already in data)
    print("  Collecting place: individuals…")
    for subj in data_graph.subjects(RDF.type, EPIG.Place):
        label_lit = data_graph.value(subj, RDFS.label)
        pleiades = data_graph.value(subj, SKOS.exactMatch)

        onto.add((subj, RDF.type, EPIG.Place))
        onto.add((subj, RDF.type, OWL.NamedIndividual))
        if label_lit:
            onto.add((subj, RDFS.label, label_lit))
        if pleiades:
            onto.add((subj, SKOS.exactMatch, pleiades))

    # 3f. Province individuals
    print("  Collecting province: individuals…")
    for uri in collect_vocab_individuals(data_graph, PROV_NS):
        label = get_label_from_uri(uri)
        onto.add((uri, RDF.type, EPIG.Province))
        onto.add((uri, RDF.type, OWL.NamedIndividual))
        onto.add((uri, RDFS.label, Literal(label.replace("_", " "), lang="en")))

    return onto


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Build an OWL ontology from existing RDF epigraphic data"
    )
    parser.add_argument(
        "--ttl",
        type=str,
        default=str(DEFAULT_TTL),
        help=f"Path to the source TTL file (default: {DEFAULT_TTL})",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help=f"Output ontology file (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    ttl_path = Path(args.ttl)
    if not ttl_path.exists():
        print(f"Error: TTL file not found: {ttl_path}")
        sys.exit(1)

    output_path = Path(args.output)

    # Load data graph
    print(f"Loading data from: {ttl_path}")
    data_graph = Graph()
    data_graph.parse(str(ttl_path), format="turtle")
    print(f"  Loaded {len(data_graph)} triples")

    # Build ontology
    print("Building ontology…")
    onto = build_ontology(data_graph)

    # Serialize
    onto.serialize(destination=str(output_path), format="turtle")
    print(f"\nOntology written to: {output_path}")
    print(f"  Total triples: {len(onto)}")


if __name__ == "__main__":
    main()
