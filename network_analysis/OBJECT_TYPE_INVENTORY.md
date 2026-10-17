# `object_type` 棚卸しとカテゴリ再設計案

調査日: 2026-10-05
対象: `validated_career_graphs/claude/` の全 `benefactions[].objects[]` — **7,590件**
調査方法: 全2,042ファイルを全件パース（サンプリングなし）。
`object_type=other` の2,833件は `object` / `object_description` / `benefaction_text` /
`notes` を突き合わせて内容を分類。

---

## 1. 結論

3点が判明した。

1. **現行語彙は14種ではなく「40種」。** 飽和した上位13種と、
   1〜2件しかない尻尾27種が混在している。統制語彙として機能していない。
2. **`other` 2,833件のうち、カテゴリ拡充で救えるのは約4割。**
   残り約6割は碑文側に情報がないか（15.6%）、ラテン語の汎用語
   （`monumentum`, `votum`, `donum`）そのものが記録されている（42.9%）。
   **語彙を増やしても `other` はゼロにならない。**
3. **残り28%は615種の超ロングテール**（最頻でも10件）。
   ルールベースでも新カテゴリ追加でも回収できない。

→ したがって**「カテゴリを豊かにする」だけでは不十分**で、
   §5 の方針転換（`other` の3分割 + 階層化 + 分類の再実行）が必要。

---

## 2. 現行 `object_type` の全40種

| # | object_type | 件数 | 評価 |
|---:|---|---:|---|
| 1 | other | 2,833 | **要再分類** |
| 2 | building | 1,157 | **抽象的すぎる（要階層化）** |
| 3 | statue | 572 | 可 |
| 4 | tomb | 524 | 可 |
| 5 | temple | 499 | 可 |
| 6 | money | 405 | 可 |
| 7 | altar | 312 | 可（`other` に28件取りこぼし） |
| 8 | road | 276 | 可 |
| 9 | public banquet | 171 | 可 |
| 10 | gladiatorial games | 131 | 可 |
| 11 | portico | 123 | 可 |
| 12 | sportulae | 110 | 可 |
| 13 | bath | 109 | 可 |
| 14 | theatrical performances | 83 | 可 |
| 15 | aqueduct | 68 | 可 |
| 16 | arch | 47 | 可 |
| 17 | bridge | 33 | 可 |
| 18 | basilica | 29 | 可 |
| 19 | forum | 16 | 可 |
| 20 | dedication | 13 | **行為であって対象物でない** |
| 21 | theater | 11 | 可 |
| 22 | ritual | 11 | **行為であって対象物でない** |
| 23 | games | 9 | `gladiatorial games` と重複 |
| 24 | unknown | 7 | `other` と重複 |
| 25 | monument | 7 | 汎用語 |
| 26 | wall | 7 | 可 |
| 27 | city | 5 | 粒度が異なる |
| 28 | fountain | 4 | `water source` と重複 |
| 29 | signum | 4 | `statue` と重複 |
| 30 | land | 2 | 可（`other` に35件取りこぼし） |
| 31 | shrine | 2 | `temple` と重複 |
| 32 | ritual sacrifice | 2 | 可（`other` に24件取りこぼし） |
| 33 | water source | 1 | `fountain` と重複 |
| 34 | military infrastructure | 1 | — |
| 35 | votive offering | 1 | — |
| 36 | decoration | 1 | 可（`other` に18件取りこぼし） |
| 37 | column | 1 | 可（`other` に46件取りこぼし） |
| 38 | congiarium | 1 | `sportulae` と重複 |
| 39 | vicus | 1 | 粒度が異なる |
| 40 | church | 1 | 可 |

### 観察された問題

- **重複・ゆれ**: `games`/`gladiatorial games`、`fountain`/`water source`、
  `signum`/`statue`、`shrine`/`temple`、`congiarium`/`sportulae`、`unknown`/`other`
- **カテゴリ軸の混在**: `dedication`・`ritual` は**行為**、
  `city`・`vicus` は**地理単位**であり、「寄進対象物」ではない
- **取りこぼし**: `column`(1件) に対し `other` 内に46件、
  `land`(2件) に対し35件、`ritual sacrifice`(2件) に対し24件、
  `decoration`(1件) に対し18件、`altar`(312件) に対しても28件が `other` に落ちている
  → **語彙不足ではなく抽出時の判定ブレ**。カテゴリを増やすだけでは直らない

---

