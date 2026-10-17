# `social_status` 棚卸しとカテゴリ再設計の論点

調査日: 2026-10-16
対象: `validated_career_graphs/claude/` の全 `persons[].social_status` — **85,118件**
調査方法: 全2,042ファイルを全件パース（サンプリングなし）。
`social_status_evidence` を突き合わせて軸の帰属と判定根拠を確認。

先行事例: [OBJECT_TYPE_INVENTORY.md](OBJECT_TYPE_INVENTORY.md)（`object_type` の再設計）

---

## 1. 結論

4点が判明した。

1. **現行語彙は91種。統制されていない。** 抽出プロンプトが統制語彙を
   与えておらず（`e.g. ... etc.` の開いた例示）、LLM が都度生成している。
   91種のうち**45種が10件未満、22種が1件のみ**。
2. **`object_type` と違い、社会的身分は本来「多軸」である。**
   法的身分・身分階層・職業・役職・宗教的役割・軍事の6軸が
   単一の文字列フィールドに混在している。
   **2階層化（category + subtype）では解決しない。**
3. **70.3%が空文字**（59,830件）。`object_type` の `other` と違い
   「分類できない」ことすら記録されていない。
   再分類してもカバレッジは改善しない。
4. **`social_status_evidence` の 3,708件は原文引用ではなく推論文**であり、
   プロンプト自身の規約に違反している。再分類の入力としての信頼性に関わる。

→ したがって `object_type` と同じ「2階層の統制語彙に置換」では**不十分**で、
   §5 の設計判断（多軸化するか否か）を先に決める必要がある。

---

## 2. 全体の分布

| | 件数 | 比率 |
|---|---:|---:|
| persons 総数 | 85,118 | 100% |
| **`social_status` が空文字** | **59,830** | **70.3%** |
| 値あり | 25,288 | 29.7% |
| └ うち `social_status_evidence` あり | 25,138 | 99.4%（値ありに対し） |

**再抽出は不要。** `social_status_evidence` が99.4%存在するため、
EDCS からのスクレイピングをやり直す必要はない。
既存JSON内の `social_status` + `social_status_evidence` を入力として、
分類パスだけを再実行できる（`object_type` と同じ条件）。

ただし §4-4 のとおり、evidence の品質には問題がある。

---

## 3. 現行 `social_status` の全91種

軸ごとに分類して示す。軸の区分は本書の分析のために与えたもので、
**データ上はすべて同一フィールドの値**である。

### 3-1. 身分階層（ordo） — 20種 / 13,683件

| social_status | 件数 | 評価 |
|---|---:|---|
| emperor | 9,355 | 可 |
| senator-consularis | 847 | 可（位階付き） |
| senator-clarissimus | 744 | 可（位階付き） |
| imperial-family | 592 | 可 |
| decurio | 585 | **同綴異義（§4-2）** |
| equestrian | 535 | 可 |
| empress | 523 | 可 |
| equestrian-perfectissimus | 177 | 可（位階付き） |
| equestrian-egregius | 130 | 可（位階付き） |
| senator-praetorius | 104 | 可（位階付き） |
| municipal-elite | 35 | 粒度が異なる |
| senator | 20 | 位階なしの上位語 |
| equestrian-splendidus | 15 | 可（位階付き） |
| centenarius | 7 | 俸給等級であり身分ではない |
| local-ruler | 5 | 粒度が異なる |
| king | 3 | ローマ身分体系外 |
| equestrian-excellentissimus | 2 | 可（位階付き） |
| patricius | 2 | `patrician` と重複 |
| equestrian-eminentissimus | 1 | 可（位階付き） |
| decurion | 1 | `decurio` と重複（綴りゆれ） |

> `senator-*` / `equestrian-*` は**身分と位階を連結した複合値**。
> 身分（senator）と位階（consularis）は別の軸であり、
> 現状は文字列連結で表現されている。

### 3-2. 法的身分 — 9種 / 5,142件

