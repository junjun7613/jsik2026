import json
import os
from anthropic import Anthropic
import google.generativeai as genai
from openai import OpenAI
from dotenv import load_dotenv
from tqdm import tqdm

# .envファイルから環境変数を読み込む
load_dotenv()

roman_emperors = {'Augustus': 'Q1405', 'Tiberius': 'Q1407', 'Caligula': 'Q1409', 'Claudius': 'Q1411', 'Nero': 'Q1413', 'Galba': 'Q1414', 'Otho': 'Q1416', 'Vitellius': 'Q1417', 'Vespasian': 'Q1419', 'Titus': 'Q1421', 'Domitian': 'Q1423', 'Nerva': 'Q1424', 'Trajan': 'Q1425', 'Hadrian': 'Q1427', 'Antoninus Pius': 'Q1429', 'Marcus Aurelius': 'Q1430', 'Lucius Verus': 'Q1433', 'Commodus': 'Q1434', 'Pertinax': 'Q1436', 'Didius Julianus': 'Q1440', 'Septimius Severus': 'Q1442', 'Caracalla': 'Q1446', 'Geta (emperor)': 'Q183089', 'Macrinus': 'Q1752', 'Diadumenian': 'Q46840', 'Elagabalus': 'Q1762', 'Severus Alexander': 'Q1769', 'Maximinus Thrax': 'Q1777', 'Gordian I': 'Q1782', 'Gordian II': 'Q1803', 'Pupienus': 'Q1797', 'Balbinus': 'Q1805', 'Gordian III': 'Q1812', 'Philip the Arab': 'Q1817', 'Philip II (Roman emperor)': 'Q318865', 'Decius': 'Q1830', 'Herennius Etruscus': 'Q273253', 'Trebonianus Gallus': 'Q171023', 'Hostilian': 'Q46837', 'Volusianus': 'Q202222', 'Aemilianus': 'Q177980', 'Silbannacus': 'Q442570', 'Valerian (emperor)': 'Q46750', 'Gallienus': 'Q104475', 'Saloninus': 'Q297494', 'Claudius Gothicus': 'Q46762', 'Quintillus': 'Q185844', 'Aurelian': 'Q46780', 'Tacitus (emperor)': 'Q177988', 'Florianus': 'Q199946', 'Probus (emperor)': 'Q187068', 'Carus': 'Q187004', 'Carinus': 'Q190097', 'Numerian': 'Q46821', 'Diocletian': 'Q43107', 'Maximian': 'Q46768', 'Galerius': 'Q172168', 'Constantius Chlorus': 'Q131195', 'Severus II': 'Q46814', 'Maxentius': 'Q182070', 'Licinius': 'Q184549', 'Maximinus Daza': 'Q189095', 'Valerius Valens': 'Q311274', 'Martinian (emperor)': 'Q268744', 'Constantine the Great': 'Q8413', 'Constantine II (emperor)': 'Q46734', 'Constans I': 'Q185538', 'Constantius II': 'Q46418', 'Magnentius': 'Q212876', 'Nepotianus': 'Q367598', 'Julian (emperor)': 'Q33941', 'Jovian (emperor)': 'Q34074', 'Valentinian I': 'Q46720', 'Valens': 'Q172471', 'Procopius (usurper)': 'Q316284', 'Gratian': 'Q189108', 'Magnus Maximus': 'Q211396', 'Valentinian II': 'Q46846', 'Eugenius': 'Q313058', 'Theodosius I': 'Q46696', 'Arcadius': 'Q159369', 'Honorius': 'Q159798', 'Constantine III (Western Roman emperor)': 'Q209793', 'Theodosius II': 'Q160353', 'Priscus Attalus': 'Q316286', 'Constantius III': 'Q201905', 'Joannes': 'Q309847', 'Valentinian III': 'Q170026', 'Marcian': 'Q178004', 'Petronius Maximus': 'Q191940', 'Avitus': 'Q203198', 'Majorian': 'Q191956', 'Libius Severus': 'Q207121', 'Anthemius': 'Q211772', 'Olybrius': 'Q193678', 'Glycerius': 'Q202543', 'Julius Nepos': 'Q103860', 'Romulus Augustulus': 'Q130601', 'Leo I (emperor)': 'Q183776', 'Leo II (emperor)': 'Q191707', 'Zeno (emperor)': 'Q183452', 'Basiliscus': 'Q193056', 'Anastasius I Dicorus': 'Q173470', 'Justin I': 'Q183445', 'Justinian I': 'Q41866', 'Justin II': 'Q183813', 'Tiberius II Constantine': 'Q31491', 'Maurice (emperor)': 'Q181764', 'Phocas': 'Q31556'}

