# `position_abstract` 棚卸しと統制の方針

調査日: 2026-10-17
対象: `validated_career_graphs/claude/` の全 `career_path[]` — **20,750件**
調査方法: 全2,042ファイルを全件パース（サンプリングなし）。

先行事例: [OBJECT_TYPE_INVENTORY.md](OBJECT_TYPE_INVENTORY.md) /
[SOCIAL_STATUS_INVENTORY.md](SOCIAL_STATUS_INVENTORY.md)

---

## 1. 結論

先行する2つの再設計とは**病理の種類が異なる**。

1. **第1階層（`position_type`）は既に統制されている。** 10種に収まっており、
   `social_status` が91種に発散していたのとは対照的。
   **第1階層の再設計は不要**。
2. **称号が役職に混在している（5,736件・27.6%）。** `imperator`,
   `pater patriae`, `Germanicus` 等は職務ではなく地位・権限・勝利称号。
   これが最大の問題。
3. **同一の役職に異なる `position_type` が割り当てられている（86.2%）。**
   ただし一部は正当な区別（`pontifex maximus` と `pontifex`）であり、
   機械的に統一してはいけない。
4. **ロングテールは小さい。** 5件未満が485種あるが合計783件（3.8%）。
   `social_status` ほど深刻ではない。

→ したがって「全659種を統制語彙に置き換える」のではなく、
   **称号の分離**と**主要官職の統制**に絞るのが妥当。

---

## 2. 全体の分布

| | 件数 |
|---|---:|
| `career_path` 総数 | 20,750 |
| `position_abstract` が空 | 4 |
| distinct | **659** |

### 2-1. 上位N種のカバー率

| | 件数 | カバー率 |
|---|---:|---:|
| 上位20種 | 14,974 | 72.2% |
| **上位30種** | 16,704 | **80.5%** |
| **上位50種** | 18,168 | **87.6%** |
| 上位75種 | 18,930 | 91.2% |
| 上位100種 | 19,350 | 93.3% |
| 上位200種 | 20,067 | 96.7% |

**上位50種で87.6%**。統制の対象として現実的な規模である。

### 2-2. 第1階層（`position_type`）— 既に統制済み

| position_type | 件数 |
|---|---:|
| imperial-administration | 7,386 |
| military | 2,968 |
| local-administration | 2,498 |
| local-priesthood | 2,401 |
| provincial-administration | 2,059 |
| imperial-priesthood | 1,530 |
| other | 1,314 |
| occupation | 556 |
| provincial-priesthood | 37 |
| economic | 1 |

---

## 3. 観察された問題

### 3-1. 【最重要】称号が役職に混在している — 5,736件（27.6%）

`career_path` は「役職の経歴」を記録する配列だが、**役職ではないもの**が
含まれている。

| position_abstract | 件数 | 性質 |
|---|---:|---|
| imperator | 1,453 | 地位の表示（軍の最高司令権） |
| tribunicia potestas | 1,436 | 権限であって官職ではない |
| pater patriae | 1,060 | 称号 |
| Augustus | 568 | 称号 |
| Caesar | 387 | 称号 |
| Germanicus | 211 | 勝利称号 |
| Parthicus | 165 | 勝利称号 |
| Britannicus | 125 | 勝利称号 |
| princeps iuventutis | 82 | 称号 |
| Sarmaticus | 63 | 勝利称号 |
| Dacicus | 50 | 勝利称号 |
| censor | 22 | （職だが皇帝の場合は称号的） |
| その他（`Imperator`, `Pater Patriae` 等の表記ゆれ含む） | — | |

分類も不統一である。

```
imperator      → imperial-administration 934 / military 516 / other 3
pater patriae  → imperial-administration 660 / other 400
Germanicus     → other / imperial-administration / military に分散
```

同じ称号が「帝国行政」「軍事」「その他」に散っている。
`social_status` における軸の混在（§4-1）と同じ構造の問題である。

### 3-2. 同一役職に異なる `position_type` — 165種 / 17,877件（86.2%）

```
consul (1,673件)
    1641 imperial-administration
      27 provincial-administration
       3 local-administration
       2 other
proconsul (1,010件)
     736 provincial-administration
     274 imperial-administration
```

**ただし、すべてが誤りではない。** 原文を確認した結果:

| 例 | 判定 |
|---|---|
| `pontifex` → imperial-priesthood | 原文は `pontifex maximus`（皇帝の大神祇官） |
| `pontifex` → local-priesthood | 原文は `pont(ifici)`（地方の神祇官） |
| → **正当な区別** | `position_abstract` が粗すぎて同一視されている |

一方:

| 例 | 判定 |
|---|---|
| `proconsul` → provincial-administration | 原文 `proco(n)s(ul)` |
| `proconsul` → imperial-administration | 原文 `proco(n)s(ul)`（同一） |
| → **判定の揺れ** | 同じ原文に別の type が付いている |

→ 機械的な統一は危険。**原文（`position`）を見て区別すべきケースと、
  単なる揺れのケースを分ける必要がある。**

### 3-3. 表記ゆれ — 17組