## 3. `other` 2,833件の内訳（実測）

| 区分 | 件数 | 比率 | 対応 |
|---|---:|---:|---|
| **GENERIC**（ラテン語の汎用語そのもの） | 1,214 | 42.9% | 新カテゴリで受ける |
| **UNMATCHED**（615種のロングテール） | 793 | 28.0% | LLM再分類が必要 |
| **UNCLASSIFIABLE**（判読不能・動詞のみ） | 443 | 15.6% | **回収不能**。`unknown` 明示 |
| **SPECIFIC**（既存／新カテゴリに割当可能） | 383 | 13.5% | 機械的に再割当可能 |

### 3-1. GENERIC（1,214件・42.9%） — 汎用語が記録されている

碑文が「何を」としか書いていないケース。カテゴリ不足ではない。

| 内容 | 件数 | 代表形 |
|---|---:|---|
| 記念物・銘文一般 | 843 | `monumentum/titulus`, `inscription/monument`, `titulum` |
| 奉献物一般 | 246 | `votum`, `sacrum`, `vota` |
| 贈与一般 | 84 | `donum`, `munificentia`, `liberalitas` |
| 追悼一般 | 41 | `memoria`, `memoriae` |

> これらは `monumentum`（記念物）という語しか碑文にない。
> 「建物か像か祭壇か」は**原文から決定不能**。
> 新設する `monument.generic` / `votive.generic` で正直に受けるべき。

### 3-2. SPECIFIC（383件・13.5%） — 再割当可能

| 割当先 | 件数 | 代表形 |
|---|---:|---|
| funerary.tomb_structure | 57 | `sepulcrum`, `tumulum`, `cupulam` |
| altar（既存へ取りこぼし回収） | 49 | `aram`, `ara`, `aram cum fundamentis` |
| building.element | 46 | `columnis`, `marmoribus`, `opus doliare` |
| land.estate | 35 | `fines provinciae`, `agri publici`, `praedia` |
| privilege.legal_status | 32 | `civitas`, `honor`, `municipium`, `libertas` |
| distribution.food | 27 | `vinum`, `tritici modios`, `semodium` |
| offering.sacrificial_animal | 24 | `agnum`, `taurum`, `vaccam`, `verbecem` |
| vessel_equipment | 19 | `urceum`, `candelabra`, `lucernas`, `aenea` |
| decoration.ornament | 18 | `ornamenta`, `omnibus ornamentis` |
| infrastructure.bridge | 17 | `pontes`, `pontibus` |
| funerary.mensa | 16 | `mensa`, `mensas`, `mensa martyrum` |
| building.education_culture | 16 | `gymnasium`, `gymnasia` |
| infrastructure.milestone | 10 | `miliaria` |
| distribution.largesse | 9 | `missilia` |
| infrastructure.water | 5 | `cisternam`, `lacus` |

**新規性の高い発見**: 供犠動物（`agnum`/`taurum`/`verbecem`）24件、
土地・境界（`fines provinciae`/`agri publici`）35件、
法的身分（`civitas`/`libertas`）32件は、現行語彙に受け皿が存在しない。

### 3-3. UNCLASSIFIABLE（443件・15.6%） — 回収不能

| 内容 | 件数 | 代表形 |
|---|---:|---|
| 判読不能・欠損 | 315 | `unknown`, `[unknown object]`, `[object not preserved]`, `[---]` |
| 動詞のみ（目的語なし） | 128 | `fecit`, `posuit`, `restituit`, `dedicavit` |

碑文が破損しているか、原文に目的語がない。
**どれだけカテゴリを増やしても分類できない。**
`other` に混ぜず `unknown` として明示的に分離すべき。

### 3-4. UNMATCHED（793件・28.0%） — 615種のロングテール

最頻でも10件という極端な裾野。代表例:

```
 10  [Bonae] Menti          6  vestigium              6  trit(ici) mo(dios) X m(ilia)
  5  hanc tabulam           4  liberalitates parentum  3  maceria cinctam
  3  fundamenta             3  conubium               2  horologio（日時計）
  2  coronam                2  picturis               2  thorace Caelestis Augustae
  2  museis                 2  carmina                2  gradus n(umero) IIII
  2  palma argentea         2  urbem                  2  vestem
```

一部は新カテゴリで拾える（`horologio`→設備、`picturis`→装飾、
`fundamenta`/`maceria`→建築部材、`coronam`/`palma argentea`→記念品）が、
**ルールベースでは限界**。原文の文脈解釈が要るため LLM による再分類が必要。