| social_status | 件数 | 評価 |
|---|---:|---|
| citizen | 2,600 | 可（ただし §4-4） |
| freedman | 942 | 可 |
| slave | 767 | 可 |
| freeborn | 523 | 可 |
| freedwoman | 306 | `freedman` の性別違い（§4-3） |
| patrician | 1 | `patricius` と重複 |
| imperial-slave | 1 | 可 |
| imperial-freedman-or-slave | 1 | **判定保留値がそのまま記録されている** |
| imperial-slave-or-freedman | 1 | 同上・語順違いで別値になっている |

### 3-3. 軍事 — 5種 / 2,044件

| social_status | 件数 | 評価 |
|---|---:|---|
| soldier | 1,249 | 可 |
| veteran | 466 | **経歴であって身分ではない** |
| centurio | 315 | **階級であって身分ではない** |
| military | 13 | `soldier` と重複 |
| military-commander | 1 | 役職 |

### 3-4. 宗教的役割 — 26種 / 1,649件

| social_status | 件数 | 評価 |
|---|---:|---|
| sacerdos | 1,011 | **役職（§4-5 で career_path と重複）** |
| flamen | 446 | 同上 |
| martyr | 50 | 役割ではなく死後の評価 |
| pontifex | 27 | 役職 |
| local-priesthood | 26 | 粒度が異なる |
| deity | 20 | **人物ではない** |
| augur | 17 | 役職 |
| deacon | 10 | `diaconus` と重複 |
| diaconus | 4 | `deacon` と重複 |
| fidelis | 4 | 信徒一般 |
| subdiaconus | 3 | 可 |
| monk | 3 | 可 |
| clericus | 3 | `cleric` と重複 |
| cleric | 3 | `clericus` と重複 |
| lector | 3 | 可 |
| sancta | 3 | 死後の評価 |
| augustalis | 3 | **解放奴隷の宗教職。法的身分と重なる** |
| flaminica | 2 | `flamen` の性別違い |
| consecrated-virgin | 2 | 以下4種が同一概念（§4-3） |
| virgo sacrata | 2 | 同上（ラテン語形） |
| santimoniale | 2 | 同上（綴りゆれ） |
| castimonialis | 1 | 同上（綴りゆれ） |
| bishop | 1 | 可 |
| presbyter | 1 | 可 |
| archdeacon | 1 | 可 |
| deceased-spirit | 1 | **人物ではない** |

### 3-5. 役職 — 19種 / 1,156件

| social_status | 件数 | 評価 |
|---|---:|---|
| municipal-magistrate | 608 | 可（上位語） |
| legatus | 146 | **career_path と重複** |
| duovir | 136 | 同上 |
| aedilis | 126 | 同上 |
| tribunus | 44 | 同上 |
| quaestor | 27 | 同上 |
| consul | 26 | 同上 |
| imperial-administration | 15 | 粒度が異なる |
| provincial-administration | 9 | 粒度が異なる |
| curator | 5 | career_path と重複 |
| local-administration | 4 | 粒度が異なる |
| provincial-governor | 3 | career_path と重複 |
| administrator | 1 | 粒度が異なる |
| quinquennalis | 1 | career_path と重複 |
| promagister | 1 | career_path と重複 |
| local | 1 | 意味不明 |
| **flamen-decurio** | 1 | **複合値（§4-1）** |
| **veteran-decurio** | 1 | **複合値（§4-1）** |
| **equestrian-decurio** | 1 | **複合値（§4-1）** |

### 3-6. 職業 — 9種 / 481件

| social_status | 件数 | 評価 |
|---|---:|---|
| artisan | 233 | 可（上位語） |
| gladiator | 126 | 可 |
| merchant | 52 | 可 |
| medicus | 36 | 可 |
| occupation | 16 | **軸名そのものが値になっている** |
| actor | 13 | 可 |
| charioteer | 3 | 可 |
| musician | 1 | 可 |
| contractor | 1 | 可 |

### 3-7. 分類不能 — 2種 / 1,132件

| social_status | 件数 | 評価 |
|---|---:|---|
| unknown | 1,114 | 可（明示的な不明） |
| other | 18 | **要再分類** |

### 3-8. 複数軸にまたがる値 — 1種 / 1件

| social_status | 件数 | 評価 |
|---|---:|---|
| `augur, pontifex` | 1 | **カンマ区切りで2役職** |