| 組 | 件数 |
|---|---|
| `imperator` / `Imperator` | 1,453 / 39 |
| `pater patriae` / `Pater Patriae` | 1,060 / 2 |
| `princeps iuventutis` / `Princeps iuventutis` | 82 / 1 |
| `episcopus` / `Episcopus` | 65 / 1 |
| `Augustalis` / `augustalis` | 29 / 2 |
| `honores` / `honor` | 40 / 7 |
| `Xvir` / `xvir` | 5 / 3 |

**注意**: `medicus`(32) と `Medicus`(14) は**同綴異義**。
前者は「医師」（occupation）、後者は Marcus Aurelius の**勝利称号**。
単純な小文字化では誤統合する。

### 3-4. ロングテール — 485種が5件未満

| | 種数 | 件数 |
|---|---:|---:|
| 5件未満 | 485 | 783（3.8%） |
| うち1件のみ | 301 | 301 |

`social_status`（91種中45種が10件未満）と比べると、**全体に占める比率は小さい**。
ローマの官職は本来多様であり、659種は「発散」ではなく「実態」の面がある。

---

## 4. 方針

### 4-1. 全件の統制語彙化は行わない

`object_category`（54個体）と `social_status`（37個体）は**分析の軸**であり、
統制する価値が明確だった。`position_abstract` は**役職名そのもの**で、
性質が異なる。659種を無理に統制すると、史料の多様性を潰すことになる。

### 4-2. 行うこと

| # | 対象 | 件数 | 内容 |
|---|---|---:|---|
| 1 | **称号の分離** | 5,693 | `position_type` に `title` を追加して移す |
| 2 | **表記ゆれの統合** | 7組 | 大小文字。`Medicus` の同綴異義に注意 |
| 3 | **主要官職の統制** | 12,925 | `position_canonical` を付与 |
| 4 | 残り | 2,128（10.3%） | `position_abstract` のまま。統制しない |

マッピング表: [mapping/position_canonical_map.json](mapping/position_canonical_map.json)

称号17種 + 官職49種 = **18,618件（89.7%）**をカバーする。
上位50種だけでは 87.6% だが、称号の表記ゆれを拾うことで 89.7% になる。

### 4-4. tier — 官職の序列軸

`position_type`（行政単位: imperial / provincial / local / military …）とは
**直交する軸**として `tier` を定義する。

| tier | 意味 |
|---|---|
| title | 称号・権限（職務ではない） |
| senatorial | 元老院身分の官職 |
| equestrian | 騎士身分の官職 |
| municipal | 都市の官職 |
| military | 軍務 |
| priesthood | 祭司職 |
| occupation | 職業 |

同じ `consul` でも属州総督として記録されれば `position_type` は
`provincial-administration` になるが、`tier` は常に `senatorial` である。

### 4-5. 原文の確認が要るもの

以下は `position_abstract` が粗すぎて確定できない。`refine: true` を付けた。

| 値 | 理由 |
|---|---|
| `legatus` | legatus Augusti pro praetore（総督）と legatus legionis（軍団長） |
| `praefectus` | praefectus praetorio / aegypti / cohortis で階層が大きく異なる |
| `quaestor` | 都市のクァエストルと元老院のクァエストル |
| `decurio` | 都市参事会員と騎兵小隊長の同綴異義 |
| `tribunus` | tribunus militum と tribunus plebis |
| `eques` | 騎兵と騎士身分 |
| `magister` | magister vici / collegii / militum |

### 4-3. `position_type` の揺れ（§3-2）について

**本作業では扱わない。** 正当な区別と単なる揺れが混在しており、
原文を1件ずつ見る必要がある。称号を分離（4-2 #1）すれば分散の
主要因が消えるため、その後に再評価する。

---

## 5. 未確定の論点

| # | 論点 | 備考 |
|---|---|---|
| 1 | 称号を `position_type: title` とするか、別フィールドに出すか | career_path から出すとスキーマ変更が大きい |
| 2 | `position_canonical` の粒度 | `duovir` と `duumvir` を統合するか（別表記だが同一官職） |
| 3 | 統制語彙をオントロジーに載せるか | `epigp:` 名前空間を切るか |
| 4 | `position_abstract` を温存するか | 先行事例に倣えば温存（生成来歴） |

---

## 6. オントロジー実装（2026-10-17 完了）

`hmk_ontology/ontology/epig_ontology.ttl` に実装した（CLAUDE.md のとおり
オントロジーの編集は `hmk_ontology` 側で行う）。

### 6-1. 名前空間

```turtle
@prefix epigp: <http://epigraphic-careers.org/ontology/position/> .
```

### 6-2. クラス3つ・個体70

| クラス | 個体 | 内容 |
|---|---:|---|
| `epig:PositionType` | 11 | 行政単位（既存10 + `title`） |
| `epig:PositionTier` | 7 | 官職の序列軸 |
| `epig:Position` | 52 | 官職45 + 称号7 |

`epig:Position` の内訳: municipal 14 / military 11 / priesthood 10 /
senatorial 7 / equestrian 4 / occupation 3 / title 7。