---

## 4. カテゴリ再設計案（2階層）

ご指摘のとおり `building` は抽象的すぎる（1,157件＝最大の実体カテゴリ）。
**`category`（第1階層・粗い軸）＋ `subtype`（第2階層・細かい軸）** の2層とし、
ネットワーク分析時に粒度を選べるようにする。

> 設計方針
> - 第1階層は **9種に固定**。投影グラフのノードとして使える粒度
> - 第2階層は拡張可能。未知の対象は第1階層のみ埋めて `subtype=null` を許す
> - **物理的対象と非物理的恩恵を別の第1階層に分離**（`privilege` / `distribution`）
> - 判読不能は `unknown` に隔離し、`other` を廃止

### 第1階層（category）

| category | 内容 | 推定件数 |
|---|---|---:|
| `structure` | 建造物・建築物 | 約2,400 |
| `monument` | 像・祭壇・銘文・記念物 | 約1,700 |
| `funerary` | 墓・埋葬関連 | 約650 |
| `infrastructure` | 道路・水道・橋・里程標 | 約420 |
| `distribution` | 金銭・食糧・施与 | 約780 |
| `spectacle` | 競技会・演劇・饗宴 | 約400 |
| `offering` | 供犠・奉献物 | 約290 |
| `privilege` | 法的身分・特権（非物理） | 約35 |
| `unknown` | 判読不能・特定不能 | 約450 |

### 第2階層（subtype）

#### structure（`building` の解体）

| subtype | 現行からの移行元 | 件数 |
|---|---|---:|
| `structure.temple` | temple, shrine | 501 |
| `structure.bath` | bath | 109 |
| `structure.portico` | portico | 123 |
| `structure.basilica` | basilica | 29 |
| `structure.theater` | theater | 11 |
| `structure.arch` | arch | 47 |
| `structure.forum` | forum | 16 |
| `structure.wall` | wall | 7 |
| `structure.gymnasium` | （新設） | 16 |
| `structure.utility` | （新設）horreum, macellum, taberna | 少数 |
| `structure.element` | （新設）column, marmor, fundamenta, pavimentum | 約46+ |
| `structure.church` | church | 1 |

> **訂正（§7で確定）**: 当初この表に `structure.unspecified`（building の残余
> 約1,157件）を置き、「機械的に細分できないため温存」としていたが、
> **これは誤りだった**。`building` 1,157件を実測した結果、43.0%は機械的に降格可能、
> 36.7%もLLMで分類可能で、真に特定不能なのは20.2%（234件）のみ。
> 詳細と確定後の内訳は §7-2 を参照。

#### monument

| subtype | 移行元 | 件数 |
|---|---|---:|
| `monument.statue` | statue, signum | 576 |
| `monument.altar` | altar + other内49 | 361 |
| `monument.inscription` | （新設）titulus | 約843 |
| `monument.decoration` | decoration + other内18 | 19 |
| `monument.vessel` | （新設）urceus, candelabrum, lucerna | 19 |

> **訂正（§7で確定）**: 当初この表に `monument.generic`（約843件）を置いていたが、
> `structure.unspecified` との間に意味上の違いがなく、**両者とも廃止**した。
> 代替カテゴリは §7-1 を参照。

#### funerary

| subtype | 移行元 | 件数 |
|---|---|---:|
| `funerary.tomb` | tomb | 524 |
| `funerary.tomb_structure` | （新設）sepulcrum, tumulus, cupula | 57 |
| `funerary.mensa` | （新設）mensa | 16 |
| `funerary.memoria` | （新設）memoria | 41 |

#### infrastructure

| subtype | 移行元 | 件数 |
|---|---|---:|
| `infrastructure.road` | road | 276 |
| `infrastructure.aqueduct` | aqueduct | 68 |
| `infrastructure.bridge` | bridge + other内17 | 50 |
| `infrastructure.water` | fountain, water source + other内5 | 10 |
| `infrastructure.milestone` | （新設）miliarium | 10 |
| `infrastructure.military` | military infrastructure | 1 |

#### distribution

| subtype | 移行元 | 件数 |
|---|---|---:|
| `distribution.money` | money | 405 |
| `distribution.sportulae` | sportulae, congiarium | 111 |
| `distribution.banquet` | public banquet | 171 |
| `distribution.food` | （新設）vinum, triticum, oleum | 27 |
| `distribution.largesse` | （新設）missilia | 9 |