def load_filtered_inscriptions(json_path):
    """
    JSONファイルから碑文データを読み込む

    Parameters:
    -----------
    json_path : str
        JSONファイルのパス

    Returns:
    --------
    list
        碑文データのリスト
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def call_llm(prompt, model_type, client):
    """
    指定されたLLMモデルを呼び出す

    Parameters:
    -----------
    prompt : str
        プロンプト
    model_type : str
        使用するモデル ('claude', 'gemini', 'gpt')
    client : object
        APIクライアント

    Returns:
    --------
    str
        LLMのレスポンステキスト
    """
    if model_type == 'claude':
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8192,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        return message.content[0].text

    elif model_type == 'gemini':
        model = client.GenerativeModel('gemini-3-pro-preview')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=8192,
                temperature=0
            )
        )
        return response.text

    elif model_type == 'gpt':
        response = client.chat.completions.create(
            model="gpt-5.2-2025-12-11",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=16384,  # GPT supports up to 16,384 tokens
            temperature=0
        )
        return response.choices[0].message.content

    else:
        raise ValueError(f"Unknown model type: {model_type}")


def extract_person_and_career(inscription_text, edcs_id, client, model_type='claude', dating_from=None, dating_to=None):
    """
    LLMを使用して碑文から人物と経歴を抽出する

    Parameters:
    -----------
    inscription_text : str
        碑文のテキスト
    edcs_id : str
        碑文のEDCS-ID
    client : object
        APIクライアント
    model_type : str
        使用するモデル ('claude', 'gemini', 'gpt')
    dating_from : float, optional
        碑文の年代下限
    dating_to : float, optional
        碑文の年代上限

    Returns:
    --------
    dict
        人物名と経歴情報を含む辞書
    """
    # 皇帝リストをプロンプトに含める
    emperor_list = "\n".join([f"  - {name} (Wikidata QID: {qid})" for name, qid in sorted(roman_emperors.items())])

    dating_info = ""
    if dating_from is not None and dating_to is not None:
        try:
            # 空文字列や無効な値をチェック
            if dating_from != '' and dating_to != '':
                dating_info = f"\n\nInscription dating: {int(float(dating_from))} - {int(float(dating_to))} CE"
        except (ValueError, TypeError):
            # 変換できない場合はスキップ
            pass

    prompt = """Please analyze the following Latin inscription and extract the information below in JSON format.

Inscription text:
""" + inscription_text + dating_info + """

Information to extract:
1. The names of ALL persons mentioned in the inscription, regardless of whether they are main subjects, dedicators, or mentioned in passing (e.g., government officials who approved the inscription, family members, colleagues, etc.). Extract every person.
2. ALL communities/groups mentioned in the inscription, including legions, cities, towns, villages, associations, collegia, tribes, etc. For each community, extract:
   - The label as it appears in the inscription (Latin form)
   - A normalized label (standardized Latin form)
   - A controlled category type (see community types list below)