---

## 4. 観察された問題

### 4-1. 【最重要】単一フィールドが多軸を表現できていない

社会的身分は本来、相互に排他的でない複数の軸からなる。

| 軸 | 件数 | 種数 |
|---|---:|---:|
| 身分階層（ordo） | 13,682 | 19 |
| 法的身分 | 5,142 | 9 |
| 軍事 | 2,044 | 5 |
| 宗教的役割 | 1,649 | 26 |
| 役職 | 1,156 | 19 |
| 職業 | 481 | 9 |
| 分類不能 | 1,132 | 2 |

同一人物が複数の軸に同時に属することは通常である。
解放奴隷（法的身分）かつ商人（職業）かつアウグスタリス（宗教的役割）は
碑文に頻出する組み合わせだが、**現在のスキーマでは1つしか記録できない**。

#### 証拠1: 複合値が生成されている

抽出側が単一フィールドの制約に行き詰まった痕跡が、4件残っている。

```
flamen-decurio      1件   （宗教的役割 + 身分階層）
veteran-decurio     1件   （軍事 + 身分階層）
equestrian-decurio  1件   （身分階層 + 身分階層）
augur, pontifex     1件   （役職 + 役職、カンマ区切り）
```

また `senator-consularis` / `equestrian-perfectissimus` など
**位階付きの値1,275件**も、身分と位階という2軸の文字列連結である。

#### 証拠2: evidence に複数軸の語があるのに単一値しか記録されていない

`social_status_evidence` を走査し、複数の軸を示す語が同時に出現する例を数えた。

| evidence に同時出現 | 件数 | 記録された値（例） |
|---|---:|---|
| decurio + flamen | 11 | `decurio` |
| decurio + veteran | 5 | `veteran`（evidence: `vet(erano) ex dec(urione)`） |
| centurio + decurio | 2 | `decurio` |
| flamen + augustalis | 1 | `municipal-magistrate` |
| decurio + freedman | 1 | `decurio` |

`vet(erano) ex dec(urione)`（元参事会員の退役兵）は**両方が明示されている**が、
記録は `veteran` のみで `decurio` が失われている。

> これは検出できた分のみで、実際の多軸事例はこれより多い。
> 走査は限られたパターン（flamen/decurio/veteran/centurio/freedman/augustalis）
> に基づくため、下限値として読むべきである。

### 4-2. `decurio` 585件は同綴異義語

`decurio` は**都市参事会員**と**騎兵小隊長**の両方を指す。
evidence から判別を試みた結果:

| 判定 | 件数 |
|---|---:|
| 都市参事会員（`ordo`, `decurion-` 等） | 144 |
| 軍事・騎兵（`alae`, `turma`, `equit-` 等） | 4 |
| **判別不能** | **437** |

`object_type` における `monumentum`（tomb/building/other に分裂）と
同じ構造の問題だが、こちらは**正解が文脈でしか決まらない**ため、
機械規則では437件が未確定のまま残る。LLM 判定が必須となる。

### 4-3. 重複・表記ゆれ

| 重複する値 | 件数 | 備考 |
|---|---|---|
| `decurio` / `decurion` | 585 / 1 | 綴りゆれ |
| `cleric` / `clericus` | 3 / 3 | 英語形とラテン語形 |
| `deacon` / `diaconus` | 10 / 4 | 同上 |
| `patricius` / `patrician` | 2 / 1 | 同上 |
| `military` / `soldier` | 13 / 1,249 | 同義 |
| `consecrated-virgin` / `virgo sacrata` / `santimoniale` / `castimonialis` | 2/2/2/1 | **同一概念が4種に分裂** |
| `imperial-freedman-or-slave` / `imperial-slave-or-freedman` | 1 / 1 | **語順違いで別値** |
| `freedman` / `freedwoman` | 942 / 306 | 性別違い（`gender` と冗長） |
| `flamen` / `flaminica` | 446 / 2 | 同上 |

`freedwoman` / `flaminica` は性別による語形変化であり、
`gender` フィールドが別にある以上、身分語彙としては冗長である。

### 4-4. evidence の 3,708件が原文引用ではない

