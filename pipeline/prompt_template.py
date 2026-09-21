"""
Shared prompt template for Latin inscription information extraction.
Imported by extract_career_graph.py and the finetuning pipeline.
"""

roman_emperors = {'Augustus': 'Q1405', 'Tiberius': 'Q1407', 'Caligula': 'Q1409', 'Claudius': 'Q1411', 'Nero': 'Q1413', 'Galba': 'Q1414', 'Otho': 'Q1416', 'Vitellius': 'Q1417', 'Vespasian': 'Q1419', 'Titus': 'Q1421', 'Domitian': 'Q1423', 'Nerva': 'Q1424', 'Trajan': 'Q1425', 'Hadrian': 'Q1427', 'Antoninus Pius': 'Q1429', 'Marcus Aurelius': 'Q1430', 'Lucius Verus': 'Q1433', 'Commodus': 'Q1434', 'Pertinax': 'Q1436', 'Didius Julianus': 'Q1440', 'Septimius Severus': 'Q1442', 'Caracalla': 'Q1446', 'Geta (emperor)': 'Q183089', 'Macrinus': 'Q1752', 'Diadumenian': 'Q46840', 'Elagabalus': 'Q1762', 'Severus Alexander': 'Q1769', 'Maximinus Thrax': 'Q1777', 'Gordian I': 'Q1782', 'Gordian II': 'Q1803', 'Pupienus': 'Q1797', 'Balbinus': 'Q1805', 'Gordian III': 'Q1812', 'Philip the Arab': 'Q1817', 'Philip II (Roman emperor)': 'Q318865', 'Decius': 'Q1830', 'Herennius Etruscus': 'Q273253', 'Trebonianus Gallus': 'Q171023', 'Hostilian': 'Q46837', 'Volusianus': 'Q202222', 'Aemilianus': 'Q177980', 'Silbannacus': 'Q442570', 'Valerian (emperor)': 'Q46750', 'Gallienus': 'Q104475', 'Saloninus': 'Q297494', 'Claudius Gothicus': 'Q46762', 'Quintillus': 'Q185844', 'Aurelian': 'Q46780', 'Tacitus (emperor)': 'Q177988', 'Florianus': 'Q199946', 'Probus (emperor)': 'Q187068', 'Carus': 'Q187004', 'Carinus': 'Q190097', 'Numerian': 'Q46821', 'Diocletian': 'Q43107', 'Maximian': 'Q46768', 'Galerius': 'Q172168', 'Constantius Chlorus': 'Q131195', 'Severus II': 'Q46814', 'Maxentius': 'Q182070', 'Licinius': 'Q184549', 'Maximinus Daza': 'Q189095', 'Valerius Valens': 'Q311274', 'Martinian (emperor)': 'Q268744', 'Constantine the Great': 'Q8413', 'Constantine II (emperor)': 'Q46734', 'Constans I': 'Q185538', 'Constantius II': 'Q46418', 'Magnentius': 'Q212876', 'Nepotianus': 'Q367598', 'Julian (emperor)': 'Q33941', 'Jovian (emperor)': 'Q34074', 'Valentinian I': 'Q46720', 'Valens': 'Q172471', 'Procopius (usurper)': 'Q316284', 'Gratian': 'Q189108', 'Magnus Maximus': 'Q211396', 'Valentinian II': 'Q46846', 'Eugenius': 'Q313058', 'Theodosius I': 'Q46696', 'Arcadius': 'Q159369', 'Honorius': 'Q159798', 'Constantine III (Western Roman emperor)': 'Q209793', 'Theodosius II': 'Q160353', 'Priscus Attalus': 'Q316286', 'Constantius III': 'Q201905', 'Joannes': 'Q309847', 'Valentinian III': 'Q170026', 'Marcian': 'Q178004', 'Petronius Maximus': 'Q191940', 'Avitus': 'Q203198', 'Majorian': 'Q191956', 'Libius Severus': 'Q207121', 'Anthemius': 'Q211772', 'Olybrius': 'Q193678', 'Glycerius': 'Q202543', 'Julius Nepos': 'Q103860', 'Romulus Augustulus': 'Q130601', 'Leo I (emperor)': 'Q183776', 'Leo II (emperor)': 'Q191707', 'Zeno (emperor)': 'Q183452', 'Basiliscus': 'Q193056', 'Anastasius I Dicorus': 'Q173470', 'Justin I': 'Q183445', 'Justinian I': 'Q41866', 'Justin II': 'Q183813', 'Tiberius II Constantine': 'Q31491', 'Maurice (emperor)': 'Q181764', 'Phocas': 'Q31556'}


