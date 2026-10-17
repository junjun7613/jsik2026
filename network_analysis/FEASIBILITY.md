# 北アフリカ碑文ナレッジグラフ — ネットワーク分析 実現可能性調査

調査日: 2026-10-05
対象データ: `pipeline/provenance/validated_career_graphs/claude/`
調査方法: 全2,042ファイルを実際にパースして全件集計（サンプリングなし）

---

## 1. 結論（要約）

提案された4タスク（グラフ化 / 分析エンジン / 動的サブグラフ抽出 / 可視化）は、
**いずれも技術的には実装可能**。NetworkXへの変換、中心性計算、コミュニティ抽出、
PyVis可視化のいずれにもデータ側の障害はない。

ただし、**ドキュメントの想定どおりの形で「歴史的インサイト」まで到達できるのは
以下の2つに限られる**:

- 役職遷移ネットワーク（テーマB） — ただし皇帝・皇族の除外が必須
- 恵与対象の Object–Object 投影（テーマA の一部）

残りは前提作業（§5）を先に片付けないと、結果が出ないか、出ても解釈できない。

---

## 2. 実測されたデータ規模

| 項目 | 件数 |
|---|---:|
| ファイル数 | 2,042 |
| 碑文レコード | 56,918 |
| 人物言及（person reference） | 85,118 |
| うち経歴あり | 10,500 |
| うち **2役職以上**（遷移エッジが作れる） | **3,571** |
| 恵与行為（benefaction） | 6,932 |
| 恵与を行った人物 | 6,015 |
| `cost_numeric` が入っている恵与 | 512 |
| 人物間関係（person_relationships） | 30,321 |
| 年代が数値で確定 | **9,906（17%）** |
| 年代未確定 | 47,012（83%） |

### 碑文数 上位10地点

| 属州 | 地名 | 碑文数 |
|---|---|---:|
| Africa proconsularis | Carthago | 9,082 |
| Numidia | Lambaesis | 2,626 |
| Africa proconsularis | Dougga / Thugga | 2,087 |
| Numidia | Sid | 2,057 |
| Numidia | Cirta (Constantine) | 1,701 |
| Numidia | Thibilis (Sellaoua Announa) | 1,516 |
| Numidia | Thibilis | 1,515 |
| Numidia | Celtianis (El Meraba) | 1,309 |
| Africa proconsularis | Ammaedara (Haydrah) | 1,236 |
| Africa proconsularis | Thullium (Ksar Beni Fredj) | 943 |

---

## 3. 実データ構造 vs ドキュメントの想定

ドキュメント §4 が想定する `nodes[]` / `edges[]` のフラット構造とは **実データが異なる**。

実際の構造（碑文1件 = 1レコード、トップレベルは配列）:

```
record
├── edcs_id
├── persons[]
│   ├── person_id, person_name, person_name_normalized, person_name_link
│   ├── social_status, gender, ethnicity, age_at_death
│   ├── divinity, divinity_type            （enrich で付与）
│   ├── career_path[]
│   │   ├── position, position_normalized, position_abstract
│   │   ├── position_type, order
│   │   └── location, location_normalized  （enrich で付与）
│   ├── benefactions[]
│   │   ├── benefaction_type, object, object_type, benefaction_text
│   │   ├── cost, cost_numeric, cost_unit  （enrich で付与）
│   │   ├── objects[]                      （enrich で付与）
│   │   └── recipient_communities[]        （enrich で付与）
│   └── life_events[]
├── communities[]
├── person_relationships[]
│   └── source_person_id, target_person_id, target_community_id, type, property
├── original_data{}   … EDCS由来（place, province, dating_from/to, lat/lon, 碑文本文）
└── _provenance{}     … 生成アクティビティの履歴
```

**想定より情報量は多い。** パーサーを実データに合わせるだけでよく、
データ不足による機能削減は発生しない。

---

## 4. テーマ別の判定

### ◎ 実現可能 — 役職遷移ネットワーク（テーマB）