プロンプトは以下を明示的に要求している（[prompt_template.py:368](../pipeline/prompt_template.py#L368)）:

> All "evidence" fields ... must contain ONLY a direct quote copied verbatim
> from the inscription text. Do NOT include reasoning, interpretation, explanation.

しかし推論語（`indicating`, `suggests`, `typically`, `implies` 等）を含む
evidence が **3,708件**存在する。

| social_status | 推論文の件数 |
|---|---:|
| citizen | 1,779 |
| freedman | 376 |
| unknown | 335 |
| emperor | 286 |
| freeborn | 270 |
| slave | 143 |

実例:

```
'Arn(ensi) - member of Arnensis tribe, indicating Roman citizenship'
'Greek cognomen Eutices suggests freedman status'
'au<g=c>us(talis) — augustalis, typically a freedman serving in the imperial...'
```

`citizen` 2,600件のうち1,779件（68%）がこの形式である。
つまり **`citizen` は碑文に明示された身分ではなく、
投票部族名（tribus）やfiliationからの推論**であることが多い。

これは2つの意味を持つ:

1. **再分類の入力として使える。** 推論の根拠（`Arn(ensi)`）は原文であり、
   ハイフン以降が解釈である。機械的に分離できる。
2. **データの性質として記録すべき。** 「碑文に明示された身分」と
   「名前や部族から推論された身分」は証拠としての強度が違う。
   現在は区別されていない。

### 4-5. 役職系の値が `career_path` と重複

`social_status` に役職名が入っている3,506件のうち、
**1,149件は同じ語が `career_path[].position` にも存在**する。

| social_status | career_path にも同じ語 |
|---:|---:|
| sacerdos | 584 |
| centurio | 254 |
| aedilis | 85 |
| flamen | 83 |
| decurio | 72 |
| pontifex | 23 |

`sacerdos` は1,011件中584件（58%）が重複している。

役職は `career_path` が担当する軸であり、`social_status` に
同じ情報を置くのは冗長であるだけでなく、
**「身分」と「経歴」の境界を曖昧にする**。

### 4-6. 人物でない値

| 値 | 件数 | 内容 |
|---|---:|---|
| deity | 20 | 神格。`persons[]` に神が含まれている |
| deceased-spirit | 1 | Dis Manibus 等の被献呈者 |

これらは身分語彙の問題ではなく、
**`persons[]` に人間でない存在が混入している**という別の問題を示す。
身分カテゴリの再設計では解決しない。

### 4-7. evidence が当該人物以外を指している場合がある

**2026-10-16 の語彙設計作業で新たに検出。**

`social_status_evidence` から追加の軸を機械的に拾う規則を試作したところ、
`social_status='emperor'` の人物に `legal.slave` が付与される誤りが
**18件**発生した。原因は evidence の内容:

```
social_status: 'emperor'
evidence     : 'Aug(usti) ser(vus) — Fortunatus is described as slave of the Augustus'
evidence     : 'Caesaris ser(vus) - owner of imperial slaves'
```

これらは**皇帝の奴隷**についての記述であり、皇帝自身の身分ではない。
evidence は「この人物の身分の根拠」とは限らず、
**同じ碑文に登場する他の人物への言及を含む**。

帰結:

- evidence への正規表現マッチだけで軸を追加してはならない
- 追加軸の判定は、**人物の同定を含めて** LLM に行わせる必要がある
- `status_category_map.json` の `evidence_rules` は `enabled: false` とし、
  LLM プロンプト用の参考パターンとしてのみ残した

同様に `decurio` も、`dec(urio) alae Flaviae`（騎兵小隊長）を
機械規則で `decurio_municipal` と誤判定する例が検出されたため、
`ambiguous_forms` 側でのみ扱う。

---

## 5. 設計判断 — 多軸化するか否か

`object_type` では「第1階層 + 第2階層」の2階層化で解決した。
しかし §4-1 のとおり、社会的身分では**階層化では足りない**。
以下の3案がある。

### 案A: 単軸・2階層（`object_type` と同じ形）

```json
"status_category": "legal",
"status_subtype": "legal.freedman"
```

| | |
|---|---|
| 利点 | 実装が軽い。`object_type` のスクリプトをほぼ流用できる |
| 欠点 | **多軸の実態を潰す。** `flamen-decurio` 型の複合値を再生産する |

→ §4-1 の問題が未解決のまま残るため、**推奨しない**。

### 案B: 多軸・複数フィールド

```json
"legal_status":    "freedman",
"ordo":            "decurio",
"occupation":      "merchant",
"religious_role":  "augustalis"
```

| | |
|---|---|
| 利点 | 実態に最も忠実。軸ごとに独立して分析できる |
| 欠点 | スキーマ変更が大きい。RDF・評価データセット・エディタの改修が必要 |

### 案C: 単軸＋多値配列（中間案）

```json
"social_statuses": [
  {"category": "legal", "subtype": "legal.freedman",
   "evidence": "lib(ertus)", "certainty": "explicit"},
  {"category": "religious", "subtype": "religious.augustalis",
   "evidence": "aug(ustalis)", "certainty": "explicit"}
]
```

| | |
|---|---|
| 利点 | 多軸を表現でき、軸の追加が容易。`objects[]` と同じ配列パターンで前例がある |
| 欠点 | 「主たる身分は何か」が決まらない。分析時に代表値の選択規則が要る |

> `certainty`（explicit / inferred）を持たせれば §4-4 の問題も同時に解決する。

### 併せて決めるべきこと

1. **役職を `social_status` に残すか**（§4-5。`career_path` との重複1,149件）
2. **位階を分離するか**（`senator-consularis` → 身分 `senator` + 位階 `consularis`）
3. **`veteran` / `centurio` の扱い**（経歴・階級であって身分ではない）
4. **70.3%の空文字をどうするか**（`unknown` を明示するか空のままか）
5. **`deity` / `deceased-spirit`**（身分語彙ではなく `persons[]` の設計問題）

---

## 6. 処理コストの見積もり

案が確定していないため暫定値だが、`object_type` との対比で規模感を示す。

| | `object_type` | `social_status` |
|---|---:|---:|
| 対象件数 | 7,590 | **25,288**（非空のみ） |
| distinct 値 | 40 | 91 |
| 証拠テキストの存在率 | 100% | 99.4% |
| 機械規則で確定できる見込み | 88.9%（実績） | **要検証** |

機械的に処理できる見込みの内訳（推定）:

| 対象 | 件数 | 処理 |
|---|---:|---|
| 表記ゆれの統合 | 約30 | 機械的（§4-3） |
| 明確な単一軸の値 | 約20,000 | 機械的マッピング |
| `decurio` の判別不能分 | 437 | **LLM 必須**（§4-2） |
| 多軸の可能性がある分 | **要検証** | LLM 必須 |
| `other` | 18 | LLM |

> **注意**: `object_type` では「表層形 → カテゴリ」の対応が
> ほぼ一意だったため機械規則が88.9%を処理できた。
> `social_status` では**多軸判定が必要なため、同じ比率は期待できない**。
> 案B・案Cを採る場合、evidence から他の軸を拾い直す作業が加わるため、
> LLM 呼び出しの比率は `object_type` より高くなる。

---

## 7. オントロジー側の状況

`epig:SocialStatus` クラスは**既に存在する**
（[epig_ontology.ttl:501](../../hmk_ontology/ontology/epig_ontology.ttl)）。

```turtle
epig:SocialStatus a owl:Class ;
    rdfs:label "Social Status"@en , "社会的身分"@ja ;
    rdfs:comment "人物の社会的身分の共有リソース (例: decurio)。"@ja .
```

ただし:

- **個体（コントロールドボキャブラリ）が未定義**
- プロパティ `epig:socialStatus` は `xsd:string`（`epig:SocialStatus` を range にしていない）
- domain は `epig:PersonReference`

`epig:FundingType` / `epig:ObjectCategory` と同じ SKOS 方式に揃える土台はある。
`epigo:`（object）に倣い `epigs:`（status）のサブ名前空間を切るのが自然。

案Bを採る場合は軸ごとにプロパティを分ける（`epig:legalStatus` 等）、
案Cを採る場合は `epig:socialStatusStatement` のような再具象化ノードが要る。
**データ構造の決定が先行する。**

---

## 8. 論点の状態

| # | 論点 | 状態 |
|---|---|---|
| 1 | 多軸化するか（案A/B/C） | **未確定・最優先** |
| 2 | 役職を `social_status` に残すか（§4-5） | 未確定 |
| 3 | 位階（consularis 等）を分離するか | 未確定 |
| 4 | `veteran` / `centurio` の扱い | 未確定 |
| 5 | 70.3%の空文字の扱い | 未確定 |
| 6 | evidence の explicit / inferred 区別（§4-4） | 未確定 |
| 7 | `deity` / `deceased-spirit`（§4-6） | **別件**（`persons[]` の設計問題） |
| 8 | 旧 `social_status` を後方互換で残すか | 未確定 |

> `object_type` では論点8に相当する判断を「併記（旧値を温存）」とし、
> `epig:objectType` と `epig:objectCategory` を別プロパティとして共存させた。
> `social_status` でも同じ方針が取れる。

---

## 9. 決定事項（2026-10-16）

§5 の3案および §8 の論点について、以下を決定した。

### 9-1. 案C（単軸＋多値配列）を採用

決め手は **同一軸内に複数の値が明示されている人物が112件**存在すること。
案B（軸ごとに固定スロット）では `religious_role` が1つしか持てず、
`flamen divi Antonini Pii, flamen divi Traiani, sacerdos Cereris et
Aesculapi, flamen divi Magni Antonini, sacerdos unicus`（宗教職5つ）
のような事例で情報が失われる。これは現在の単一値フィールドの問題を
軸の数だけ増やして再現するに等しい。

### 9-2. 役職は `career_path` に委ねる

役職・宗教職系の `social_status` 保持者2,688件のうち
**2,512件（93.5%）が `career_path` を持つ**。
`career_path` 側は `position_type` が10種に統制されており、
役職の器としては `social_status`（91種に発散）より優れている。
時系列（`order`）と場所（`location`）も記録できる。

### 9-3. 宗教は「役職」と「立場」で分割する

`career_path` との重複率が、そのまま役職らしさの指標になっていた。

| 分類 | 例 | career_path に同語 |
|---|---|---|
| **役職** → career_path へ | pontifex / diaconus / lector | **100%** |
| | flamen | 90% |
| | sacerdos | 73% |
| **立場** → social_statuses に残す | martyr / monk / fidelis / sancta | **0%** |
| | consecrated-virgin 系 | **0%** |

「修道士」「殉教者」「信徒」は役職ではないため `career_path` に入りようがなく、
`religious` 軸に残す必要がある。

### 9-4. `augustalis` は文脈依存として扱う

`augustalis` → `legal.freedman` への変換は妥当だが、**無条件には行えない**。

| evidence | 意味 | 扱い |
|---|---|---|
| `sevir / IIIIIIvir Augustalis` | 解放奴隷の職 | `legal.freedman`（inferred）＋ career_path |
| `sodalis Augustalis` | 元老院の祭司団 | career_path のみ。freedman を含意しない |
| どちらの語もなし（37件） | 判別不能 | **LLM へ** |

実データ上、`social_status='augustalis'` は3件のみで、
大半は抽出時点で既に `freedman` に変換されている。

### 9-5. 確定した軸構成（6軸 / 31 subtype）

| category | subtype数 | 件数（延べ） |
|---|---:|---:|
| ordo | 10 | 13,688 |
| legal | 5 | 5,139 |
| military | 3 | 2,044 |
| unknown | 1 | 1,114 |
| occupation | 6 | 465 |
| religious | 6 | 93 |

マッピング表: [mapping/status_category_map.json](mapping/status_category_map.json)

### 9-6. 機械規則の適用見込み（シミュレーション実測）

全85,118人物に対し規則を適用した結果（**書き込みなし**）:

| 処理 | 件数 |
|---|---:|
| 空文字（対象外） | 59,830 |
| **direct（単一軸に確定）** | **21,952** |
| delegated（career_path へ委譲） | 2,686 |
| ambiguous → 既定値（LLM で要確認） | 432 |
| ambiguous → evidence で解決 | 154 |
| pending_llm | 39 |
| excluded（非人物） | 21 |
| multi_axis | 4 |

`social_statuses` に値が入る人物: **22,542**
certainty 内訳: explicit 18,214 / inferred 4,328

> 多軸割当てが4件と少ないのは、**機械規則では安全に増やせない**ため（§4-7）。
> 多軸の実態（§4-1 で下限112件以上）を拾うには LLM パスが必要である。

### 9-7. 未決定

| # | 論点 | 備考 |
|---|---|---|
| 1 | 位階（consularis 等）を `rank` として分離するか | マッピング表には `rank` を暫定で用意済み |
| 2 | 70.3%の空文字の扱い | `unknown` を明示するか空のままか |
| 3 | 代表値の選択規則 | 案Cの弱点。分析側で `ordo > legal > military > religious > occupation` 等 |
| 4 | 旧 `social_status` の後方互換 | `object_type` と同様に併記（温存）を推奨 |
| 5 | `deity` / `deceased-spirit` 21件 | **別件**（`persons[]` の設計問題） |

---

## 10. オントロジー実装（2026-10-16 完了）

`hmk_ontology/ontology/epig_ontology.ttl` に実装した（CLAUDE.md のとおり
オントロジーの編集は `hmk_ontology` 側で行い、本リポジトリからは読み取り専用で参照する）。

### 10-1. 名前空間

```turtle
@prefix epigs: <http://epigraphic-careers.org/ontology/status/> .
```

`epigf:`（funding）/ `epigo:`（object）に倣う。

### 10-2. 語彙個体 37件（第1階層6 + 第2階層31）

`epig:SocialStatus` を `skos:Concept` のサブクラスとし、
第2階層は `skos:broader` で第1階層に接続する。

| 第1階層 | 配下 |
|---|---:|
| epigs:ordo | 10 |
| epigs:occupation | 6 |
| epigs:religious | 6 |
| epigs:legal | 5 |
| epigs:military | 3 |
| epigs:unknown | 1 |

語彙個体は `status_category_map.json` から機械生成しており、
**両者の値集合が完全に一致することを検証済み**（過不足ゼロ）。

### 10-3. クラス・プロパティ

```turtle
epig:SocialStatusStatement  rdfs:subClassOf hmki:Statement .
```

案Cの多値を表現するための再具象化ノード。`epig:BenefactionStatement` と同じ形。

| プロパティ | domain | range |
|---|---|---|
| epig:hasSocialStatusStatement | PersonReference | SocialStatusStatement |
| epig:socialStatusCategory | SocialStatusStatement | SocialStatus |
| epig:socialStatusSubtype | SocialStatusStatement | SocialStatus |
| epig:statusRank | SocialStatusStatement | xsd:string |
| epig:statusCertainty | SocialStatusStatement | xsd:string |
| epig:statusEvidence | SocialStatusStatement | xsd:string |
| epig:statusReasoning | SocialStatusStatement | xsd:string |
| epig:socialStatusSource | SocialStatusStatement | xsd:string |

`epig:statusRank` は §9-7 論点1（位階の分離）に対応する。
`epig:statusCertainty` / `epig:statusReasoning` は §4-4（推論と明示の区別）に対応する。

### 10-4. 後方互換

既存の `epig:socialStatus`（`xsd:string`）は**温存**し、
`rdfs:comment` に生成来歴保持のための旧値である旨を追記した。
`epig:objectType` と `epig:objectCategory` の関係と同じ扱い。

### 10-5. 検証結果

| 項目 | 結果 |
|---|---|
| Turtle パース | OK（1,005 → 1,276 triples、+271） |
| 第2階層の broader 接続 | 31/31 すべて第1階層へ |
| notation と URI の一致 | 37/37 |
| en/ja ラベル | 37/37 |
| skos:definition | 37/37 |
| domain/range の未定義クラス参照 | なし |
| epigo: との名前空間混線 | なし（重複0） |
| 既存 triple の喪失 | 1件のみ（意図的に差し替えた旧 comment） |
