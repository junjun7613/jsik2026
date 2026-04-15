"""
碑文データのオントロジーを生成するスクリプト

extract_career_graph.pyのプロンプトとRDFデータから
OWL/RDFS形式のオントロジーを自動生成します。
"""

from rdflib import Graph, Namespace, RDF, RDFS, OWL, XSD, Literal, URIRef
import os

def create_epigraphy_ontology(output_path='ontology/epigraphy_ontology.ttl'):
    """
    碑文学データのオントロジーを作成する

    Parameters:
    -----------
    output_path : str
        出力オントロジーファイルのパス
    """
    # 名前空間の定義
    EPIG = Namespace("http://example.org/epigraphy/")
    FOAF = Namespace("http://xmlns.com/foaf/0.1/")
    DCTERMS = Namespace("http://purl.org/dc/terms/")
    SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

    # グラフの作成
    g = Graph()
    g.bind("epig", EPIG)
    g.bind("foaf", FOAF)
    g.bind("dcterms", DCTERMS)
    g.bind("skos", SKOS)
    g.bind("owl", OWL)
    g.bind("rdfs", RDFS)

    # オントロジーの基本情報
    ontology_uri = EPIG["ontology"]
    g.add((ontology_uri, RDF.type, OWL.Ontology))
    g.add((ontology_uri, RDFS.label, Literal("Epigraphy Ontology", lang="en")))
    g.add((ontology_uri, RDFS.label, Literal("碑文学オントロジー", lang="ja")))
    g.add((ontology_uri, RDFS.comment, Literal(
        "An ontology for representing Roman inscriptions, including persons, careers, benefactions, communities, and relationships.",
        lang="en"
    )))
    g.add((ontology_uri, DCTERMS.created, Literal("2025-12-19", datatype=XSD.date)))
    g.add((ontology_uri, OWL.versionInfo, Literal("1.0")))

    # ========================================
    # クラスの定義
    # ========================================

    # Inscription Class
    g.add((EPIG.Inscription, RDF.type, OWL.Class))
    g.add((EPIG.Inscription, RDFS.label, Literal("Inscription", lang="en")))
    g.add((EPIG.Inscription, RDFS.label, Literal("碑文", lang="ja")))
    g.add((EPIG.Inscription, RDFS.comment, Literal(
        "A Latin inscription from the Roman period",
        lang="en"
    )))

    # Person Class (use FOAF:Person)
    g.add((FOAF.Person, RDF.type, OWL.Class))
    g.add((FOAF.Person, RDFS.label, Literal("Person", lang="en")))
    g.add((FOAF.Person, RDFS.label, Literal("人物", lang="ja")))

    # Community Class
    g.add((EPIG.Community, RDF.type, OWL.Class))
    g.add((EPIG.Community, RDFS.label, Literal("Community", lang="en")))
    g.add((EPIG.Community, RDFS.label, Literal("集団", lang="ja")))
    g.add((EPIG.Community, RDFS.comment, Literal(
        "A group, organization, or community mentioned in inscriptions (e.g., legion, city, collegium)",
        lang="en"
    )))

    # CommunityType Class
    g.add((EPIG.CommunityType, RDF.type, OWL.Class))
    g.add((EPIG.CommunityType, RDFS.label, Literal("Community Type", lang="en")))
    g.add((EPIG.CommunityType, RDFS.label, Literal("集団タイプ", lang="ja")))
    g.add((EPIG.CommunityType, RDFS.comment, Literal(
        "Type of community: legion, city, collegium, etc.",
        lang="en"
    )))

    # SocialStatus Class
    g.add((EPIG.SocialStatus, RDF.type, OWL.Class))
    g.add((EPIG.SocialStatus, RDFS.label, Literal("Social Status", lang="en")))
    g.add((EPIG.SocialStatus, RDFS.label, Literal("社会的身分", lang="ja")))
    g.add((EPIG.SocialStatus, RDFS.comment, Literal(
        "Social status of a person (e.g., senator, equestrian, decurion, freedman)",
        lang="en"
    )))

    # CareerPosition Class
    g.add((EPIG.CareerPosition, RDF.type, OWL.Class))
    g.add((EPIG.CareerPosition, RDFS.label, Literal("CareerPosition", lang="en")))
    g.add((EPIG.CareerPosition, RDFS.label, Literal("経歴職位", lang="ja")))
    g.add((EPIG.CareerPosition, RDFS.comment, Literal(
        "A position or office held by a person during their career",
        lang="en"
    )))

    # Benefaction Class
    g.add((EPIG.Benefaction, RDF.type, OWL.Class))
    g.add((EPIG.Benefaction, RDFS.label, Literal("Benefaction", lang="en")))
    g.add((EPIG.Benefaction, RDFS.label, Literal("恵与行為", lang="ja")))
    g.add((EPIG.Benefaction, RDFS.comment, Literal(
        "An act of public benefaction (evergetism) such as construction, donation, or games",
        lang="en"
    )))

    # Relationship Class
    g.add((EPIG.Relationship, RDF.type, OWL.Class))
    g.add((EPIG.Relationship, RDFS.label, Literal("Relationship", lang="en")))
    g.add((EPIG.Relationship, RDFS.label, Literal("関係性", lang="ja")))
    g.add((EPIG.Relationship, RDFS.comment, Literal(
        "A relationship between persons or between a person and a community",
        lang="en"
    )))

    # RelationshipType Class
    g.add((EPIG.RelationshipType, RDF.type, OWL.Class))
    g.add((EPIG.RelationshipType, RDFS.label, Literal("RelationshipType", lang="en")))
    g.add((EPIG.RelationshipType, RDFS.label, Literal("関係性タイプ", lang="ja")))
    g.add((EPIG.RelationshipType, RDFS.comment, Literal(
        "Type of relationship: family, colleague, patronage, dedication, economic, affiliation",
        lang="en"
    )))

    # Place Class
    g.add((EPIG.Place, RDF.type, OWL.Class))
    g.add((EPIG.Place, RDFS.label, Literal("Place", lang="en")))
    g.add((EPIG.Place, RDFS.label, Literal("場所", lang="ja")))

    # Province Class
    g.add((EPIG.Province, RDF.type, OWL.Class))
    g.add((EPIG.Province, RDFS.label, Literal("Province", lang="en")))
    g.add((EPIG.Province, RDFS.label, Literal("属州", lang="ja")))

    # ========================================
    # Object Properties (関係性プロパティ)
    # ========================================

    # mentions
    g.add((EPIG.mentions, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.mentions, RDFS.label, Literal("mentions", lang="en")))
    g.add((EPIG.mentions, RDFS.label, Literal("言及する", lang="ja")))
    g.add((EPIG.mentions, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.mentions, RDFS.comment, Literal(
        "Relates an inscription to an entity (person, community, relationship, benefaction) mentioned in it",
        lang="en"
    )))

    # mainSubject
    g.add((EPIG.mainSubject, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.mainSubject, RDFS.label, Literal("mainSubject", lang="en")))
    g.add((EPIG.mainSubject, RDFS.label, Literal("主題", lang="ja")))
    g.add((EPIG.mainSubject, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.mainSubject, RDFS.range, FOAF.Person))
    g.add((EPIG.mainSubject, RDFS.subPropertyOf, EPIG.mentions))

    # socialStatus
    g.add((EPIG.socialStatus, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.socialStatus, RDFS.label, Literal("socialStatus", lang="en")))
    g.add((EPIG.socialStatus, RDFS.label, Literal("社会的身分", lang="ja")))
    g.add((EPIG.socialStatus, RDFS.domain, FOAF.Person))
    g.add((EPIG.socialStatus, RDFS.range, EPIG.SocialStatus))

    # hasCareerPosition
    g.add((EPIG.hasCareerPosition, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.hasCareerPosition, RDFS.label, Literal("hasCareerPosition", lang="en")))
    g.add((EPIG.hasCareerPosition, RDFS.label, Literal("経歴職位を持つ", lang="ja")))
    g.add((EPIG.hasCareerPosition, RDFS.domain, FOAF.Person))
    g.add((EPIG.hasCareerPosition, RDFS.range, EPIG.CareerPosition))

    # hasBenefaction
    g.add((EPIG.hasBenefaction, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.hasBenefaction, RDFS.label, Literal("hasBenefaction", lang="en")))
    g.add((EPIG.hasBenefaction, RDFS.label, Literal("恵与行為を行う", lang="ja")))
    g.add((EPIG.hasBenefaction, RDFS.domain, FOAF.Person))
    g.add((EPIG.hasBenefaction, RDFS.range, EPIG.Benefaction))

    # affiliatedWith
    g.add((EPIG.affiliatedWith, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.affiliatedWith, RDFS.label, Literal("affiliatedWith", lang="en")))
    g.add((EPIG.affiliatedWith, RDFS.label, Literal("所属する", lang="ja")))
    g.add((EPIG.affiliatedWith, RDFS.domain, FOAF.Person))
    g.add((EPIG.affiliatedWith, RDFS.range, EPIG.Community))

    # communityType
    g.add((EPIG.communityType, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.communityType, RDFS.label, Literal("communityType", lang="en")))
    g.add((EPIG.communityType, RDFS.label, Literal("集団タイプ", lang="ja")))
    g.add((EPIG.communityType, RDFS.domain, EPIG.Community))
    g.add((EPIG.communityType, RDFS.range, EPIG.CommunityType))

    # relationshipType
    g.add((EPIG.relationshipType, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.relationshipType, RDFS.label, Literal("relationshipType", lang="en")))
    g.add((EPIG.relationshipType, RDFS.label, Literal("関係性タイプ", lang="ja")))
    g.add((EPIG.relationshipType, RDFS.domain, EPIG.Relationship))
    g.add((EPIG.relationshipType, RDFS.range, EPIG.RelationshipType))

    # source, target (for relationships)
    g.add((EPIG.source, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.source, RDFS.label, Literal("source", lang="en")))
    g.add((EPIG.source, RDFS.label, Literal("起点", lang="ja")))
    g.add((EPIG.source, RDFS.domain, EPIG.Relationship))
    g.add((EPIG.source, RDFS.range, FOAF.Person))

    g.add((EPIG.target, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.target, RDFS.label, Literal("target", lang="en")))
    g.add((EPIG.target, RDFS.label, Literal("対象", lang="ja")))
    g.add((EPIG.target, RDFS.domain, EPIG.Relationship))

    # Career sequence properties
    g.add((EPIG.nextPosition, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.nextPosition, RDFS.label, Literal("nextPosition", lang="en")))
    g.add((EPIG.nextPosition, RDFS.label, Literal("次の職位", lang="ja")))
    g.add((EPIG.nextPosition, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.nextPosition, RDFS.range, EPIG.CareerPosition))

    g.add((EPIG.previousPosition, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.previousPosition, RDFS.label, Literal("previousPosition", lang="en")))
    g.add((EPIG.previousPosition, RDFS.label, Literal("前の職位", lang="ja")))
    g.add((EPIG.previousPosition, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.previousPosition, RDFS.range, EPIG.CareerPosition))
    g.add((EPIG.previousPosition, OWL.inverseOf, EPIG.nextPosition))

    # Family relationship properties
    for relation in ['Father', 'Mother', 'Son', 'Daughter', 'Brother', 'Sister']:
        prop = EPIG[f"has{relation}"]
        g.add((prop, RDF.type, OWL.ObjectProperty))
        g.add((prop, RDFS.label, Literal(f"has{relation}", lang="en")))
        g.add((prop, RDFS.domain, FOAF.Person))
        g.add((prop, RDFS.range, FOAF.Person))
        g.add((prop, RDFS.subPropertyOf, FOAF.knows))

    # Geographic properties
    g.add((EPIG.province, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.province, RDFS.label, Literal("province", lang="en")))
    g.add((EPIG.province, RDFS.label, Literal("属州", lang="ja")))
    g.add((EPIG.province, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.province, RDFS.range, EPIG.Province))

    g.add((EPIG.place, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.place, RDFS.label, Literal("place", lang="en")))
    g.add((EPIG.place, RDFS.label, Literal("場所", lang="ja")))
    g.add((EPIG.place, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.place, RDFS.range, EPIG.Place))

    # Wikidata link
    g.add((EPIG.wikidataEntity, RDF.type, OWL.ObjectProperty))
    g.add((EPIG.wikidataEntity, RDFS.label, Literal("wikidataEntity", lang="en")))
    g.add((EPIG.wikidataEntity, RDFS.label, Literal("Wikidataエンティティ", lang="ja")))
    g.add((EPIG.wikidataEntity, RDFS.domain, FOAF.Person))

    # ========================================
    # Datatype Properties (データプロパティ)
    # ========================================

    # Text content
    g.add((EPIG.text, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.text, RDFS.label, Literal("text", lang="en")))
    g.add((EPIG.text, RDFS.label, Literal("テキスト", lang="ja")))
    g.add((EPIG.text, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.text, RDFS.range, XSD.string))

    # Dating
    g.add((EPIG.datingFrom, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.datingFrom, RDFS.label, Literal("datingFrom", lang="en")))
    g.add((EPIG.datingFrom, RDFS.label, Literal("年代開始", lang="ja")))
    g.add((EPIG.datingFrom, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.datingFrom, RDFS.range, XSD.integer))

    g.add((EPIG.datingTo, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.datingTo, RDFS.label, Literal("datingTo", lang="en")))
    g.add((EPIG.datingTo, RDFS.label, Literal("年代終了", lang="ja")))
    g.add((EPIG.datingTo, RDFS.domain, EPIG.Inscription))
    g.add((EPIG.datingTo, RDFS.range, XSD.integer))

    # Person properties
    g.add((EPIG.normalizedName, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.normalizedName, RDFS.label, Literal("normalizedName", lang="en")))
    g.add((EPIG.normalizedName, RDFS.label, Literal("正規化名", lang="ja")))
    g.add((EPIG.normalizedName, RDFS.range, XSD.string))

    g.add((EPIG.ethnicity, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.ethnicity, RDFS.label, Literal("ethnicity", lang="en")))
    g.add((EPIG.ethnicity, RDFS.label, Literal("民族性", lang="ja")))
    g.add((EPIG.ethnicity, RDFS.domain, FOAF.Person))
    g.add((EPIG.ethnicity, RDFS.range, XSD.string))

    g.add((EPIG.ageAtDeath, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.ageAtDeath, RDFS.label, Literal("ageAtDeath", lang="en")))
    g.add((EPIG.ageAtDeath, RDFS.label, Literal("享年", lang="ja")))
    g.add((EPIG.ageAtDeath, RDFS.domain, FOAF.Person))
    g.add((EPIG.ageAtDeath, RDFS.range, XSD.integer))

    # Evidence properties
    g.add((EPIG.evidence, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.evidence, RDFS.label, Literal("evidence", lang="en")))
    g.add((EPIG.evidence, RDFS.label, Literal("根拠", lang="ja")))
    g.add((EPIG.evidence, RDFS.range, XSD.string))
    g.add((EPIG.evidence, RDFS.comment, Literal(
        "Text evidence from the inscription supporting this claim",
        lang="en"
    )))

    g.add((EPIG.genderEvidence, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.genderEvidence, RDFS.label, Literal("genderEvidence", lang="en")))
    g.add((EPIG.genderEvidence, RDFS.label, Literal("性別の根拠", lang="ja")))
    g.add((EPIG.genderEvidence, RDFS.domain, FOAF.Person))
    g.add((EPIG.genderEvidence, RDFS.range, XSD.string))

    g.add((EPIG.ethnicityEvidence, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.ethnicityEvidence, RDFS.label, Literal("ethnicityEvidence", lang="en")))
    g.add((EPIG.ethnicityEvidence, RDFS.label, Literal("民族性の根拠", lang="ja")))
    g.add((EPIG.ethnicityEvidence, RDFS.domain, FOAF.Person))
    g.add((EPIG.ethnicityEvidence, RDFS.range, XSD.string))

    g.add((EPIG.ageAtDeathEvidence, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.ageAtDeathEvidence, RDFS.label, Literal("ageAtDeathEvidence", lang="en")))
    g.add((EPIG.ageAtDeathEvidence, RDFS.label, Literal("享年の根拠", lang="ja")))
    g.add((EPIG.ageAtDeathEvidence, RDFS.domain, FOAF.Person))
    g.add((EPIG.ageAtDeathEvidence, RDFS.range, XSD.string))

    # Career position properties
    g.add((EPIG.position, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.position, RDFS.label, Literal("position", lang="en")))
    g.add((EPIG.position, RDFS.label, Literal("職位", lang="ja")))
    g.add((EPIG.position, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.position, RDFS.range, XSD.string))

    g.add((EPIG.positionNormalized, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.positionNormalized, RDFS.label, Literal("positionNormalized", lang="en")))
    g.add((EPIG.positionNormalized, RDFS.label, Literal("職位（正規化）", lang="ja")))
    g.add((EPIG.positionNormalized, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.positionNormalized, RDFS.range, XSD.string))

    g.add((EPIG.positionAbstract, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.positionAbstract, RDFS.label, Literal("positionAbstract", lang="en")))
    g.add((EPIG.positionAbstract, RDFS.label, Literal("職位（抽象形）", lang="ja")))
    g.add((EPIG.positionAbstract, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.positionAbstract, RDFS.range, XSD.string))

    g.add((EPIG.positionType, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.positionType, RDFS.label, Literal("positionType", lang="en")))
    g.add((EPIG.positionType, RDFS.label, Literal("職位タイプ", lang="ja")))
    g.add((EPIG.positionType, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.positionType, RDFS.range, XSD.string))

    g.add((EPIG.order, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.order, RDFS.label, Literal("order", lang="en")))
    g.add((EPIG.order, RDFS.label, Literal("順序", lang="ja")))
    g.add((EPIG.order, RDFS.domain, EPIG.CareerPosition))
    g.add((EPIG.order, RDFS.range, XSD.integer))

    # Benefaction properties
    g.add((EPIG.benefactionType, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.benefactionType, RDFS.label, Literal("benefactionType", lang="en")))
    g.add((EPIG.benefactionType, RDFS.label, Literal("恵与タイプ", lang="ja")))
    g.add((EPIG.benefactionType, RDFS.domain, EPIG.Benefaction))
    g.add((EPIG.benefactionType, RDFS.range, XSD.string))

    g.add((EPIG.object, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.object, RDFS.label, Literal("object", lang="en")))
    g.add((EPIG.object, RDFS.label, Literal("対象物", lang="ja")))
    g.add((EPIG.object, RDFS.domain, EPIG.Benefaction))
    g.add((EPIG.object, RDFS.range, XSD.string))

    g.add((EPIG.objectType, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.objectType, RDFS.label, Literal("objectType", lang="en")))
    g.add((EPIG.objectType, RDFS.label, Literal("対象物タイプ", lang="ja")))
    g.add((EPIG.objectType, RDFS.domain, EPIG.Benefaction))
    g.add((EPIG.objectType, RDFS.range, XSD.string))

    g.add((EPIG.cost, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.cost, RDFS.label, Literal("cost", lang="en")))
    g.add((EPIG.cost, RDFS.label, Literal("費用", lang="ja")))
    g.add((EPIG.cost, RDFS.domain, EPIG.Benefaction))
    g.add((EPIG.cost, RDFS.range, XSD.string))

    # Relationship properties
    g.add((EPIG.relationshipProperty, RDF.type, OWL.DatatypeProperty))
    g.add((EPIG.relationshipProperty, RDFS.label, Literal("relationshipProperty", lang="en")))
    g.add((EPIG.relationshipProperty, RDFS.label, Literal("関係性プロパティ", lang="ja")))
    g.add((EPIG.relationshipProperty, RDFS.domain, EPIG.Relationship))
    g.add((EPIG.relationshipProperty, RDFS.range, XSD.string))

    # ========================================
    # オントロジーの保存
    # ========================================

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    g.serialize(destination=output_path, format='turtle')

    # OWL/XML形式でも保存
    owl_path = output_path.replace('.ttl', '.owl')
    g.serialize(destination=owl_path, format='xml')

    # 統計情報
    print("=" * 80)
    print("オントロジー生成完了")
    print(f"クラス数: {len(list(g.subjects(RDF.type, OWL.Class)))}")
    print(f"ObjectProperty数: {len(list(g.subjects(RDF.type, OWL.ObjectProperty)))}")
    print(f"DatatypeProperty数: {len(list(g.subjects(RDF.type, OWL.DatatypeProperty)))}")
    print(f"出力ファイル (Turtle): {output_path}")
    print(f"出力ファイル (OWL/XML): {owl_path}")
    print("=" * 80)

    return g


if __name__ == "__main__":
    # オントロジー生成
    create_epigraphy_ontology()