最も条件が良い。

- `career_path[].order` は **2役職以上の3,571人すべてで欠損・重複ゼロ**。
  順序関係がそのまま有向エッジになる。整合性チェックの追加実装は不要。
- `position_abstract` による正規化が 20,474件 / 655種で機能しており、
  表記ゆれを吸収済み。集計に耐える。
- 抽出される遷移: **ユニーク1,300種 / 延べ9,977件**。
  重み付き有向グラフとして十分な密度。

抽出された遷移の上位:

| 遷移 | 件数 |
|---|---:|
| pontifex → tribunicia potestas | 965 |
| consul → pater patriae | 659 |
| tribunicia potestas → consul | 605 |
| tribunicia potestas → imperator | 505 |
| imperator → consul | 447 |
| pater patriae → proconsul | 327 |
| imperator → Augustus | 317 |
| consul → proconsul | 272 |
| legatus → consul | 120 |
| **aedilis → duovir** | **90** |

> **重大な注意点**
> 上位遷移がほぼ皇帝称号（`imperator`, `pater patriae`, `Augustus`,
> `Britannicus`, `Parthicus`）で占められている。社会的身分でも `emperor` が
> 9,355件と突出。これは皇帝の称号列挙であって「キャリアパス」ではない。
> **皇帝・皇族を除外しない限り、分析結果は皇帝称号のノイズに支配される。**
> 除外後に残る地方エリートの遷移（`aedilis → duovir` 系）が本来の分析対象で、
> 規模は数百件程度に落ちる。

`position_type` の分布:

| position_type | 件数 |
|---|---:|
| imperial-administration | 7,370 |
| military | 2,967 |
| local-administration | 2,372 |
| local-priesthood | 2,277 |
| provincial-administration | 2,054 |
| imperial-priesthood | 1,530 |
| other | 1,314 |
| occupation | 556 |
| provincial-priesthood | 37 |

この `position_type` は、ドキュメントが求める
「地方官職 → 帝国中央へのクリティカル・パス特定」「階層性計測」に直接使える。

### ○ 条件付きで実現可能 — 恵与行為の多部グラフ（テーマA）

`[Person] → [Benefaction] → [Object]` の経路はデータ上成立する。
`object_type` は統制語彙になっている。

| object_type | 件数 |
|---|---:|
| other | 2,833 |
| building | 1,157 |
| statue | 572 |
| tomb | 524 |
| temple | 499 |
| money | 405 |
| altar | 312 |
| road | 276 |
| public banquet | 171 |
| gladiatorial games | 131 |
| portico | 123 |
| sportulae | 110 |
| bath | 109 |
| theatrical performances | 83 |
| aqueduct | 68 |

**Object–Object 投影は可能。** 同一人物が複数種の対象に寄進した共起ペアは
136種 / 延べ1,552件。歴史的に筋の通ったクラスタが既に見えている:

| 共起ペア | 件数 |
|---|---:|
| other ↔ statue | 57 |
| building ↔ other | 55 |
| money ↔ statue | 55 |
| public banquet ↔ statue | 53 |
| statue ↔ temple | 53 |
| **public banquet ↔ sportulae** | **51** |
| money ↔ public banquet | 48 |
| building ↔ temple | 47 |

`public banquet ↔ sportulae`（饗宴と施与金）、`building ↔ temple` など、
エウエルゲティズムの類型として解釈可能な組み合わせ。コミュニティ抽出に足りる。

> **Person–Person 投影は現状ほぼ不可能。これが最大の制約。**
>
> - 寄進者6,015人のうち `person_name_normalized` が入っているのは
>   **371人（6%）** のみ
> - 複数碑文にまたがる名前は30種・321参照分しかない
> - つまり人物は「碑文内の言及」止まりで、**碑文をまたいで同一人物に
>   束ねられていない**ため、「共通の寄進対象を持つ人物ネットワーク」は
>   ほぼ空になる
>
> **救済策あり**: `entity_resolution/person_clusters_final.json` に
> **1,973クラスタの人物同定結果が既に存在する**
> （praenomen/nomen/cognomen + 地名ベース、confidence付き）。
> これを噛ませれば Person–Person 投影が成立する。
> ただしクラスタ品質の検証は別途必要（最大クラスタは size 72 で、
> 過剰併合の疑いがある）。