#### spectacle

| subtype | 移行元 | 件数 |
|---|---|---:|
| `spectacle.gladiatorial` | gladiatorial games, games | 140 |
| `spectacle.theatrical` | theatrical performances | 83 |

#### offering（新設の第1階層）

| subtype | 移行元 | 件数 |
|---|---|---:|
| `offering.sacrifice` | ritual sacrifice + other内24 | 26 |
| `offering.votive` | votive offering | 1 |
| `offering.generic` | **GENERIC受け皿**（votum, sacrum） | 約246 |

#### land / privilege（新設の第1階層）

| subtype | 移行元 | 件数 |
|---|---|---:|
| `land.estate` | land + other内35 | 37 |
| `privilege.legal_status` | （新設）civitas, libertas, honor, municipium | 32 |

> `privilege` は**物理的対象ではない**。
> `city` / `vicus`（粒度が異なる既存値）もここに吸収する。

#### unknown

| subtype | 移行元 | 件数 |
|---|---|---:|
| `unknown.illegible` | other内315 + unknown 7 | 322 |
| `unknown.verb_only` | other内128 | 128 |

---

## 5. 推奨する進め方

### 再抽出は不要

**重要**: `benefaction_text` は対象2,698件中 **2,697件（100%）に存在**する。
ラテン語原文と `object_description`（英訳）が両方残っている。

→ **EDCS からのスクレイピングをやり直す必要はない。**
既存JSON内の `object` + `object_description` + `benefaction_text` を入力として、
**分類パスだけを再実行**できる。

### 処理対象の切り分け（コスト最小化）

| 対象 | 件数 | 処理 |
|---|---:|---|
| 既存13カテゴリの明確なもの | 3,836 | **機械的マッピングのみ**（LLM不要） |
| `other` のうち SPECIFIC | 383 | **ルールベースで再割当**（LLM不要） |
| `other` のうち GENERIC | 1,214 | **機械的に generic カテゴリへ**（LLM不要） |
| `other` のうち UNCLASSIFIABLE | 443 | **機械的に unknown へ**（LLM不要） |
| `other` のうち UNMATCHED | **793** | **LLM再分類が必要** |
| `building` の降格判定 | **1,157** | **LLM再分類が必要** |

→ **LLM 呼び出しは 1,950件のみ**。全7,590件の再処理に対し **約26%** で済む。

### 手順

1. 第1階層9種・第2階層の統制語彙を確定（本書 §4 を叩き台に）
2. 機械的マッピング表を作成し、LLM不要の5,876件を一括変換
3. 残り1,950件を LLM で分類（`benefaction_text` を根拠として渡し、
   `category` / `subtype` / 判定根拠を返させる）
4. `subtype=null` を許容する運用とし、無理な細分を強制しない
5. ネットワーク分析側は **第1階層をデフォルト**、
   必要に応じ第2階層に降りる実装にする

---

## 6. 論点の状態

| # | 論点 | 状態 |
|---|---|---|
| 1 | `structure.unspecified` / `monument.generic` の扱い | **確定** → §7-1（廃止） |
| 2 | `privilege` を寄進対象に含めるか | **確定** → §7-3（現状維持） |
| 3 | `building` 1,157件の分解可能性 | **確定** → §7-2 |
| 4 | 既知の不整合（多重割当） | **判明** → §7-4 |
| 5 | `offering.sacrifice` は「対象物」か「宗教行為」か。`benefaction_type`（行為の軸）との役割分担 | **未確定** |
| 6 | 旧 `object_type` を後方互換で残すか、完全置換するか | **未確定** |

---

# 第2部: 確定事項

最終更新: 2026-10-05

ここまでの検討で確定した事項をまとめる。
§1〜§5 は調査の経緯、本節以降が**実装時に参照すべき確定仕様**。

---

## 7. 確定事項

### 7-0. サマリ