3. For EACH person, extract their social status, gender, ethnicity (Roman, Roman with local name, local) if evident from the text. Use standardized labels from the list below to minimize variation.
4. For EACH person, if their career is described, extract the career path in exact order mentioned in the text. For each position, classify it into one of the position types listed below.
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
6. If following types of relationships between persons or between persons and communities are described, extract those as well.
    Types of relationships to extract (use EXACTLY these type labels):
        - Family relationships: type = "family"
        - Colleague relationships: type = "colleague"
        - Patronage relationships: type = "patronage"
        - Dedicator and dedicatee relationships: type = "dedication"
        - Economic relationships: type = "economic"
        - Affiliation relationships (person to community): type = "affiliation"

    For relationship property, use standardized labels from the list below:
        Family: "father", "mother", "son", "daughter", "brother", "sister", "spouse", "husband", "wife", "grandfather", "grandmother", "grandson", "granddaughter", "uncle", "aunt", "nephew", "niece", "cousin"
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
      "social_status_evidence": "Text evidence for the social status",
      "gender": "Gender (male, female, unknown)",
      "gender_evidence": "Text evidence for the gender",
      "ethnicity": "Ethnicity (Roman, Roman with local name, local)",
      "ethnicity_evidence": "Text evidence for the  ethnicity",
      "age_at_death": "Age at death in years (if mentioned, e.g., from 'vixit anni LX' or 'vixit annis LX' or 'vix. ann. LX')",
      "age_at_death_evidence": "Text evidence for the age at death (e.g., 'vixit anni LX')",
      "has_career": true/false,
      "career_path": [
        {
          "position": "Title or office (Latin)",
          "position_normalized": "title or office without philological remarks in nominative form (Latin)",
          "position_abstract": "most abstract form of the position, removing all qualifiers and specifications (Latin)",
          "position_type": "Type of position following the classification below ( military, imperial administration, provincial administration, local administration, imperial priesthood, provincial priesthood, local priesthood, occupation, other)",
          "position_description": "Description of the position (English)",
          "order": 1
        }
      ],
      "benefactions": [
        {
          "benefaction_type": "Type of benefaction based on benefaction type list",
          "object": "What was built/repaired/donated (Latin)",
          "object_type": "Type of object listed above",
          "object_description": "Description of the object (English)",
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
- ALL relationships should be recorded in the "person_relationships" array:
  * For person-to-person relationships: Use "source_person_id" and "target_person_id", set "target_community_id" to null
    Example: If person 0 (main subject) has a relationship with person 1 (father), record: {"source_person_id": 0, "target_person_id": 1, "target_community_id": null, "type": "family", "property": "father", ...}
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
- Output JSON only and do not include any explanatory text."""

    try:
        # LLMを呼び出す
        response_text = call_llm(prompt, model_type, client)
        # JSONの前後にある余分なテキストを削除
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        json_str = response_text[json_start:json_end]
        result = json.loads(json_str)
        result['edcs_id'] = edcs_id

        # 後方互換性のため、personsの最初の人物を旧形式のフィールドにも追加
        # また、旧形式のmain_persons/relationshipsも保持
        if result.get('persons') and len(result['persons']) > 0:
            first_person = result['persons'][0]
            result['person_name'] = first_person.get('person_name', 'Unknown')
            result['person_name_readable'] = first_person.get('person_name_readable', '')
            result['person_name_normalized'] = first_person.get('person_name_normalized', '')
            result['person_name_link'] = first_person.get('person_name_link', '')
            result['social_status'] = first_person.get('social_status', '')
            result['social_status_evidence'] = first_person.get('social_status_evidence', '')
            result['has_career'] = first_person.get('has_career', False)
            result['career_path'] = first_person.get('career_path', [])
            result['benefactions'] = first_person.get('benefactions', [])

            # main_persons形式も生成（RDF生成スクリプトの後方互換性のため）
            result['main_persons'] = result['persons']

            # person_relationshipsをrelationships形式に変換
            result['relationships'] = result.get('person_relationships', [])

        return result
    except json.JSONDecodeError as e:
        error_msg = f"JSON解析エラー (EDCS-ID: {edcs_id}): {e}"
        print(error_msg)
        print(f"レスポンス: {response_text[:500]}...")  # 最初の500文字のみ表示
        return {
            "edcs_id": edcs_id,
            "person_name": "Parse Error",
            "person_name_readable": "Parse Error",
            "has_career": False,
            "career_path": [],
            "notes": f"JSON解析エラー: {str(e)}",
            "raw_response": response_text,
            "error": error_msg
        }
    except Exception as e:
        error_msg = f"LLM呼び出しエラー (EDCS-ID: {edcs_id}): {e}"
        print(error_msg)
        return {
            "edcs_id": edcs_id,
            "person_name": "Error",
            "person_name_readable": "Error",
            "has_career": False,
            "career_path": [],
            "notes": f"LLM呼び出しエラー: {str(e)}",
            "raw_response": "",
            "error": error_msg
        }


def save_error_log(error_log_path, error_log, model_type, json_path):
    """
    エラーログをファイルに保存（追記モード）
    """
    from datetime import datetime

    # 既存のログファイルがあるかチェック
    file_exists = os.path.exists(error_log_path)

    with open(error_log_path, 'a', encoding='utf-8') as f:
        # 新規ファイルの場合はヘッダーを書き込む
        if not file_exists:
            f.write("=" * 80 + "\n")
            f.write(f"エラーログ - {model_type.upper()} Model\n")
            f.write(f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"入力ファイル: {json_path}\n")
            f.write("=" * 80 + "\n\n")

        # 新しいエラーを追記
        for error in error_log:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n")
            f.write(f"EDCS-ID: {error['edcs_id']}\n")
            f.write(f"エラータイプ: {error['error_type']}\n")
            f.write(f"エラーメッセージ: {error['error_message']}\n")
            f.write(f"碑文テキスト: {error['inscription_text']}\n")
            f.write("-" * 80 + "\n\n")


def process_inscriptions(json_path, output_path, model_type='claude', api_key=None, limit=None):
    """
    碑文データを処理し、人物と経歴情報を抽出する

    Parameters:
    -----------
    json_path : str
        入力JSONファイルのパス
    output_path : str
        出力JSONファイルのパス
    model_type : str
        使用するモデル ('claude', 'gemini', 'gpt')
    api_key : str, optional
        APIキー（指定しない場合は環境変数から取得）
    limit : int, optional
        処理する碑文の最大数（テスト用）
    """
    # エラーログファイルのパスを生成
    error_log_path = output_path.replace('.json', '_errors.log')
    error_log = []
    pending_error_log = []  # チェックポイント保存用の一時バッファ

    # APIクライアントを初期化
    if model_type == 'claude':
        if api_key:
            client = Anthropic(api_key=api_key)
        else:
            client = Anthropic()  # 環境変数ANTHROPIC_API_KEYから取得
    elif model_type == 'gemini':
        if api_key:
            genai.configure(api_key=api_key)
        else:
            genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
        client = genai
    elif model_type == 'gpt':
        if api_key:
            client = OpenAI(api_key=api_key)
        else:
            client = OpenAI()  # 環境変数OPENAI_API_KEYから取得
    else:
        raise ValueError(f"Unknown model type: {model_type}. Choose from: claude, gemini, gpt")

    # 碑文データを読み込む
    print(f"碑文データを読み込み中: {json_path}")
    inscriptions = load_filtered_inscriptions(json_path)
    print(f"読み込み完了: {len(inscriptions)}件")

    # 既存の出力ファイルがあれば読み込んで、処理済みのEDCS-IDを取得
    processed_ids = set()
    results = []
    if os.path.exists(output_path):
        print(f"既存の出力ファイルを検出: {output_path}")
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                existing_results = json.load(f)
                results = existing_results  # 既存の結果を保持
                processed_ids = {item.get('edcs_id') for item in existing_results}
                print(f"処理済み: {len(processed_ids)}件")
        except json.JSONDecodeError:
            print(f"警告: 既存ファイルの読み込みに失敗しました。最初から処理します。")
            results = []
            processed_ids = set()

    # 既存のエラーログがあれば読み込む
    error_log = []
    if os.path.exists(error_log_path):
        print(f"既存のエラーログを検出: {error_log_path}")
        try:
            with open(error_log_path, 'r', encoding='utf-8') as f:
                # エラーログの既存エントリを読み込み（簡易的にEDCS-IDのみを抽出）
                content = f.read()
                # EDCS-IDを含む行を探して既存エラーを識別
                import re
                existing_error_ids = set(re.findall(r'EDCS-ID: (EDCS-\d+)', content))
                print(f"既存エラーログ: {len(existing_error_ids)}件")
                # エラーログはファイルから再構築せず、新規エラーのみを追記する形式に変更
        except Exception as e:
            print(f"警告: エラーログの読み込みに失敗しました: {e}")
            error_log = []

    # 処理する件数を制限
    if limit:
        inscriptions = inscriptions[:limit]
        print(f"処理件数を{limit}件に制限")

    # 未処理の碑文のみをフィルタリング
    unprocessed_inscriptions = [item for item in inscriptions if item.get('EDCS-ID') not in processed_ids]
    print(f"未処理: {len(unprocessed_inscriptions)}件")

    if len(unprocessed_inscriptions) == 0:
        print("全ての碑文が既に処理済みです。")
        return

    # 各碑文を処理
    checkpoint_interval = 10  # 10件ごとに保存
    #for i, item in enumerate(inscriptions, 1):
    # tqdmを使用して進捗表示（未処理のもののみ）
    total_items = len(inscriptions)
    for i, item in enumerate(tqdm(unprocessed_inscriptions, desc="Processing inscriptions"), 1):
        edcs_id = item.get('EDCS-ID', 'Unknown')
        inscription_text = item.get('inscription', '')

        # 全体の進捗を表示（処理済み + 現在の未処理）
        current_position = len(processed_ids) + i
        print(f"\n[{current_position}/{total_items}] 処理中: {edcs_id}")

        if not inscription_text or inscription_text.strip() == "?":
            print(f"  警告: 碑文テキストが空またはunknownです")
            results.append({
                "edcs_id": edcs_id,
                "person_name": "No Text",
                "person_name_readable": "No Text",
                "has_career": False,
                "career_path": [],
                "notes": "碑文テキストが存在しません",
                "original_data": item
            })

            # チェックポイント保存
            if len(results) % checkpoint_interval == 0 or i == len(unprocessed_inscriptions):
                print(f"  チェックポイント: {len(results)}件を保存中...")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

            continue

        # LLMで人物と経歴を抽出
        try:
            # 年代情報を取得
            dating_from = item.get('dating_from')
            dating_to = item.get('dating_to')

            result = extract_person_and_career(
                inscription_text,
                edcs_id,
                client,
                model_type,
                dating_from=dating_from,
                dating_to=dating_to
            )

            # エラーがあればログに記録し、結果には含めない
            if 'error' in result:
                error_entry = {
                    'edcs_id': edcs_id,
                    'error_type': 'Parse Error' if result['person_name'] == 'Parse Error' else 'LLM Error',
                    'error_message': result.get('notes', ''),
                    'inscription_text': inscription_text[:200] + '...' if len(inscription_text) > 200 else inscription_text
                }
                error_log.append(error_entry)
                pending_error_log.append(error_entry)
                print(f"  エラー: JSON解析エラーのため出力から除外します")

                # エラーログのチェックポイント保存
                if len(pending_error_log) >= checkpoint_interval or i == len(unprocessed_inscriptions):
                    print(f"  エラーログを保存中...")
                    save_error_log(error_log_path, pending_error_log, model_type, json_path)
                    pending_error_log = []  # バッファをクリア

                continue  # 結果リストに追加せずスキップ

            result['original_data'] = item  # 元データも保持
            results.append(result)

            # チェックポイント保存
            if len(results) % checkpoint_interval == 0 or i == len(unprocessed_inscriptions):
                print(f"  チェックポイント: {len(results)}件を保存中...")
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2)

            # 人物情報を表示
            persons = result.get('persons', [])
            person_relationships = result.get('person_relationships', [])
            if persons:
                print(f"  抽出人物数: {len(persons)}")
                for idx, person in enumerate(persons):
                    person_info = f"    [ID:{person.get('person_id', idx)}] {person.get('person_name_readable', 'Unknown')}"
                    if person.get('person_name_normalized'):
                        person_info += f" → {person.get('person_name_normalized')} ({person.get('person_name_link')})"
                    print(person_info)
                    print(f"        経歴: {len(person.get('career_path', []))}件, 恵与: {len(person.get('benefactions', []))}件")
                print(f"  関係性数: {len(person_relationships)}")
            else:
                # フォールバック（旧形式）
                person_info = f"  人物: {result.get('person_name_readable', 'Unknown')}"
                if result.get('person_name_normalized'):
                    person_info += f" → {result.get('person_name_normalized')} ({result.get('person_name_link')})"
                print(person_info)
                print(f"  経歴: {len(result.get('career_path', []))}件")
        except Exception as e:
            print(f"  エラー: {e}")
            # 例外エラーもログに記録し、結果には含めない
            error_entry = {
                'edcs_id': edcs_id,
                'error_type': 'Exception',
                'error_message': str(e),
                'inscription_text': inscription_text[:200] + '...' if len(inscription_text) > 200 else inscription_text
            }
            error_log.append(error_entry)
            pending_error_log.append(error_entry)

            # エラーログのチェックポイント保存
            if len(pending_error_log) >= checkpoint_interval or i == len(unprocessed_inscriptions):
                print(f"  エラーログを保存中...")
                save_error_log(error_log_path, pending_error_log, model_type, json_path)
                pending_error_log = []  # バッファをクリア

    # 結果を保存
    print(f"\n結果を保存中: {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 最後に残っているエラーログを保存
    if pending_error_log:
        print(f"最終エラーログを保存中...")
        save_error_log(error_log_path, pending_error_log, model_type, json_path)
        pending_error_log = []

    # 統計情報を表示
    print("\n" + "=" * 80)
    print("処理完了")
    print(f"総処理件数: {len(results)}")
    print(f"経歴情報あり: {sum(1 for r in results if r.get('has_career'))}")
    print(f"経歴情報なし: {sum(1 for r in results if not r.get('has_career'))}")
    print(f"エラー件数: {len(error_log)}")
    if error_log:
        print(f"エラーログファイル: {error_log_path}")
    print(f"結果ファイル: {output_path}")


if __name__ == "__main__":
    import sys
    import argparse

    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description='碑文から人物と経歴情報を抽出')
    parser.add_argument('--model', '-m', type=str, default='claude',
                        choices=['claude', 'gemini', 'gpt'],
                        help='使用するモデル (claude, gemini, gpt)')
    parser.add_argument('--api-key', '-k', type=str, default=None,
                        help='APIキー（指定しない場合は環境変数から取得）')
    parser.add_argument('--limit', '-l', type=int, default=10,
                        help='処理する碑文の最大数（デフォルト: 10）')
    parser.add_argument('--input', '-i', type=str,
                        default='filtered_data/2025-12-16-EDCS_via_Lat_Epig-prov_Africaproconsularis+place_Carthago-8520_filtered.json',
                        help='入力JSONファイルのパス')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='出力JSONファイルのパス（指定しない場合は自動生成）')

    args = parser.parse_args()

    # APIキーの確認
    api_key = args.api_key
    if not api_key:
        # 環境変数から取得を試みる
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
            print(f"エラー: {env_var_name}が設定されていません")
            print(f"\n以下のいずれかの方法でAPIキーを設定してください:")
            print(f"1. 環境変数を設定: export {env_var_name}='your-api-key'")
            print(f"2. コマンドライン引数: python extract_career_graph.py --model {args.model} --api-key your-api-key")
            sys.exit(1)

    # 出力ファイルパスを生成（モデルごとに分ける）
    if args.output is None:
        # 入力ファイルのパスから地名フォルダを抽出
        input_path_parts = args.input.split('/')
        place_folder = None

        # filtered_data/の後に地名フォルダがあるか確認
        if 'filtered_data' in input_path_parts:
            filtered_data_idx = input_path_parts.index('filtered_data')
            if filtered_data_idx + 1 < len(input_path_parts):
                place_folder = input_path_parts[filtered_data_idx + 1]

        # 入力ファイル名からベース名を動的に生成
        input_basename = os.path.basename(args.input)
        # '_filtered.json'や'_errors.json'を削除してベース名を取得
        if input_basename.endswith('_filtered.json'):
            base_name = input_basename.replace('_filtered.json', '')
        elif input_basename.endswith('_errors.json'):
            base_name = input_basename.replace('_errors.json', '')
        elif input_basename.endswith('.json'):
            base_name = input_basename.replace('.json', '')
        else:
            base_name = input_basename

        # 地名フォルダがある場合は、それを含めた構造で出力
        if place_folder:
            output_file = f'career_graphs/{args.model}/{place_folder}/{base_name}_career.json'
        else:
            output_file = f'career_graphs/{args.model}/{base_name}_career.json'
    else:
        output_file = args.output

    print(f"使用モデル: {args.model}")
    print(f"入力ファイル: {args.input}")
    print(f"出力ファイル: {output_file}")
    print(f"処理制限: {args.limit}件")
    print()

    # 処理実行
    process_inscriptions(
        args.input,
        output_file,
        model_type=args.model,
        api_key=api_key,
        limit=args.limit
    )