`benefaction_type` の分布:

| benefaction_type | 件数 |
|---|---:|
| construction | 3,417 |
| other | 1,661 |
| donation | 861 |
| repair | 592 |
| games | 213 |
| feast | 166 |
| dedication | 12 |
| statue | 10 |

### △ 限定的 — 神々の媒介ハブ分析

ドキュメントは「どの神々（例: サトゥルヌス）が媒介ハブになっているか」を
求めているが、データ構造が想定と異なる。

- 神格は**人物側の `divinity` / `divinity_type` フラグ**として表現されている
- 「寄進対象の神」への明示的エッジは存在せず、
  `benefactions[].objects[].object_type` に `temple` / `altar` として
  現れるのみ
- 神名単位の媒介中心性を出すには、`person_relationships` の
  `dedication` 型（7,433件）を経由する再設計が必要

実装は可能だが、**ドキュメントが想定する形そのままでは出ない**。

### △ 限定的 — コスト分析

`cost_numeric` が入っているのは 6,932件中 **512件（7.4%）**。
規模の定量比較は、この512件に限った部分集合としてしか成立しない。
「寄進の規模によるエリート層のサブグループ検出」は、
母集団の7%に対する分析になる点を明示する必要がある。

### ◎ 実現可能 — 人物間関係ネットワーク（ドキュメント未記載）

ドキュメントには明示されていないが、`person_relationships` が
**30,321件**と最も密度が高い。家族・庇護関係のネットワーク分析が可能。

| 関係タイプ | 件数 |
|---|---:|
| family | 19,716 |
| dedication | 7,433 |
| patronage | 1,073 |
| affiliation | 1,008 |
| colleague | 768 |
| economic | 172 |
| other | 151 |

`patronage`（庇護関係）1,073件は、ドキュメントが狙う
「異なる社会階層を結びつける媒介ハブ」の分析に直接使える。
テーマAの Person–Person 投影が人物同定待ちである間、
**こちらは碑文内で完結するため即座に分析可能**。

---

## 5. Task 3（動的サブグラフ抽出）への影響

| フィルタ軸 | 判定 | 根拠 |
|---|---|---|
| 身分（Status） | ◎ | `social_status` が統制語彙で充実 |
| 空間（City / Region） | ◎ | 属州・地名・緯度経度すべて揃う |
| 時代（Chronology） | **△ 要注意** | 数値年代は17%のみ |

### 身分フィルタ — 問題なし

| social_status | 件数 |
|---|---:|
| emperor | 9,355 |
| citizen | 2,600 |
| soldier | 1,249 |
| unknown | 1,114 |
| sacerdos | 1,011 |
| freedman | 942 |
| senator-consularis | 847 |
| slave | 767 |
| senator-clarissimus | 744 |
| municipal-magistrate | 608 |
| imperial-family | 592 |
| decurio | 585 |
| equestrian | 535 |
| empress | 523 |
| freeborn | 523 |

ドキュメントが求める「解放奴隷 / 騎士階級 / 元老院階級」の層別は
`freedman` 942 / `equestrian` 535 / `senator-*` 1,591 で成立する。

### 空間フィルタ — 問題なし

属州（Africa proconsularis / Numidia）、地名、緯度経度がすべて `original_data`
に揃っている。Carthago 9,082 vs Lambaesis 2,626 など、
「沿岸部大都市 vs 内陸部」の比較に十分な規模。

### 年代フィルタ — 最大の弱点

数値年代を持つのは **9,906件（17%）** のみ。世紀別内訳:

| 世紀 | 件数 |
|---|---:|
| 前1世紀 | 8 |
| 0（境界） | 175 |
| 1世紀 | 1,098 |
| 2世紀 | 3,296 |
| 3世紀 | 3,768 |
| 4世紀 | 854 |
| 5世紀 | 395 |
| 6世紀 | 259 |
| 7世紀 | 38 |
| 8世紀 | 1 |
| 10世紀 | 5 |
| 11世紀 | 9 |

「世紀別サブグラフの比較」自体は実行できるが、
**母集団の83%が脱落する**ため、時代差として観測されたものが
実際の歴史的変化なのか、年代が付与されやすい碑文種別のバイアスなのかを
区別できない。結論を出す際は必ずこの制約を明示する必要がある。

また、**5〜11世紀に約700件**が出ている。ローマ期北アフリカとしては不自然で、
`dating_from` / `dating_to` のパース不良か外れ値。前処理での除外が必要。

---

## 6. 実装前に片付けるべき前提作業

優先度順。1と3は必須。

1. **皇帝・皇族の除外フィルタ**
   テーマB成立の必須条件。`social_status in (emperor, empress, imperial-family)`
   および皇帝称号系の `position_abstract` を除外する。
   これをやらないと役職遷移グラフは皇帝称号のノイズで埋まる。

2. **人物同定の接続**
   Person–Person 投影の必須条件。
   既存の `entity_resolution/person_clusters_final.json`（1,973クラスタ）を
   活用する。ただし最大クラスタ size 72 の過剰併合を検証してから使う。
   confidence レベルでの足切りが必要。

3. **年代の外れ値除去と欠損の扱いの明示**
   5世紀以降の約700件を除外。
   そのうえで「年代フィルタ適用時は母集団の17%が対象」であることを
   分析結果・レポートに必ず併記する。

4. **`object_type` / `benefaction_type` の `other` の扱い**
   `other` が object_type で2,833件（最多）、benefaction_type で1,661件。
   投影グラフで `other` が人工的なハブになるため、
   除外するか再分類するかの判断が必要。

---

## 7. 実装可否まとめ

| ドキュメント上のタスク | 判定 | 備考 |
|---|---|---|
| Task 1: NetworkX Graph / DiGraph 化 | ◎ | 想定スキーマと実データの差異を吸収するパーサーが必要 |
| Task 2-1: 2部グラフ投影（Object–Object） | ◎ | 共起136種1,552件。即実行可能 |
| Task 2-1: 2部グラフ投影（Person–Person） | △ | 人物同定が前提。既存クラスタの活用で成立 |
| Task 2-1: コミュニティ抽出 | ◎ | Object–Object 側で成立 |
| Task 2-2: 役職遷移・最頻経路 | ◎ | 皇帝除外が前提。order 欠損ゼロ |
| Task 2-2: アウトライヤー経路検出 | ○ | 3,571人が母集団。皇帝除外後は数百人規模 |
| Task 2-3: 各種中心性 | ◎ | 障害なし |
| Task 3: 身分フィルタ | ◎ | |
| Task 3: 空間フィルタ | ◎ | |
| Task 3: 時代フィルタ | △ | 対象が17%に限定される点の明示が必須 |
| Task 4: PyVis / Plotly 可視化 | ◎ | 障害なし |
| Task 4: `analysis_insights.md` | ○ | 上記制約を踏まえた記述が必要 |
| （追加提案）人物間関係ネットワーク | ◎ | 30,321件。ドキュメント未記載だが最も密度が高い |

---

## 8. 調査の再現方法

本レポートの数値は、以下のディレクトリを全件パースして算出した
（サンプリング・推計なし）。

```
pipeline/provenance/validated_career_graphs/claude/*/*/*_career.json
```

集計項目: レコード数、人物数、経歴長分布、`order` の欠損・重複、
`position_abstract` / `position_type` / `object_type` / `benefaction_type` /
`social_status` / 関係タイプの頻度、`dating_from`/`dating_to` の世紀別分布、
寄進対象の共起ペア、`person_name_normalized` の碑文横断出現。