| # | 決定 | 根拠 |
|---|---|---|
| 1 | 現行 `object_type`（40値・フラット）を**廃止**し、2階層の統制語彙に置換 | 重複・軸の混在・取りこぼし（§2） |
| 2 | 第1階層 `category` を **9種に固定** | 投影グラフのノードとして使える粒度 |
| 3 | 第2階層 `subtype` は**拡張可能・null許容** | 無理な細分を強制しない |
| 4 | `building` を解体して `structure.*` に細分 | 抽象的すぎる（最大の実体カテゴリ） |
| 5 | `structure.unspecified` / `monument.generic` の二本立ては**廃止** | 両者に意味上の違いがなかった（§7-1） |
| 6 | `privilege` は**第1階層で分離**のうえ現状維持 | §7-3 |
| 7 | 判読不能は `unknown.*` に**隔離**し、`other` を廃止 | 「分類できない」と「分類していない」を区別 |
| 8 | **再抽出は不要**。分類パスのみ再実行 | `benefaction_text` が100%存在（§7-5） |

**運用規則**

- `category`（第1階層9種）は**必須**。いずれかを必ず埋める
- `subtype`（第2階層）は**任意**。確定できない場合は `null`
- ネットワーク分析は**第1階層をデフォルト**とし、必要に応じ第2階層に降りる

---

### 7-1. 【確定】`structure.unspecified` / `monument.generic` の廃止

§4 の前案ではこの2つを併置したが、**両者に意味上の違いはなかった**ため廃止する。

#### 廃止の理由

定義したつもりだった基準と、実データ上の実態が一致していなかった。

| 前案のカテゴリ | 意図した基準 | 実際の基準 |
|---|---|---|
| `structure.unspecified` | 建造物だが種類不明 | 元が `object_type=building` だった |
| `monument.generic` | 記念物だが種類不明 | 元が `object_type=other` だった |

これは意味上の境界ではなく、**「元がどの値だったか」という来歴の差**でしかない。

#### 決定的な証拠

同一の表層形 `monumentum` が、3つの異なる `object_type` に割り振られている。

```
monumentum  →  tomb: 106 / building: 40 / other: 48
```

前案では、このうち40件が `structure.unspecified`、48件が `monument.generic` へ行き、
**まったく同じ語が別カテゴリに分かれたまま固定される**。再分類の目的に反する。

#### 代替: 原文の記述内容で分ける

来歴ではなく「**原文に何と書かれているか**」を基準にする。

| カテゴリ | 基準 | 件数 |
|---|---|---:|
| `monument.unspecified` | 原文が `monumentum` / `memoria` としか書いていない。**記念物であることは確実だが、墓か建物か像かが原文から決まらない** | 約900 |
| `offering.unspecified` | 原文が `votum` / `sacrum` としか書いていない | 約246 |
| `unknown.illegible` | 原文が破損・欠落し、対象を特定できない | 約556 |

前2者は**史料側の限界を表すカテゴリ**として意味を持つ。
最後の1つは単なる情報欠落であり、性質が異なるので分離する。

---

### 7-2. 【確定】`building` 1,157件の分解可能性

§4 で「機械的に細分できないため温存」としたのは**誤り**だった。
全1,157件を実測した結果、大半が分解可能。

| 区分 | 件数 | 比率 |
|---|---:|---:|
| 機械的に `structure.*` 等へ降格可能 | 498 | 43.0% |
| ロングテール 280種（LLM判定が必要） | 425 | 36.7% |
| 真に特定不能（`unknown structure`, `opus`, `aedificium`） | 234 | 20.2% |

#### 機械的に降格可能な内訳（498件）

| 降格先 | 件数 | 代表形 |
|---|---:|---|
| `structure.element` | 96 | `pilas III`, `fundamenta ex caemento`, `gradus` |
| `structure.portico` | 55 | `porticum`, `porticus` |
| `structure.arch` | 52 | `arcum`, `porta` |
| `funerary.tomb_structure` | 52 | `monumentum/sepulcrum`, `cupula`, `mausoleum` |
| `structure.utility` | 50 | `cellam promam`, `macellum`, `apothecam` |
| `structure.domestic` | 43 | `domum`, `domum Romulam` |
| `structure.wall` | 41 | `turres`, `moenia`, `murum` |
| `structure.gymnasium` | 38 | `gymnasium`, `xystis` |
| `structure.civic` | 27 | `tribunal`, `rostra`, `curia` |
| `structure.water` | 11 | `cisterna`, `piscinam` |
| `structure.theater` | 10 | `theatrum`, `amphitheatrum` |
| `structure.forum` | 10 | `forum`, `area macelli` |
| `structure.basilica` | 8 | `basilica`, `basilica nova` |
| `structure.temple` | 5 | `aedem sive curiam` |

#### ロングテール 280種（425件）の性質