語彙個体は `position_canonical_map.json` から機械生成しており、
**両者の値集合が完全に一致することを検証済み**（過不足ゼロ）。

### 6-3. プロパティ

| プロパティ | domain | range | 備考 |
|---|---|---|---|
| `epig:positionType` | CareerStatement | **PositionType** | **xsd:string から変更** |
| `epig:positionCanonical` | CareerStatement | Position | 新規 |
| `epig:positionTier` | CareerStatement ∪ Position | PositionTier | 新規 |
| `epig:positionCanonicalSource` | CareerStatement | xsd:string | 新規 |
| `epig:victoryTitle` | CareerStatement | xsd:string | 新規 |

`epig:positionAbstract`（`xsd:string`）は温存し、`rdfs:comment` に
旧値である旨を追記した。`objectType` ↔ `objectCategory` と同じ扱い。

### 6-4. 勝利称号の設計

`Germanicus` / `Parthicus` / `Dacicus` 等は**1個体 + 属性**とした。

```turtle
epigp:victory_title a epig:Position ;
    epig:positionTier epigp:tier_title .
```

具体的な対象地域は `epig:victoryTitle "Germania"` で区別する。
勝利称号は新たな征服のたびに増えうるため、個体を分けると語彙が
際限なく膨らむ。

### 6-5. 検証結果

| 項目 | 結果 |
|---|---|
| Turtle パース | OK（1,305 → 1,732 triples、+427） |
| Position の tier 付与 | 52/52 |
| notation と URI の一致 | 70/70 |
| en/ja ラベル | 70/70 |
| `skos:broader` の参照先 | 定義済み個体のみ（pontifex_maximus → pontifex） |
| マッピング表との一致 | 過不足ゼロ |
| 既存 triple の喪失 | **2件のみ**（意図した `positionType` の型変更） |

### 6-6. 【要対応】既存データの再生成

`epig:positionType` の range を `xsd:string` から `epig:PositionType` に
変更したため、**既存の RDF は型が一致しない**。

```turtle
# 現行の出力（文字列）
epig:positionType "imperial-administration"

# 新しい定義が期待する形
epig:positionType epigp:imperial_administration
```

`create_rdf_himiko.py` の出力変更と RDF の再生成が必要。
データ（JSON）側の `position_type` は文字列のままでよく、
RDF 生成時に URI へ写像する。

---

## 7. 適用結果（2026-10-17）

### 7-1. データへの適用

`pipeline/provenance/classify_position.py` を全件に適用した。

| | 件数 | 比率 |
|---|---:|---:|
| `career_path` 総数 | 20,750 | 100% |
| **統制語彙を付与** | **18,618** | **89.7%** |
| 統制対象外 | 2,132 | 10.3% |
| **`position_type` を `title` に変更** | **5,693** | 27.4% |

tier 別の内訳:

| tier | 件数 |
|---|---:|
| title | 5,693 |
| senatorial | 3,987 |
| priesthood | 3,660 |
| municipal | 2,488 |
| military | 1,782 |
| equestrian | 856 |
| occupation | 152 |

### 7-2. 称号の分離による効果

`position_type` の分布が改善した。

| position_type | 変更前 | 変更後 |
|---|---:|---:|
| imperial-administration | 7,386 | 3,188 |
| **other** | **1,314** | **513** |
| military | 2,968 | 2,274 |
| **title**（新規） | — | **5,693** |

`other` が **1,314 → 513** に減った。称号が「その他」に落ちていた分が
正しく分離されたため。

書き換えた `position_type` の元の値は `_provenance.value_history` に
残している。`career_path` は RDF 上では `_vN` 版を持つが、JSON 上は
同じキーに代入されるため元の値が消えるため。

### 7-3. RDF 出力

`create_rdf_himiko.py` に以下を追加した。

| プロパティ | 出現数 |
|---|---:|
| `epig:positionCanonical` | 40,806 |
| `epig:positionType`（URI 化） | 22,838 |
| `epig:positionTier` | 20,403 |
| `epig:positionCanonicalSource` | 20,403 |
| `epig:victoryTitle` | 749 |

v0（18,618）と v1（1,785、location enrich 済み）の両方に出力されるため
合計は 20,403。JSON の 18,618 と v0 の件数が一致する。

### 7-4. 検証結果

| 項目 | 結果 |
|---|---|
| バックアップとの照合 | 既存キーの変更・消失なし（`position_type` の title 化を除く） |
| `value_history` への記録 | 元の値を保持 |
| プロジェクトバリデータ | **0 errors / 56,918 inscriptions** |
| 語彙 URI の解決 | 158種すべて定義済み、未定義ゼロ |
| TriG パース | 36/36 成功（最大ファイル含む） |
| `tier=title` と `position_type=title` の不整合 | 0件 |

### 7-5. バリデータの更新

`pipeline/validation/validate_career_graphs.py` の
`VALID_POSITION_TYPES` に `title` を追加した。追加前は 5,693 件が
`invalid value 'title'` でエラーになっていた。