def build_extraction_prompt(inscription_text: str, dating_from=None, dating_to=None) -> str:
    """
    Build the full Latin inscription extraction prompt.
    Mirrors the logic in extract_career_graph.py:extract_person_and_career().
    """
    emperor_list = "\n".join(
        [f"  - {name} (Wikidata QID: {qid})" for name, qid in sorted(roman_emperors.items())]
    )

    dating_info = ""
    if dating_from is not None and dating_to is not None:
        try:
            if dating_from != '' and dating_to != '':
                dating_info = f"\n\nInscription dating: {int(float(dating_from))} - {int(float(dating_to))} CE"
        except (ValueError, TypeError):
            pass

    return """Please analyze the following Latin inscription and extract the information below in JSON format.

Inscription text:
""" + inscription_text + dating_info + """

Information to extract:
1. The names of ALL persons mentioned in the inscription, regardless of whether they are main subjects, dedicators, or mentioned in passing (e.g., government officials who approved the inscription, family members, colleagues, etc.). Extract every person.
2. ALL communities/groups mentioned in the inscription, including legions, cities, towns, villages, associations, collegia, tribes, etc. For each community, extract:
   - The label as it appears in the inscription (Latin form)
   - A normalized label (standardized Latin form)
   - A controlled category type (see community types list below)
3. For EACH person, extract their social status, gender, ethnicity (Roman, Roman with local name, local) if evident from the text. Use standardized labels from the list below to minimize variation.
4. For EACH person, if their career is described, extract the career path in exact order mentioned in the text. For each position, classify it into one of the position types listed below. Also extract the location (city, province, or region) explicitly associated with each position if stated in the inscription.
5. For EACH person, if the inscription records any benefactions (evergetism) such as construction or repair of public buildings, temples, baths, roads, or donations of money, games, or feasts, extract those as well.
    Types of benefaction to extract (use EXACTLY these type labels):
        - Construction: type = "construction"
        - Repair: type = "repair"
        - Donation: type = "donation"
        - Games: type = "games"
        - Feast: type = "feast"
        - Other: type = "other"
    Types of objects to extract (use standardized labels):
        - Building: "building", "temple", "bath", "road", "aqueduct", etc.
        - Monetary donation: "money", "sportulae", "congiarium", etc.
        - Games: "gladiatorial games", "theatrical performances", etc.
        - Feast: "public banquet", etc.
        - Statue: "statue", "signum", etc.
        - Other: "other", etc.
    For each benefaction, if the object field contains multiple distinct items joined by "et", ",", or similar, split them into individual entries in the "objects" array. If only one item, the "objects" array should contain a single entry matching the object field.
    IMPORTANT - SHARED BENEFACTION RULE: If a single benefaction event involves multiple persons (e.g., one person acts as organizer/intermediary and another as funder/executor), record it as ONE benefaction entry under the primary agent (the person most directly responsible or explicitly named first), NOT as separate entries under each person. Do NOT duplicate the same benefaction event across multiple persons' "benefactions" arrays. If the roles are ambiguous, prefer the person described as the direct actor (e.g., the one who "fecit" or "dedit"), and note the others via the benefaction_text field.
6. If following types of relationships between persons or between persons and communities are described, extract those as well.
    Types of relationships to extract (use EXACTLY these type labels):
        - Family relationships: type = "family"
        - Colleague relationships: type = "colleague"
        - Patronage relationships: type = "patronage"
        - Dedicator and dedicatee relationships: type = "dedication"
        - Economic relationships: type = "economic"
        - Affiliation relationships (person to community): type = "affiliation"

    DIRECTION RULE: "property" always describes the role of the SOURCE person, not the target.
        - If person A is the son of person B: source=A, target=B, property="son"
        - If person A is the father of person B: source=A, target=B, property="father"
        - If person A is the wife of person B: source=A, target=B, property="wife"
        - If person A is a freedman of person B: source=A, target=B, property="freedman"
        Never set property to the role of the TARGET person.

    For relationship property, use standardized labels from the list below:
        Family: "father", "mother", "son", "daughter", "brother", "sister", "spouse", "husband", "wife",
                "grandfather", "grandmother", "grandson", "granddaughter",
                "great-grandfather", "great-great-grandfather",
                "uncle", "aunt", "nephew", "niece", "cousin",
                "ancestor", "descendant",
                "son-in-law", "daughter-in-law", "father-in-law", "mother-in-law",
                "stepson", "stepfather", "stepchild",
                "foster-child", "foster-parent", "foster-daughter", "foster-father"
        Colleague: "co-officer", "fellow-soldier", "colleague", "associate"
        Patronage: "patron", "client", "freedman", "freedwoman", "former-owner"
        Dedication: "dedicator", "dedicatee", "honored-person", "person-who-erected"
        Economic: "buyer", "seller", "debtor", "creditor", "business-partner", "tenant", "landlord", "contractor", "employer", "employee"
        Affiliation: "member", "soldier", "decurion", "citizen", "resident", "officer", "priest"

    For each relationship, extract:
        - Type of relationship (use EXACTLY: "family", "colleague", "patronage", "dedication", "economic", or "affiliation")
        - Property of the relationship (use standardized labels from above list)
        - The text in the inscription that expresses this relationship
        - If person-to-person: the name of the related person and their social status
        - If person-to-community (affiliation): the community_id from the communities array
        - Any other relevant notes

    For economic relationships, look for terms like:
        - Sale/purchase: emit, vendit, comparavit, mercatus est
        - Debt: debitor, creditor, debitum
        - Business partnership: socius, consors
        - Lease/rental: conductor, locator, colonus
        - Employment: operarius, redemptio operis

Output format (JSON):
{
  "persons": [
    {
      "person_id": 0,
      "person_name": "Name of the person (Latin form)",
      "person_name_readable": "Name of the person (readable form)",
      "praenomen": "Praenomen (first name, e.g., Gaius, Marcus, Lucius) if identifiable",
      "nomen": "Nomen gentilicium (family name, e.g., Iulius, Cornelius) if identifiable",
      "cognomen": "Cognomen (surname, e.g., Caesar, Scipio) if identifiable",
      "person_name_normalized": "Normalized name (for emperors only, exact match from the list below)",
      "person_name_link": "Wikidata QID (for emperors only, e.g., Q1421)",
      "social_status": "Social status (e.g., emperor, senator, equestrian, decurion, freedman, slave, soldier, merchant, gladiator, etc.)",
      "social_status_evidence": "Direct quote from the inscription (Latin) that indicates the social status. Empty string if not stated.",
      "gender": "Gender (male, female, unknown)",
      "gender_evidence": "Direct quote from the inscription (Latin) that indicates the gender. Empty string if not stated.",
      "ethnicity": "Ethnicity (Roman, Roman with local name, local)",
      "ethnicity_evidence": "Direct quote from the inscription (Latin) that indicates the ethnicity. Empty string if not stated.",
      "age_at_death": "Age at death in years (if mentioned, e.g., from 'vixit anni LX' or 'vixit annis LX' or 'vix. ann. LX')",
      "age_at_death_evidence": "Direct quote from the inscription (Latin) that mentions the age (e.g., 'vixit annis LX'). Empty string if not mentioned.",
      "has_career": true/false,
      "career_path": [
        {
          "position": "Title or office (Latin)",
          "position_normalized": "title or office without philological remarks in nominative form (Latin)",
          "position_abstract": "most abstract form of the position, removing all qualifiers and specifications (Latin)",
          "position_type": "Type of position following the classification below ( military, imperial administration, provincial administration, local administration, imperial priesthood, provincial priesthood, local priesthood, occupation, other)",
          "position_description": "Description of the position (English)",
          "location": "Place name explicitly associated with this position in the inscription (Latin form), or null",
          "location_normalized": "Standardized/modern place name for the location, or null",
          "location_evidence": "Text in the inscription linking this position to the location, or null",
          "order": 1
        }
      ],
      "benefactions": [
        {
          "benefaction_type": "Type of benefaction based on benefaction type list",
          "object": "What was built/repaired/donated (Latin)",
          "object_type": "Type of object listed above",
          "object_description": "Description of the object (English)",
          "objects": [
            {
              "object": "Individual object (Latin), split from the object field if multiple items",
              "object_type": "Type of this individual object"
            }
          ],
          "benefaction_text": "Text in the inscription expressing the benefaction",
          "cost": "Cost or amount if mentioned",
          "notes": "Additional information (e.g., de sua pecunia, sua impensa, etc.)"
        }
      ]
    }
  ],
  "communities": [
    {
      "community_id": 0,
      "community_name": "Name of the community as it appears in the inscription (Latin form)",
      "community_name_normalized": "Normalized name of the community (standardized Latin form)",
      "community_type": "Type of community from controlled vocabulary (see list below)",
      "community_description": "Brief description of the community (English)",
      "evidence": "Text in the inscription mentioning this community"
    }
  ],
  "person_relationships": [
    {
      "source_person_id": 0,
      "target_person_id": 1,
      "target_community_id": null,
      "type": "Type of relationship (e.g., family, colleague, patronage, dedication, economic, affiliation)",
      "property": "Relationship detail (e.g., father, sibling, superior, dedicator, honored-person, member, soldier)",
      "property_text": "Text in the inscription expressing the relationship",
      "notes": "Other relevant information"
    }
  ],
  "notes": "Other relevant information"
}

ROMAN EMPERORS LIST (for person_name_normalized and person_name_link):
""" + emperor_list + """

COMMUNITY TYPES (controlled vocabulary for community_type):
Military Units:
  - "legion" (legio)
  - "cohort" (cohors)
  - "ala" (cavalry unit)
  - "turma" (cavalry squadron)
  - "centuria" (century)
  - "vexillatio" (detachment)
  - "classis" (fleet)

Administrative/Political Communities:
  - "city" (urbs, civitas, colonia)
  - "municipium" (municipality)
  - "colonia" (colony)
  - "vicus" (village/settlement)
  - "pagus" (rural district)
  - "provincia" (province)
  - "regio" (region)
  - "tribus" (tribe - voting district)

Religious/Social Organizations:
  - "collegium" (association, guild)
  - "sodalitas" (religious association)
  - "corpus" (corporate body)
  - "ordo" (order, e.g., ordo decurionum)
  - "familia" (household/familia)
  - "templum" (temple community)

Other:
  - "populus" (people/community)
  - "other" (if none of the above fit)

Notes:
- Extract ALL communities/groups mentioned in the inscription into the "communities" array, assigning each a unique community_id starting from 0.
- If no communities are mentioned, use an empty array for "communities".
- Extract ALL persons mentioned in the inscription into the "persons" array, assigning each a unique person_id starting from 0.
- For example, if the inscription mentions: (1) the person being honored, (2) a proconsul who approved the honor, (3) the person's father, extract all three as separate entries in "persons" with person_id 0, 1, and 2.
- If no person can be identified, create one entry with "person_name" set to "Unknown".
- ROMAN NAME STRUCTURE (Tria Nomina): For Roman citizens, attempt to identify the three-part name structure:
  * praenomen: The personal first name (e.g., Gaius, Marcus, Lucius, Publius, Titus, Quintus, etc.)
  * nomen: The family name or nomen gentilicium (e.g., Iulius, Cornelius, Flavius, Valerius, etc.)
  * cognomen: The surname or additional name (e.g., Caesar, Scipio, Maximus, etc.)
  * Example: For "Gaius Iulius Caesar" → praenomen: "Gaius", nomen: "Iulius", cognomen: "Caesar"
  * Example: For "C(aius) Iulius Caesar" → praenomen: "Caius", nomen: "Iulius", cognomen: "Caesar"
  * If the name structure cannot be clearly identified (e.g., single name, non-Roman name), leave praenomen, nomen, and cognomen as empty strings
  * For freedmen, the praenomen and nomen are typically inherited from the former owner, with the original name becoming the cognomen
  * Some persons may have additional cognomina (agnomen) or filiation (e.g., "M(arci) f(ilius)" = son of Marcus)
- For each person in "persons": if the social status is not evident from the text, set "social_status" to empty string "".
- For each person in "persons": if no career information is present, set "has_career" to false and use an empty array for "career_path".
- For each person in "persons": if no benefactions are mentioned, use an empty array for "benefactions".
- IMPORTANT - SIMPLIFIED FORMAT FOR LARGE INSCRIPTIONS: If the inscription contains more than 20 persons, use a SIMPLIFIED format to reduce output size:
  * For each person in "persons", include ONLY these fields: person_id, person_name, person_name_readable, praenomen, nomen, cognomen, person_name_normalized, person_name_link, social_status, social_status_evidence, gender, gender_evidence, ethnicity, ethnicity_evidence
  * OMIT these fields: age_at_death, age_at_death_evidence, has_career, career_path, benefactions
  * For "person_relationships": extract ONLY family relationships between persons, and affiliation relationships to the main community. Omit other relationship types.
  * Still extract all persons and the main community, but with minimal details to stay within token limits.
- AGE AT DEATH: For funerary inscriptions, extract the age at death if mentioned. Common Latin expressions include:
  * "vixit annis" or "vixit anni" + number (e.g., "vixit annis LX" = lived 60 years)
  * "vix. ann." or "v. a." or "vix. a." + number (abbreviated forms)
  * "annos" or "annorum" + number (e.g., "annos XXX" = 30 years old)
  * Convert Roman numerals to Arabic numbers (e.g., LX → 60, XXX → 30, XLV → 45)
  * Record the exact Latin text in "age_at_death_evidence"
  * If age is mentioned in months (menses/mensibus) or days (dies/diebus), still record in "age_at_death_evidence" but leave "age_at_death" empty
  * If no age is mentioned, leave both "age_at_death" and "age_at_death_evidence" as empty strings
- If no relationships are mentioned, use an empty array for "person_relationships".
- Extract the career path in the order in which it appears in the inscription (this may not always correspond to chronological order).
- IMPORTANT - CONSULAR DATING FORMULAS: Do NOT extract consular offices when they appear in DATING FORMULAS:
  * Dating formulas use the ablative case: "[Name] consule" (singular) or "[Name] et [Name] consulibus" (plural)
  * Common dating patterns: "Imp(eratore) [Name] Aug(usto) [N] co(n)s(ule)", "[Name] et [Name] co(n)s(ulibus)"
  * These are temporal references for dating the inscription, NOT descriptions of the person's career
  * However, if "consul" or related terms appear in OTHER grammatical cases (nominative, genitive, dative, accusative) as part of a person's career description, DO extract them
  * Example to EXCLUDE: "Imp(eratore) Domitiano Caes(are) Aug(usto) Germ(anico) XIIII co(n)s(ule)" - this is a dating formula in ablative
  * Example to INCLUDE: "[Name] consularis" (nominative) or "[Name] consulis" (genitive) describing the person's rank
  * Example to INCLUDE: "consul designatus" (nominative), "consuli designato" (dative) - these describe career positions
- In "person_relationships", use "source_person_id" and "target_person_id" to reference persons by their person_id in the "persons" array.
- CRITICAL: "property" always describes the role of the SOURCE person (not the target).
  * Correct:   person 0 is the son  of person 1 → source=0, target=1, property="son"
  * Correct:   person 0 is the father of person 1 → source=0, target=1, property="father"
  * INCORRECT: person 0 mentions his father (person 1) → source=0, target=1, property="father"  ← Wrong! Person 0 is the son, so property should be "son"
- ALL relationships should be recorded in the "person_relationships" array:
  * For person-to-person relationships: Use "source_person_id" and "target_person_id", set "target_community_id" to null
    Example: Person 0 is the son of person 1 (father) → {"source_person_id": 0, "target_person_id": 1, "target_community_id": null, "type": "family", "property": "son", ...}
    Example: Person 1 (father) is the father of person 0 → {"source_person_id": 1, "target_person_id": 0, "target_community_id": null, "type": "family", "property": "father", ...}
    Note: The same relationship can be recorded from both directions if both persons are clearly identified.
  * For person-to-community relationships (affiliation): Use "source_person_id" and "target_community_id", set "target_person_id" to null
    Example: If person 0 is a soldier of legion 1, record: {"source_person_id": 0, "target_person_id": null, "target_community_id": 1, "type": "affiliation", "property": "soldier", ...}
    Example: If person 0 is a member of collegium 0, record: {"source_person_id": 0, "target_person_id": null, "target_community_id": 0, "type": "affiliation", "property": "member", ...}
- EMPEROR IDENTIFICATION: If social_status is "emperor" for the main person or any related person:
  * Consider the inscription text, dating range, and historical context
  * Match the person to the correct emperor from the ROMAN EMPERORS LIST above
  * Set person_name_normalized to the EXACT name from the list (e.g., "Titus", "Constantine the Great")
  * Set person_name_link to the corresponding Wikidata QID (e.g., "Q1421")
  * If multiple emperors have similar names, use the dating and context to distinguish (e.g., Constantine I vs Constantine II vs Constantine III)
  * If no confident match can be made, leave person_name_normalized and person_name_link as empty strings
  * For non-emperors, leave person_name_normalized and person_name_link as empty strings
- For benefactions, look for verbs like: fecit, construxit, aedificavit, refecit, restituit, dedit, donavit, sumptibus suis, sua pecunia, sua impensa, etc.
- Common benefaction types include:
  * construction: Building new structures (templum, aedes, basilica, forum, porta, murus, aquaeductus, etc.)
  * repair: Repairing existing structures (refecit, restituit)
  * donation: Monetary gifts or distributions (sportulae, congiarium, etc.)
  * games: Gladiatorial games, theatrical performances (ludi, munera)
  * feast: Public banquets (epulum publicum)
  * statue: Dedication of statues (statua, signum)

STANDARDIZED SOCIAL STATUS LABELS (use these EXACTLY to minimize variation):
Imperial Family:
  - "emperor" (for Augustus, Caesar with imperial power)
  - "empress" (for Augusta)
  - "imperial-family" (for other imperial family members)

Senatorial Order:
  - "senator-clarissimus" (vir clarissimus, v.c.)
  - "senator-consularis" (consular rank)
  - "senator-praetorius" (praetorian rank)

Equestrian Order:
  - "equestrian-perfectissimus" (vir perfectissimus, v.p.)
  - "equestrian-egregius" (vir egregius, v.e.)
  - "equestrian-splendidus" (vir splendidus)
  - "equestrian" (equo publico, general equestrian)

Municipal Elite:
  - "decurio" (decurion, member of local senate)
  - "duovir" (duumvir)
  - "aedilis" (aedile)
  - "quaestor" (quaestor)
  - "municipal-magistrate" (other municipal office holders)

Military:
  - "legatus" (legate)
  - "tribunus" (tribune)
  - "centurio" (centurion)
  - "soldier" (miles, general soldier)
  - "veteran" (veteranus)

Legal Status:
  - "freedman" (libertus)
  - "freedwoman" (liberta)
  - "slave" (servus, serva)
  - "freeborn" (ingenuus, ingenua)

Priesthood:
  - "flamen" (flamen)
  - "pontifex" (pontiff)
  - "augur" (augur)
  - "sacerdos" (priest/priestess)

Occupations:
  - "merchant" (negotiator, mercator)
  - "medicus" (doctor)
  - "gladiator" (gladiator)
  - "actor" (actor)
  - "artisan" (faber, etc.)

Other:
  - "unknown" (if status cannot be determined)
  - "citizen" (if only citizenship is mentioned)

- For social status, look for the indicators above and use the EXACT label from the list.
- Always prefer more specific labels over general ones (e.g., "senator-clarissimus" over "senator").
- For position_abstract in career_path: Extract only the core office/title name, removing all qualifiers, specifications, and additional information:
  * Remove adjectives and qualifiers (perpetuus, ordinarius, designatus, suffectus, etc.)
  * Remove prepositional phrases (in turmas equestres, cohortis primae, legionis III Augustae, etc.)
  * Remove geographic or unit designations
  * Remove temporal indicators (bis, ter, iterum, etc.)
  * Keep only the fundamental office title
  * Be sure position_abstract is in nominative form
  Examples:
    - "flamen perpetuus" → "flamen"
    - "adlectus in turmas equestres" → "adlectus"
    - "praefectus cohortis primae" → "praefectus"
    - "tribunus militum legionis III Augustae" → "tribunus"
    - "consul ordinarius" → "consul"
    - "duovir quinquennalis" → "duovir"
- For position_type in career_path: Classify each position into one of the following types (use EXACTLY these labels):
  * "military": Military positions (legatus, tribunus, centurio, praefectus of military units, etc.)
  * "imperial-administration": Imperial administrative positions (praefectus praetorio, praefectus urbi, procurator, a rationibus, etc.)
  * "provincial-administration": Provincial administrative positions (legatus Augusti pro praetore, proconsul, legatus legionis, etc.)
  * "local-administration": Municipal/local administrative positions (duovir, aedilis, quaestor, decurio, etc.)
  * "imperial-priesthood": Imperial cult priesthoods (flamen divi, sodalis, arvalis, etc.)
  * "provincial-priesthood": Provincial priesthoods (sacerdos provinciae, pontifex provinciae, etc.)
  * "local-priesthood": Local priesthoods (flamen municipii, pontifex, augur at local level, etc.)
  * "occupation": Non-political occupations and professions (negotiator, mercator, medicus, faber, etc.)
  * "other": Positions that don't fit the above categories or unclear classifications
- For location in career_path: Only extract a location directly linked to the specific position in the text (e.g., "legatus Hispaniae" → location: "Hispania"). Do NOT infer from findspot. Set all location fields to null if no location is explicitly stated for that position.
- For objects in benefactions: Always populate the "objects" array. If the "object" field contains multiple distinct items (joined by "et", ",", or similar conjunctions), split each into a separate entry. If only one item, the array contains one entry. Each entry uses the same object_type vocabulary as the object_type field.
- Output JSON only and do not include any explanatory text.
- CRITICAL: All "evidence" fields (social_status_evidence, gender_evidence, ethnicity_evidence, age_at_death_evidence, location_evidence, property_text, benefaction_text, etc.) must contain ONLY a direct quote copied verbatim from the inscription text. Do NOT include reasoning, interpretation, explanation, or any text not present in the inscription. If the evidence is not explicitly stated in the inscription, use an empty string ""."""