`monumentum` 40件のほか、具体語が大半を占める:

```
str]atura areae 4 / moles 4 / absides 4 / exedrae 4 / pronaum 3
cubicula IIII 4 / fossam 4 / lacum 4 / sedes 4 / tecta 3 / culmina 2
praedia 3+4 / turrem 3 / podium 2 / horologio
```

また `mon<u=i>mentum` / `mon(umentum)` / `gymnassium` / `gy]mnasium` のような
**正書法・翻刻記号のゆれ**も含む。

→ 「特定不能」ではなく**LLMで分類可能**。正規化処理も併せて行う。

---

### 7-3. 【確定】`privilege` の扱い — 現状維持

**第1階層で分離できている以上、`benefaction` の枠内に置いたままとする。**

`civitas` 付与等は厳密には「寄進」ではなく皇帝の恩恵だが、
第1階層 `privilege` として独立しているため、
分析時に `category != 'privilege'` で除外でき実害がない。
`benefaction` の枠から外す改修は**行わない**。

| subtype | 移行元 | 件数 |
|---|---|---:|
| `privilege.legal_status` | （新設）civitas, libertas, honor, municipium | 32 |
| `privilege.land` | land + other内35（praedia, agri publici, fines） | 37 |

---

### 7-4. 【判明】既知の不整合 — 121種の多重割当

同一の表層形が複数の `object_type` に割り振られている事例が **121種**存在する。
これは語彙設計の問題ではなく**既存データの不整合**であり、
再分類時に機械的に検出・統一する。

| 表層形 | 現状の分裂 | 統一先 |
|---|---|---|
| `monumentum` | tomb 106 / building 40 / other 48 | 文脈により `funerary.tomb` または `monument.unspecified` |
| `sacrum` | altar 17 / other 64 / dedication 8 / temple 27 | 文脈により `monument.altar` / `structure.temple` / `offering.unspecified` |
| `aram` | altar 53 / other 24 / building 1 | `monument.altar` |
| `arcum` | arch 19 / **building 26** | `structure.arch` |
| `porticum` | portico 44 / **building 17** | `structure.portico` |
| `gymnasium` | building 27 / gladiatorial games 5 / other 6 | `structure.gymnasium` |
| `memoria` | tomb 13 / building 5 / other 20 | `funerary.memoria` |
| `votum` | other 143 / altar 1 | `offering.unspecified` |
| `monumentum funerarium` | tomb 267 / building 4 / other 3 | `funerary.tomb` |

`arcum`・`porticum` は**専用カテゴリが存在するにもかかわらず**
それぞれ26件・17件が `building` に落ちている。
**語彙不足ではなく抽出時の判定ブレ**であり、カテゴリ追加だけでは解決しない。

---

### 7-5. 【確定】移行方式と処理コスト

#### 再抽出は不要

`benefaction_text` は対象2,698件中 **2,697件（100%）に存在**。
ラテン語原文と `object_description`（英訳）が両方残っている。

→ **EDCS からのスクレイピングをやり直す必要はない。**
既存JSON内の `object` + `object_description` + `benefaction_text` を入力として、
**分類パスのみ再実行**する。

#### 処理対象の切り分け

| 対象 | 件数 | 処理 |
|---|---:|---|
| 既存カテゴリの明確なもの | 3,836 | 機械的マッピング（LLM不要） |
| `other` のうち SPECIFIC | 383 | ルールベース再割当（LLM不要） |
| `other` のうち GENERIC | 1,214 | 機械的に `*.unspecified` へ（LLM不要） |
| `other` のうち UNCLASSIFIABLE | 443 | 機械的に `unknown.*` へ（LLM不要） |
| `building` のうち機械的降格可能 | 498 | ルールベース再割当（LLM不要） |
| `building` のうち特定不能 | 234 | 機械的に `unknown.illegible` へ（LLM不要） |
| **`other` の UNMATCHED（615種）** | **793** | **LLM再分類** |
| **`building` のロングテール（280種）** | **425** | **LLM再分類** |

**LLM呼び出しは 1,218件のみ**（全7,590件に対し **約16%**）。

> §5 時点では1,950件（26%）と見積もっていたが、
> `building` の実測により機械処理可能な範囲が広がり、**約16%に縮小**した。

#### 手順

1. 第1階層9種・第2階層の統制語彙を確定（**完了**）
2. 機械的マッピング表を作成し、LLM不要の 6,372件を一括変換
3. 残り 1,218件を LLM で分類
   （`benefaction_text` を根拠として渡し、`category` / `subtype` / 判定根拠を返させる）
