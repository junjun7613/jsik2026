import json
import os
from rdflib import Graph, Namespace, Literal, URIRef, RDF, RDFS, XSD
from rdflib.namespace import DCTERMS, FOAF, SKOS
import argparse

def create_rdf_graph(json_path, output_path, format='turtle', pleiades_mapping_path=None):
    """
    JSONファイルから碑文のRDFグラフを作成する

    Parameters:
    -----------
    json_path : str
        入力JSONファイルのパス
    output_path : str
        出力RDFファイルのパス
    format : str
        RDFのシリアライゼーション形式 ('turtle', 'xml', 'n3', 'nt', 'json-ld')
    pleiades_mapping_path : str, optional
        地名とPleiades IDの対応表ファイルパス（JSON形式）
    """
    # 名前空間の定義
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

    # グラフの作成
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
    g.bind("dcterms", DCTERMS)
    g.bind("foaf", FOAF)
    g.bind("skos", SKOS)

    # Pleiades対応表の読み込み（オプション）
    pleiades_mapping = {}
    if pleiades_mapping_path and os.path.exists(pleiades_mapping_path):
        print(f"Pleiades対応表を読み込み中: {pleiades_mapping_path}")
        with open(pleiades_mapping_path, 'r', encoding='utf-8') as f:
            pleiades_mapping = json.load(f)
        print(f"Pleiades対応表読み込み完了: {len(pleiades_mapping)}件")

    # JSONデータの読み込み
    print(f"JSONデータを読み込み中: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print(f"読み込み完了: {len(data)}件")

    # 各碑文データを処理
    for item in data:
        edcs_id = item.get('edcs_id', 'Unknown')

        # 碑文のURIを作成
        inscription_uri = BASE[edcs_id]

        # 碑文の基本情報
        g.add((inscription_uri, RDF.type, EPIG.Inscription))
        g.add((inscription_uri, DCTERMS.identifier, Literal(edcs_id)))

        # 元データから追加情報を取得
        original_data = item.get('original_data', {})

        if original_data.get('province'):
            province_name = original_data['province']
            # スペースをアンダースコアに置換してIRI用の名前を作成
            province_name_iri = province_name.replace(' ', '_')
            province_uri = PROVINCE[province_name_iri]
            g.add((inscription_uri, EPIG.province, province_uri))
            g.add((province_uri, RDF.type, EPIG.Province))
            g.add((province_uri, RDFS.label, Literal(province_name)))

        if original_data.get('place'):
            place_name = original_data['place']
            # スペースをアンダースコアに置換してIRI用の名前を作成
            place_name_iri = place_name.replace(' ', '_')
            place_uri = PLACE[place_name_iri]
            g.add((inscription_uri, EPIG.place, place_uri))
            g.add((place_uri, RDF.type, EPIG.Place))
            g.add((place_uri, RDFS.label, Literal(place_name)))

            # Pleiades IDの追加（対応表にある場合）
            if place_name in pleiades_mapping:
                pleiades_id = pleiades_mapping[place_name]
                g.add((inscription_uri, EPIG.pleiadesId, Literal(pleiades_id)))
                print(f"  {edcs_id}: Pleiades ID {pleiades_id} を追加 (place: {place_name})")

        if original_data.get('dating_from'):
            g.add((inscription_uri, EPIG.datingFrom, Literal(int(original_data['dating_from']), datatype=XSD.integer)))

        if original_data.get('dating_to'):
            g.add((inscription_uri, EPIG.datingTo, Literal(int(original_data['dating_to']), datatype=XSD.integer)))

        if original_data.get('inscription'):
            g.add((inscription_uri, EPIG.text, Literal(original_data['inscription'])))

        if original_data.get('publication'):
            g.add((inscription_uri, DCTERMS.bibliographicCitation, Literal(original_data['publication'])))

        # 人物情報の取得（新形式を優先）
        persons = item.get('persons', [])

        # 後方互換性：persons配列がない場合はmain_personsから取得
        if not persons:
            main_persons = item.get('main_persons', [])
            if not main_persons:
                # さらに後方互換性：旧形式のデータの場合
                person_name = item.get('person_name', 'Unknown')
                if person_name not in ['Unknown', 'Parse Error', 'Error', 'No Text']:
                    main_persons = [{
                        'person_name': person_name,
                        'person_name_readable': item.get('person_name_readable', ''),
                        'person_name_normalized': item.get('person_name_normalized', ''),
                        'person_name_link': item.get('person_name_link', ''),
                        'social_status': item.get('social_status', ''),
                        'social_status_evidence': item.get('social_status_evidence', ''),
                        'has_career': item.get('has_career', False),
                        'career_path': item.get('career_path', []),
                        'benefactions': item.get('benefactions', [])
                    }]
            # main_personsをpersons形式に変換（person_idを追加）
            persons = []
            for idx, person in enumerate(main_persons):
                person_copy = person.copy()
                person_copy['person_id'] = idx
                persons.append(person_copy)

        # 各人物を処理
        for person_data in persons:
            person_name = person_data.get('person_name', 'Unknown')
            person_id = person_data.get('person_id', 0)

            # Parse Error, Error, No Textの場合のみスキップ（Unknownは処理する）
            if person_name in ['Parse Error', 'Error', 'No Text']:
                continue

            # 人物のURIを作成（person_idベース）
            person_uri = PERSON[f"{edcs_id}_person_{person_id}"]

            # 人物の基本情報
            g.add((person_uri, RDF.type, FOAF.Person))
            g.add((person_uri, FOAF.name, Literal(person_name)))

            person_name_readable = person_data.get('person_name_readable')
            if person_name_readable:
                g.add((person_uri, RDFS.label, Literal(person_name_readable)))

            # Tria nomina (Roman name structure)
            praenomen = person_data.get('praenomen')
            if praenomen:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                praenomen_iri = praenomen.replace(' ', '_')
                praenomen_uri = PRAENOMEN[praenomen_iri]
                g.add((person_uri, EPIG.praenomen, praenomen_uri))
                g.add((praenomen_uri, RDF.type, EPIG.Praenomen))
                g.add((praenomen_uri, RDFS.label, Literal(praenomen)))

            nomen = person_data.get('nomen')
            if nomen:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                nomen_iri = nomen.replace(' ', '_')
                nomen_uri = NOMEN[nomen_iri]
                g.add((person_uri, EPIG.nomen, nomen_uri))
                g.add((nomen_uri, RDF.type, EPIG.Nomen))
                g.add((nomen_uri, RDFS.label, Literal(nomen)))

            cognomen = person_data.get('cognomen')
            if cognomen:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                cognomen_iri = cognomen.replace(' ', '_')
                cognomen_uri = COGNOMEN[cognomen_iri]
                g.add((person_uri, EPIG.cognomen, cognomen_uri))
                g.add((cognomen_uri, RDF.type, EPIG.Cognomen))
                g.add((cognomen_uri, RDFS.label, Literal(cognomen)))

            # 皇帝の場合、正規化名とWikidata リンクを追加
            person_name_normalized = person_data.get('person_name_normalized')
            if person_name_normalized:
                g.add((person_uri, EPIG.normalizedName, Literal(person_name_normalized)))

            person_name_link = person_data.get('person_name_link')
            if person_name_link:
                wikidata_uri = URIRef(f"http://www.wikidata.org/entity/{person_name_link}")
                g.add((person_uri, EPIG.wikidataEntity, wikidata_uri))
                g.add((person_uri, SKOS.exactMatch, wikidata_uri))

            # 碑文と人物の関係
            g.add((inscription_uri, EPIG.mentions, person_uri))
            g.add((inscription_uri, EPIG.mainSubject, person_uri))

            # 社会的身分
            social_status = person_data.get('social_status', '')
            if social_status:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                social_status_iri = social_status.replace(' ', '_')
                status_uri = STATUS[social_status_iri]
                g.add((person_uri, EPIG.socialStatus, status_uri))
                g.add((status_uri, RDF.type, EPIG.SocialStatus))
                g.add((status_uri, RDFS.label, Literal(social_status)))

                social_status_evidence = person_data.get('social_status_evidence', '')
                if social_status_evidence:
                    g.add((status_uri, EPIG.evidence, Literal(social_status_evidence)))

            # 性別
            gender = person_data.get('gender', '')
            if gender and gender != 'unknown':
                g.add((person_uri, FOAF.gender, Literal(gender)))
                gender_evidence = person_data.get('gender_evidence', '')
                if gender_evidence:
                    g.add((person_uri, EPIG.genderEvidence, Literal(gender_evidence)))

            # 民族性
            ethnicity = person_data.get('ethnicity', '')
            if ethnicity:
                g.add((person_uri, EPIG.ethnicity, Literal(ethnicity)))
                ethnicity_evidence = person_data.get('ethnicity_evidence', '')
                if ethnicity_evidence:
                    g.add((person_uri, EPIG.ethnicityEvidence, Literal(ethnicity_evidence)))

            # 享年
            age_at_death = person_data.get('age_at_death', '')
            if age_at_death:
                try:
                    age_int = int(age_at_death)
                    g.add((person_uri, EPIG.ageAtDeath, Literal(age_int, datatype=XSD.integer)))
                except (ValueError, TypeError):
                    # 数値に変換できない場合は文字列として保存
                    g.add((person_uri, EPIG.ageAtDeath, Literal(age_at_death)))

                age_at_death_evidence = person_data.get('age_at_death_evidence', '')
                if age_at_death_evidence:
                    g.add((person_uri, EPIG.ageAtDeathEvidence, Literal(age_at_death_evidence)))

            # 経歴情報
            if person_data.get('has_career', False):
                career_path = person_data.get('career_path', [])

                # orderでソート
                career_path_sorted = sorted(career_path, key=lambda x: x.get('order', 0))

                previous_career_uri = None

                for career_item in career_path_sorted:
                    position = career_item.get('position', '')
                    order = career_item.get('order', 0)

                    # 経歴アイテムのURIを作成（person_idベース）
                    career_uri = CAREER[f"{edcs_id}_person_{person_id}_career_{order}"]

                    g.add((career_uri, RDF.type, EPIG.CareerPosition))
                    g.add((person_uri, EPIG.hasCareerPosition, career_uri))

                    if position:
                        g.add((career_uri, EPIG.position, Literal(position)))

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

                    # 前の経歴と接続（order順）
                    if previous_career_uri is not None:
                        g.add((previous_career_uri, EPIG.nextPosition, career_uri))
                        g.add((career_uri, EPIG.previousPosition, previous_career_uri))

                    previous_career_uri = career_uri

            # 恵与行為（エヴェルジェティズム）情報
            benefactions = person_data.get('benefactions', [])

            for idx, benef_item in enumerate(benefactions, 1):
                # 恵与行為のURIを作成（person_idベース）
                benefaction_uri = BENEF[f"{edcs_id}_person_{person_id}_benef_{idx}"]

                g.add((benefaction_uri, RDF.type, EPIG.Benefaction))
                g.add((person_uri, EPIG.hasBenefaction, benefaction_uri))
                g.add((inscription_uri, EPIG.mentions, benefaction_uri))

                benefaction_type = benef_item.get('benefaction_type', '')
                if benefaction_type:
                    g.add((benefaction_uri, EPIG.benefactionType, Literal(benefaction_type)))

                obj = benef_item.get('object', '')
                if obj:
                    g.add((benefaction_uri, EPIG.object, Literal(obj)))

                obj = benef_item.get('object_type', '')
                if obj:
                    g.add((benefaction_uri, EPIG.objectType, Literal(obj)))

                obj_description = benef_item.get('object_description', '')
                if obj_description:
                    g.add((benefaction_uri, DCTERMS.description, Literal(obj_description, lang='en')))

                benefaction_text = benef_item.get('benefaction_text', '')
                if benefaction_text:
                    g.add((benefaction_uri, EPIG.evidence, Literal(benefaction_text)))

                # コスト情報（元のテキスト）
                cost = benef_item.get('cost', '')
                if cost:
                    g.add((benefaction_uri, EPIG.cost, Literal(cost)))

                # 数値化されたコスト（元の通貨単位のまま）
                cost_numeric = benef_item.get('cost_numeric')
                if cost_numeric is not None:
                    try:
                        cost_int = int(cost_numeric)
                        g.add((benefaction_uri, EPIG.costNumeric, Literal(cost_int, datatype=XSD.integer)))
                    except (ValueError, TypeError):
                        # 数値に変換できない場合はスキップ
                        pass

                # コストの単位（sestercesまたはdenarii）
                cost_unit = benef_item.get('cost_unit', '')
                if cost_unit:
                    g.add((benefaction_uri, EPIG.costUnit, Literal(cost_unit)))

                benef_notes = benef_item.get('notes', '')
                if benef_notes:
                    g.add((benefaction_uri, RDFS.comment, Literal(benef_notes)))

        # コミュニティ情報
        communities = item.get('communities', [])

        for community_data in communities:
            community_id = community_data.get('community_id', 0)
            community_name = community_data.get('community_name', '')

            if not community_name:
                continue

            # コミュニティのURIを作成（community_idベース）
            community_uri = COMMUNITY[f"{edcs_id}_community_{community_id}"]

            # コミュニティの基本情報
            g.add((community_uri, RDF.type, EPIG.Community))
            g.add((community_uri, RDFS.label, Literal(community_name)))
            g.add((inscription_uri, EPIG.mentions, community_uri))

            # 正規化名
            community_name_normalized = community_data.get('community_name_normalized', '')
            if community_name_normalized:
                g.add((community_uri, EPIG.normalizedName, Literal(community_name_normalized)))

            # コミュニティタイプ
            community_type = community_data.get('community_type', '')
            if community_type:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                community_type_iri = community_type.replace(' ', '_')
                comm_type_uri = COMMTYPE[community_type_iri]
                g.add((community_uri, EPIG.communityType, comm_type_uri))
                g.add((comm_type_uri, RDF.type, EPIG.CommunityType))
                g.add((comm_type_uri, RDFS.label, Literal(community_type)))

            # 説明
            community_description = community_data.get('community_description', '')
            if community_description:
                g.add((community_uri, DCTERMS.description, Literal(community_description, lang='en')))

            # エビデンス
            evidence = community_data.get('evidence', '')
            if evidence:
                g.add((community_uri, EPIG.evidence, Literal(evidence)))

        # 関係性情報（新形式を優先、後方互換性あり）
        person_relationships = item.get('person_relationships', item.get('relationships', []))

        for idx, rel_item in enumerate(person_relationships, 1):
            rel_type = rel_item.get('type', '')
            rel_property = rel_item.get('property', '')

            # 新形式: source_person_id、target_person_id、target_community_idを使用
            source_person_id = rel_item.get('source_person_id')
            target_person_id = rel_item.get('target_person_id')
            target_community_id = rel_item.get('target_community_id')

            # 後方互換性: 古い形式のsource_person_indexとtarget_person_indexもサポート
            if source_person_id is None:
                source_person_id = rel_item.get('source_person_index', 0)
            if target_person_id is None:
                target_person_id = rel_item.get('target_person_index')

            # person_idからperson URIを取得
            source_person_uri = PERSON[f"{edcs_id}_person_{source_person_id}"]

            # target_uriを決定（person、community、または旧形式）
            target_uri = None

            # target_community_idが指定されている場合（affiliation）
            if target_community_id is not None:
                target_uri = COMMUNITY[f"{edcs_id}_community_{target_community_id}"]
            # target_person_idが指定されている場合（person-to-person）
            elif target_person_id is not None:
                target_uri = PERSON[f"{edcs_id}_person_{target_person_id}"]
            else:
                # 旧形式：target_person_nameから新しいリソースを作成
                target_person_name = rel_item.get('target_person_name', rel_item.get('person_name', ''))
                if not target_person_name:
                    continue

                target_uri = PERSON[f"{edcs_id}_rel_{idx}"]
                g.add((target_uri, RDF.type, FOAF.Person))
                g.add((target_uri, FOAF.name, Literal(target_person_name)))

                # 旧形式の追加情報を処理
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
                    # スペースをアンダースコアに置換してIRI用の名前を作成
                    target_status_iri = target_status.replace(' ', '_')
                    target_status_uri = STATUS[target_status_iri]
                    g.add((target_uri, EPIG.socialStatus, target_status_uri))
                    g.add((target_status_uri, RDF.type, EPIG.SocialStatus))
                    g.add((target_status_uri, RDFS.label, Literal(target_status)))

                    target_status_evidence = rel_item.get('social_status_evidence', '')
                    if target_status_evidence:
                        g.add((target_status_uri, EPIG.evidence, Literal(target_status_evidence)))

                g.add((inscription_uri, EPIG.mentions, target_uri))

            # 関係のURIを作成
            relationship_uri = REL[f"{edcs_id}_rel_{idx}"]

            g.add((relationship_uri, RDF.type, EPIG.Relationship))

            # relationshipTypeをURIとして扱う
            if rel_type:
                # スペースをアンダースコアに置換してIRI用の名前を作成
                rel_type_iri = rel_type.replace(' ', '_')
                rel_type_uri = RELTYPE[rel_type_iri]
                g.add((relationship_uri, EPIG.relationshipType, rel_type_uri))
                g.add((rel_type_uri, RDF.type, EPIG.RelationshipType))
                g.add((rel_type_uri, RDFS.label, Literal(rel_type)))

            g.add((relationship_uri, EPIG.relationshipProperty, Literal(rel_property)))

            # 碑文とrelationshipの関係
            g.add((inscription_uri, EPIG.mentions, relationship_uri))

            # 関係の方向性
            g.add((relationship_uri, EPIG.source, source_person_uri))
            g.add((relationship_uri, EPIG.target, target_uri))

            # プロパティに基づいた直接的な関係も追加
            if rel_type == 'family':
                # 家族関係の直接リンク（person-to-personの場合のみ）
                if target_person_id is not None and rel_property in ['father', 'mother', 'son', 'daughter', 'brother', 'sister']:
                    relation_property = EPIG[f"has{rel_property.capitalize()}"]
                    g.add((source_person_uri, relation_property, target_uri))
            elif rel_type == 'affiliation':
                # affiliation関係の直接リンク（person-to-communityの場合）
                if target_community_id is not None:
                    g.add((source_person_uri, EPIG.affiliatedWith, target_uri))

            property_text = rel_item.get('property_text', '')
            if property_text:
                g.add((relationship_uri, EPIG.evidence, Literal(property_text)))

            notes = rel_item.get('notes', '')
            if notes:
                g.add((relationship_uri, RDFS.comment, Literal(notes)))

        # 全体のノート
        notes = item.get('notes', '')
        if notes:
            g.add((inscription_uri, RDFS.comment, Literal(notes)))

    # RDFファイルとして保存
    print(f"\nRDFデータを保存中: {output_path}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    g.serialize(destination=output_path, format=format)

    # 統計情報
    print("\n" + "=" * 80)
    print("RDF生成完了")
    print(f"総トリプル数: {len(g)}")
    print(f"人物数: {len(list(g.subjects(RDF.type, FOAF.Person)))}")
    print(f"コミュニティ数: {len(list(g.subjects(RDF.type, EPIG.Community)))}")
    print(f"碑文数: {len(list(g.subjects(RDF.type, EPIG.Inscription)))}")
    print(f"経歴位置数: {len(list(g.subjects(RDF.type, EPIG.CareerPosition)))}")
    print(f"恵与行為数: {len(list(g.subjects(RDF.type, EPIG.Benefaction)))}")
    print(f"関係性数: {len(list(g.subjects(RDF.type, EPIG.Relationship)))}")
    print(f"出力形式: {format}")
    print(f"出力ファイル: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='JSONからRDFデータを生成')
    parser.add_argument('--input', '-i', type=str, required=True,
                        help='入力JSONファイルのパス')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='出力RDFファイルのパス（指定しない場合は自動生成）')
    parser.add_argument('--format', '-f', type=str, default='turtle',
                        choices=['turtle', 'xml', 'n3', 'nt', 'json-ld'],
                        help='RDFのシリアライゼーション形式（デフォルト: turtle）')
    parser.add_argument('--pleiades-mapping', '-p', type=str, default='pipeline/place_pleiades_mapping.json',
                        help='地名とPleiades IDの対応表ファイルパス（JSON形式、デフォルト: pipeline/place_pleiades_mapping.json）')

    args = parser.parse_args()

    # 出力ファイルパスを生成
    if args.output is None:
        input_basename = os.path.basename(args.input)
        base_name = input_basename.replace('_career.json', '').replace('.json', '')

        # フォーマットに応じた拡張子
        extension_map = {
            'turtle': '.ttl',
            'xml': '.rdf',
            'n3': '.n3',
            'nt': '.nt',
            'json-ld': '.jsonld'
        }
        extension = extension_map.get(args.format, '.ttl')

        # 入力ファイルのディレクトリ構造を保持
        input_path_parts = args.input.split('/')
        model_folder = None
        place_folder = None

        # career_graphs/の後にモデル名フォルダと地名フォルダがあるか確認
        if 'career_graphs' in input_path_parts:
            career_graphs_idx = input_path_parts.index('career_graphs')
            # career_graphs/model/place/ の構造を想定
            if career_graphs_idx + 1 < len(input_path_parts):
                model_folder = input_path_parts[career_graphs_idx + 1]
            if career_graphs_idx + 2 < len(input_path_parts):
                place_folder = input_path_parts[career_graphs_idx + 2]

        # 出力ディレクトリの構造を決定
        if model_folder and place_folder:
            # career_graphs/model/place/ → rdf_graphs/model/place/
            output_dir = f'rdf_graphs/{model_folder}/{place_folder}'
        elif model_folder:
            # career_graphs/model/ → rdf_graphs/model/
            output_dir = f'rdf_graphs/{model_folder}'
        else:
            output_dir = 'rdf_graphs'

        output_path = f'{output_dir}/{base_name}{extension}'
    else:
        output_path = args.output

    print(f"入力ファイル: {args.input}")
    print(f"出力ファイル: {output_path}")
    print(f"RDF形式: {args.format}")
    if args.pleiades_mapping:
        print(f"Pleiades対応表: {args.pleiades_mapping}")
    print()

    create_rdf_graph(args.input, output_path, format=args.format,
                     pleiades_mapping_path=args.pleiades_mapping)