4. §7-4 の121種の多重割当を検出・統一
5. 正書法・翻刻記号のゆれ（`mon<u=i>mentum` 等）を正規化
6. `subtype=null` を許容する運用とし、無理な細分を強制しない

---

### 7-6. 【実装】マッピング表と検証結果

マッピング表を作成し、全7,590件に適用して検証した。

| ファイル | 内容 |
|---|---|
| [mapping/object_category_map.json](mapping/object_category_map.json) | マッピング表（機械可読） |
| [mapping/apply_mapping.py](mapping/apply_mapping.py) | 適用・検証スクリプト |
| [mapping/coverage_report.json](mapping/coverage_report.json) | 検証結果 |

#### 解決の優先順位

1. `normalize_surface` — 翻刻記号・正書法のゆれを除去
   （`mon<u=I>mentum`→`monumentum`、`fec(it)`→`fecit`、`[miliari]a`→`miliaria`）
2. `ambiguous_forms` — §7-4 の多重割当の既知形を最優先で確定
3. `surface_rules` — 表層形の正規表現 48本（上から順に最初にマッチしたもの）
4. `object_type_direct` — 表層形で決まらない場合に旧 `object_type` から引く
5. 未解決 → `needs_llm`

#### 検証結果（実測）

| 区分 | 件数 | 比率 |
|---|---:|---:|
| **カテゴリ確定（機械処理のみ）** | **6,628** | **87.3%** |
| └ うち `refine_llm` 推奨（任意） | 361 | 4.8% |
| **`needs_llm`（LLM判定が必須）** | **962** | **12.7%** |

解決方法の内訳: 表層形ルール 4,951件（65.2%）／
`object_type` フォールバック 1,449件（19.1%）／多重割当の既知形 1,190件（15.7%）。

> **見積もりの修正**: §7-5 では LLM 呼び出しを 1,218件（16%）と見積もっていたが、
> 実際に適用した結果 **962件（12.7%）** に縮小した。
> 当初 `monumentum`(193) / `sacrum`(116) を LLM 必須に数えていたが、
> これらは**既定カテゴリが決まっている**ため必須ではない（下記参照）。

#### `needs_llm` と `refine_llm` の区別

当初は両者を混同しており、必要コストを過大評価していた。仕様上分離した。

| フラグ | 意味 | 件数 |
|---|---|---:|
| `needs_llm` | カテゴリが決まらない。**判定必須**。未処理では使えない | 962 |
| `refine_llm` | 既定カテゴリは確定済み。文脈次第でより適切な分類がありうる**任意パス** | 361 |

`monumentum`・`sacrum`・`ritual`・`dedication` は `refine_llm`。
既定値（`monument.unspecified` / `offering.unspecified`）のままでも分析可能で、
精度を上げたい場合のみ LLM に回す。

#### `needs_llm` 962件の性質

743種の distinct 表層形、最頻でも16件という**完全なロングテール**。

```
16 opus / 10 [Bonae] Menti / 6 vestigium / 6 vetustate conlapsum
 5 structure (unspecified) / 5 operis / 6 criobolium
```

ルールベースでの追加回収は費用対効果が低い。LLM に委ねるのが妥当。

#### 第1階層の分布（検証後）

| category | 件数 | 比率 |
|---|---:|---:|
| monument | 2,033 | 26.8% |
| structure | 1,859 | 24.5% |
| distribution | 728 | 9.6% |
| （未解決→LLM） | 623 | 8.2% |
| unknown | 576 | 7.6% |
| offering | 561 | 7.4% |
| funerary | 523 | 6.9% |
| infrastructure | 399 | 5.3% |
| spectacle | 181 | 2.4% |
| privilege | 107 | 1.4% |

旧 `other` 2,833件（37.3%）という単一の巨大カテゴリが解消され、
第1階層で最大のものが 26.8% に収まった。

---

### 7-7. ネットワーク分析側への影響

- **デフォルトは第1階層9種**を投影グラフのノードとして使う
- `monument.unspecified`（約900）・`unknown.*`（約684）は
  **人工的ハブになるため、分析時に除外するオプションを必ず用意する**
  （旧 `other` 2,833件で発生していた問題の再発防止）
- 第2階層まで降りる分析は、件数が十分なカテゴリに限定する
