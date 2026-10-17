# Chen (2023) の手法による共在ネットワーク — 試作

調査日: 2026-10-13 / 10-14（氏族名版を追加）
対象データ: `pipeline/provenance/validated_career_graphs/claude/`（2,042ファイル）

---

## 1. 結論

**Chen の手法（二部グラフ + Louvain）は本データでは機能しない。
しかし地域性は実在し、集中度分析に切り替えれば検出できる。**

| アプローチ | 結果 |
|---|---|
| 恵与対象 × 場所 → Louvain | 投影が密度 0.945、分割不能 |
| 神格 × 場所 → Louvain | Q = 0.09〜0.15、帰無モデル以下 |
| 氏族名 × 場所 → Louvain | Q = 0.083、帰無モデル以下 |
| **氏族名 → 集中度分析** | **162名中44名が有意に空間集中（Moran z > 1.96）** |
| **恵与対象 × 恵与対象（同一碑文内）** | **Louvain は不発だが、48ペア中27ペアが有意に共起（§1-2）** |
| **役職 × 役職（同一碑文・別人同士）** | **32ペア中18ペアが有意。属州別で初めて帰無を上回る（§1-3）** |
| **氏族名 × 氏族名（同一碑文・非血縁）** | **92ペア中8ペアが有意。属州で軸が変わる（§1-4）** |
| **経歴内の隣接役職（cursus）** | **セクター間に二経路の分離。年代不要（§1-5・最有望）** |

> ### ⚠ §1-2〜§1-4 に共通する限界 — 年代を考慮していない
>
> 恵与対象・役職共起・氏族名共起は**すべて無向共起**であり、
> 約700年分の碑文を1枚のネットワークに潰している。
> **これらの所見は「地域差」とも「時代差」とも解釈でき、両者を区別できない。**
>
> 例えば §1-3 の「Numidia は legatus 単一ハブ、Africa proconsularis は2極構造」は
> 統治構造の地域差として記述したが、Numidia が軍団属州として分離したのは
> 2世紀末〜3世紀であり、**同じデータは時代差でも説明できる**。
> §1-4 の `Aurelius` 絡みのペアも、212年のカラカラ勅令前後で
> 語の意味が変わるため年代なしでは解釈できない。
>
> 年代の付与率は **18.2%**（51,941件中9,466件、幅の中央値59年）。
> 年代別に切ると各分析の母数は 27〜43% に落ちるうえ、
> **年代付き碑文は無作為標本ではない**（経歴記載率 32% 対 11%。
> 皇帝名や執政官年号を含む公的碑文に偏る）。
> 年代で切ることは碑文の性格で切ることでもある。
>
> **§1-5 はこの問題を構造的に回避する**（cursus は内部に相対順序を持つ）。
> 歴史解釈を目指すなら §1-5 が最も有望。

原因は**データが入れ子構造（nested）でモジュール構造でない**こと（§4-2）。
Louvain の失敗は手法の誤適用であって、データに構造がないことを意味しない。

帰無モデル40回との比較:

| 構成 | 投影 | Louvain Q | 帰無モデル | 判定 |
|---|---|---:|---|---|
| 皇帝込み | deity–deity | 0.148 | 0.108 ± 0.004、**z = +9.17** | ランダム超過 |
| 皇帝込み | place–place | 0.087 | 0.113 ± 0.005、z = −5.03 | 下回る |
| 神のみ | deity–deity | 0.125 | 0.161 ± 0.009、z = −3.91 | 下回る |
| 神のみ | place–place | 0.113 | 0.170 ± 0.011、z = −5.43 | 下回る |

4構成中、ランダムを超えるのは「皇帝込みの deity–deity」のみ。
しかもその Q=0.148 は構造ありとされる水準（目安 0.3）に届かない。

z>0 になるのは皇帝崇拝が**帝国全土に一様分布する**ためで、
「ネルウァとトラヤヌスはどこでも共起する」という同語反復に近い。
地域文化の検出とは言いがたい。

### 1-0. 氏族名（nomen）でも Louvain では出ない。ただし地域性は実在する

神格の次に氏族名を試した（`build_nomen_network.py`）。
データ量は神格の約9倍、形も Chen に近い。

| | 種類数 | 場所数 | 比 | 二部密度 |
|---|---:|---:|---:|---:|
| Chen | 83 cults | 56 places | 1.48 | 0.081 |
| 神格 | 125 | 127 | 0.98 | 0.047 |
| **氏族名** | **1,267** | **660** | **1.37** | 0.012 |

それでも **Q = 0.083（place–place）/ 0.105（nomen–nomen）**、
帰無モデルに対し z = −9.65 / −6.72。閾値を12通り変えても Q は 0.083 を超えない。

**しかし、個々の氏族名を見ると地域性は明確に存在する。**
正規化エントロピー H（0 = 一地点集中、1 = 均等分散、n≥40 の氏族名）:

| 氏族名 | H | 件数 | 地点 | 上位地点 |
|---|---:|---:|---:|---|
| Antistius | 0.665 | 112 | 24 | Thibilis 58 |
| Gabinius | 0.681 | 90 | 21 | **Dougga 45** |
| **Sittius** | **0.732** | **399** | **44** | **Thibilis 96, Cirta 56, Tiddis 44** |
| Sittia | 0.746 | 228 | 37 | Cirta 50, Thibilis 36 |
| ⋯ | | | | |
| Cocceius | 0.958 | 97 | 58 | （分散） |
| Flavius Claudius | 0.982 | 48 | 38 | （分散） |

**Sittius の分布は歴史的事実と一致する。** 前44年、シッティウスの従者が
キルタ周辺に入植した結果が、Thibilis・Cirta・Tiddis という
**キルタ連合（confederatio Cirtensis）** の中心地への集中として現れている。
Gabinius が Dougga に集中するのも同様の構図。

つまり **「地域性がない」のではなく、Louvain による分割では捉えられない**。
理由は §4-2 に示す。

### 1-0b. 集中度分析では地域性が検出できる（`concentration.py`）

Louvain を捨て、氏族名ごとの**空間分布の偏り**を測った。結果は明確。

| 指標 | 内容 |
|---|---|
| 正規化エントロピー H | 0 = 一地点集中、1 = 均等分散 |
| 分散距離 disp | 出現数で重み付けした重心からの平均距離（km） |
| **Moran's I** | 空間的自己相関。z > 1.96 で有意に集中 |

**158 名中 42 名（27%）が Moran's I で有意に空間集中**（z > 1.96）。

| 氏族名 | n | H | disp | z | 上位地点 |
|---|---:|---:|---:|---:|---|
| **Sittia** | 228 | 0.746 | **58km** | **10.8** | Cirta 22% |
| **Sittius** | 399 | 0.732 | **61km** | **8.9** | Thibilis 24% |
| Seius | 79 | 0.902 | 121km | 8.3 | Thibilis |
| Fonteius | 36 | 0.828 | 68km | 5.8 | Lambaesis |
| Cornelia | 245 | 0.876 | 131km | 5.0 | Thibilis |
| ⋯ | | | | | |
| Cocceius | 97 | 0.958 | **258km** | 0.4 | （分散） |
| Acilius | 40 | 0.960 | **249km** | 0.9 | （分散） |

分散距離が決定的で、**集中型 58〜100km 対 分散型 192〜258km** と明瞭に分かれる。
Sittius/Sittia がキルタ連合に集中する史実が、z = 8.9 / 10.8 という
高い有意性で再現された。

> **実装上の重要な注意**: Moran's I は**不在地点を 0 として含める**必要がある。
> 当初は出現地点のみで計算し、Sittius が z = 0.81（有意でない）になっていた。
> 「ある地点に無い」ことは欠測ではなく情報であり、
> 全823地点を含めると z = 8.94 になる。この違いは決定的。

#### 地図（`plot_concentration.py`）

| 図 | 内容 |
|---|---|
| `map1_overview.png` | 全出土地（灰）に、空間集中した42名の重心（橙）を重ねた図。重心がキルタ〜Thibilis 周辺に密集することが見て取れる |
| **`map2_examples.png`** | **最も明快。** 集中型（Sittia/Sittius/Seius）と分散型（Numisius/Caesius/Volusius）を同一縮尺で並べた小多重図 |
| `fig4_dispersion_entropy.png` | 分散距離 × エントロピーの散布図 |

背景地図は **Pleiades / Pelagios の属州ポリゴン**
（`pipeline/case_study/pleiades-regions-magis-pelagios.geojson`、リポジトリ内に既存）
を GeoJSON から直接描画している。cartopy / geopandas は未導入だが、
今回の問いは地域性なので海岸線より**属州境界**の方が読み手の助けになる。

Pleiades は同一属州に時代・典拠の異なる複数ポリゴンを持つため、
境界線は概略であって厳密な行政区画ではない。

> **散布図が示したこと**: 当初「2つの regime」と想定したが、実際は
> **連続的なグラデーション**だった。集中型と分散型は両端であって、
> 離散的な2群ではない。図のタイトルもそう修正した。

> **発見した不具合**: 当初 `Nerva`（421km）と `Traianus`（281km）が
> 「最も分散した氏族名」として出ていた。これらは氏族名ではなく皇帝の
> コグノーメンで、抽出時に nomen 欄に入ったもの。`Aurellius` のような
> 綴り異表記も除外漏れしていた。皇帝フィルタに追加し、
> 重子音の正規化を入れて修正（162名 → 158名、44 → 42）。

### 1-1. 属州別に絞っても改善しない

Chen の対象が単一文化圏（長江下流域・56地点）であることを踏まえ、
属州ごとに分割して再実行した（deity–deity 投影、神のみ、帰無モデル30回）。

| 範囲 | 場所 | 神格 | 二部密度 | Q | 帰無 | z |
|---|---:|---:|---:|---:|---:|---:|
| 北アフリカ全域 | 127 | 125 | 0.047 | 0.125 | 0.160 | −3.32 |
| Africa proconsularis | 87 | 89 | **0.060** | 0.109 | 0.165 | −4.58 |
| Numidia | 31 | 52 | 0.112 | 0.093 | 0.198 | −5.13 |

密度は Africa proconsularis で 0.060 と Chen の 0.081 に最も近づいたが、
**Q はむしろ下がり、ランダムとの乖離は拡大した**。
範囲を狭めても地域クラスタは現れない。

Numidia では `Bacax, Bacacis`（土着神）が n=2 のクラスタとして分離するが、
残り 50 神は 3 つの大クラスタに吸収される。

### 1-2. 同一碑文内の共起では有意な結果が出る（`build_cooccurrence_network.py`）

調査日: 2026-10-14

ここまでは全て「何が同じ**場所**に現れるか」を問うていた。
単位を **edcs_id（碑文）** に変え、「何が同じ**テキスト**に現れるか」を問うと、
**飽和が起きず、初めて積極的な所見が得られる。**

| | ノード | 密度 |
|---|---|---:|
| 恵与対象 × 場所 投影（§3・失敗） | 41型 × 363地点 | **0.945** |
| **恵与対象 × 恵与対象 共起（本節）** | 33 subtype | **0.309** |

`object_type` の最大値が `other`（7,590件中2,833件）であるため、
`mapping/apply_mapping.py` を通して再分類している（§7 の2階層カテゴリ）。
効果は小さくない:

| | ラベル付与された碑文 | 2種以上を持つ碑文 |
|---|---:|---:|
| 生の `object_type`（`--no-remap`） | 2,811 | 443 |
| 再分類・`*.unspecified` 込み（`--keep-unspecified`） | 3,935 | 565 |
| **再分類・`*.unspecified` 除外（既定）** | **2,860** | **495** |

**Louvain はここでも不発**（Q = 0.174、帰無 0.180 ± 0.040、z = −0.15）。
§4-2 の入れ子構造の問題は同じく効いている。
ただし `*.unspecified` を外した後はクラスタの中身が明瞭になり、
**建造物系／施与・娯楽系／街道系**の3群に分かれる（分割の有意性はないが、解釈はできる）。

**しかしペア単位の順列検定（型頻度・碑文あたり型数を固定、500回）では明確に出る。**
48ペア中 **27ペアが z ≥ +1.96、2ペアが z ≤ −1.96**:

| ペア | 観測 | 期待 | z |
|---|---:|---:|---:|
| bridge — road | 28 | 2.2 | **+18.14** |
| aqueduct — water | 9 | 0.5 | +11.23 |
| banquet — *gymnasium* | 35 | 9.1 | +9.74 |
| banquet — sportulae | 40 | 13.1 | **+9.00** |
| sportulae — *gymnasium* | 23 | 6.5 | +7.46 |
| **bath — utility（厨房・倉庫等）** | 8 | 1.2 | **+6.28** |
| money — theatrical | 29 | 11.1 | +6.01 |
| statue — temple | 50 | 30.9 | +4.26 |
| arch — portico | 10 | 4.4 | +2.87 |
| ⋯ | | | |
| statue — portico | 9 | 17.0 | **−2.40** |

**負の偏り（忌避）も検出される**ことが重要で、単なる頻度効果ではないことを示す。

#### 解釈上の注意 — 2点

**(a) `bridge — road` は定型表現。** z は最大だが、中身は街道修復の決まり文句:

> `pontes vetustate dilapsos` ＋ `iter longa incuria corruptum`
> （老朽で崩れた橋／長年の放置で損なわれた道）

確認した4件すべてがこの同一文型。「橋と道が共に寄進された」のではなく
**定型句を検出している**。euergetism の実態としては
`banquet — sportulae`（epulum + sportulae）や `money — theatrical` の方が解釈に値する。

**(b) `gymnasium` は本マッピングの誤分類。** `object_category_map.json` は
`structure.gymnasium`（建造物）としているが、共起パターンがこれを否定する。
北アフリカの碑文では *gymnasium* は通例**油の施与**を指す:

- 共起相手は `epulum` / `sportulae` / `visceratio` — いずれも施与
- 周辺テキストの動詞は **`dedit` 26件のみ**。
  `fecit` / `exstruxit` / `aedificavit`（建造動詞）は**ゼロ**
- 表層形も `gymnasium populo`（民衆へ）、`gymnasium biduo`（2日間）

**`distribution.oil` として `distribution` 側に移すべき。**
ただしこれは `hmk_ontology` 側ではなく `mapping/object_category_map.json` の
修正であり、OBJECT_TYPE_INVENTORY.md §7 の仕様変更にあたるため未実施。
上表の `gymnasium` 行は、修正すれば `distribution` 内の共起に統合される。

> この共起ネットワークは、**場所を軸にした2つの否定的所見に対する
> 最初の積極的所見**である。ただし母数は碑文の 10.3%（495/4,814）にとどまる。
> 大半の碑文は恵与対象を1つしか記録しない。

#### (c) `*.unspecified` の扱い — 2段階で対処した

当初は `*.unspecified` をノードとして残していたが、
**56ペア中11ペア（20%）がこれ絡みで、しかも解釈不能**だった。
`structure.unspecified — wall`（z = +4.44）は
「何らかの建造物が壁と一緒に言及された」としか言えない。

**第1段階 — マッピング表に規則を追加して救えるものを救った。**

`structure` 系の裾を全件（239種・339件）精査したところ、
**未分類の具体語が混ざっていた**:

| 表層形 | 本来の subtype |
|---|---|
| `fossam`（溝）, `moles`（堤） | `structure.utility` ほか |
| `praetorium`, `aulas`, `cryptam`, `zothecas` | `structure.domestic` |
| `septizonium`, `tholum`, `chalcidicum` | `structure.civic` |
| `epistylium`, `tetrastylum`, `gradibus`, `tessellatum` | `structure.element` |
| `castra`, `burgum`, `munimenta`, `τείχεα` | `structure.wall` |
| `pantheum`, `synagogam`, `κτίσμα τῶν μαρτυρίων` | `structure.temple` |

`object_category_map.json` に `*_extra` 規則7本を追加し、
**117件を回収**（`structure` の subtype 無し: 339 → 228）。

> **既存の分類は1件も変えていない。** 規則は「上から順に最初にマッチ」なので
> 既存50規則の**後ろ**に追加した。全7,590件で旧版と新版を突き合わせ、
> **回帰ゼロ**を確認済み。
>
> 途中で7件の回帰を検出し、原因を特定して除外した:
> `aeterna domus`（永遠の住まい＝墓の定型句）を `structure.domestic` に、
> `munitio` of a road（街道の「munire」）を `structure.wall` に
> 奪っていた。これらは旧版では手順4（`object_type` 由来）で
> 正しく分類されており、surface 規則は手順3なので先に効いてしまう。

**第2段階 — 残った真の汎用語はノードから外した（既定）。**

残り228件は `opus` / `aedificium` / `monumentum` / `votum` といった
**ラテン語の汎用語そのもの**で、語彙追加では解決しない。
OBJECT_TYPE_INVENTORY.md §4 が
「記念物であることは確実だが、墓か建物か像かが原文から決まらない」
と定義しているとおり、これは**情報の不在であって恵与の種類ではない**。
神格版が `Unknown deity` を除外しているのと同じ理由で、ノードから外した。

`--keep-unspecified` で従来の挙動に戻せる（出力タグは `_withunspec`）。

| | ペア数 | 有意（正/負） | 解釈 |
|---|---:|---:|---|
| `--keep-unspecified` | 52 | 30 / 1 | 11ペアが解釈不能 |
| **既定（除外）** | **48** | **27 / 2** | **全ペアが解釈可能** |

除外により**埋もれていた所見が表に出た**のが収穫で、
`bath — utility`（z = +6.28、浴場と厨房・倉庫）、
`arch — portico`（z = +2.87）は従来 `unspecified` に吸われて見えなかった。

#### 図（`plot_cooccurrence.py`）

| 図 | 内容 |
|---|---|
| **`fig5_pair_deviation.png`** | **主図。** ペアごとの観測値（塗り）と期待値（白抜き）をダンベルで結び、z 順に並べたもの。差そのものが読み取れる |
| `fig6_cooc_network.png` | 共起グラフ。エッジの色と太さは**生の共起数ではなく z**。施与系（banquet/sportulae/gymnasium/theatrical/money）が濃い塊として見える |
| `fig7_remap_gain.png` | 再分類で回収される碑文数（`--no-remap` との比較） |

`fig5` が論旨を担う。**両裾を残して**いるのが要点で、
上位 z だけを切り出すと「避け合うペア」が消え、
単なる頻度効果と区別できなくなる。

`fig6` では **Louvain クラスタによる着色を行っていない**。
Q が帰無モデルを下回る以上、分割で色を塗れば
統計が否定しているものを図が主張することになる。
代わりに色は z の符号のみを表す。

孤立対（`bridge–road`、`aqueduct–water`）は力学配置で本体を
隅に押しやるため描画から外し、図中に注記した（`plot_network.py` と同じ方針）。

配色は既存2スクリプトと同じ検証済みパレット。
`validate_palette.js` で再確認し全項目 PASS
（最悪隣接 CVD ΔE 9.1 protan、通常視 19.6）。
正負は**発散配色**として扱い、中間は灰（第3の色相を使わない）。

### 1-3. 役職の共起 — 同一碑文に併記された「別人同士」（`build_position_cooccurrence.py`）

調査日: 2026-10-14

恵与対象と同じ問いを役職に適用した。ただし**決定的な制約**がある。

#### 一人の cursus と、複数人の併記は別の問い

役職を2つ以上持つ碑文は 1,829 件あるが、内訳は:

| | 件数 | 性質 |
|---|---:|---|
| 一人の経歴（cursus） | 1,170 | **順序を持つ有向遷移**。「aedilis を経て duovir」 |
| **複数人の併記** | **659** | **無向の共起**。恵与対象と同じ構造 |

前者を無向共起として扱うと `order` を捨てることになり、
FEASIBILITY.md が「役職遷移ネットワーク」として別に確保している問いを
雑に潰すことになる。**本スクリプトは後者のみを対象とする。**

> **実装上の落とし穴**: 当初は「2人以上が登場する碑文」を選んだうえで
> 全員の役職を**合併**してペアを数えていた。これだと
> `consul — praetor` 27件中12件が**一人の cursus 内のペア**で、
> cursus を除外した意図が達成されていなかった。
> `cross_person_pairs()` で「2つの役職が別人に乗っている場合のみ数える」
> よう修正（27→18件、`aedilis — duovir` 11→8件）。
> 順列検定も同様に人の構成を保つ専用版に差し替えた
> （共起側だけ厳しくすると期待値が過大になり z が不当に下がるため）。

#### 皇帝称号の除外が必須

`consul` `imperator` `tribunicia potestas` `pater patriae` が**語彙の最上位**を占める。
皇帝への献辞が称号を全列挙するためで、これは「誰もが競った官職」ではない。
残すと全献辞が相互に結ばれ、§3 の飽和が再現する。

人物フィルタ（`is_imperial`）と称号フィルタ（`TITULATURE`）の二段で、
**14,548 person-record を除外**。効果は Louvain Q に明瞭に出る:

| | 碑文 | ノード | Q | 帰無 |
|---|---:|---:|---:|---:|
| `--include-imperial` | 1,224 | 110 | 0.149 | 0.170 |
| **既定（除外）** | **623** | **72** | **0.286** | 0.304 |

> `consul` は **`TITULATURE` に入れていない**。元老院議員が実際に就いた
> 官職であり、除くと本物の経歴段階が消える。皇帝は人物フィルタ側で落ちる。

#### 結果 — 32ペア中 18ペアが有意

Louvain は**帰無を超えない**（Q = 0.286、帰無 0.304 ± 0.046、z = −0.39）点は
他と同じだが、**クラスタの中身は本直後の4群に明瞭に分かれる**:

- **都市官職・祭司** — aedilis, duovir, flamen, flaminica, sufes, quinquennalis, patronus
- **元老院・属州** — consul, praetor, quaestor, legatus, proconsul, pontifex
- **軍** — centurio, miles, veteranus, optio, signifer, beneficiarius
- **キリスト教聖職** — episcopus, presbyter, diaconus

ペア単位の順列検定（人の構成を固定、500回）:

| ペア | 観測 | 期待 | z |
|---|---:|---:|---:|
| centurio — miles | 47 | 8.6 | **+14.80** |
| legatus — proconsul | 74 | 25.0 | **+12.25** |
| pontifex — praetor | 13 | 1.5 | +9.55 |
| consul — praetor | 18 | 3.3 | +8.60 |
| curator — proconsul | 42 | 15.0 | +7.67 |
| **flamen — flaminica** | 18 | 5.3 | **+6.19** |
| consularis — flamen | 18 | 5.9 | +5.76 |
| aedilis — duovir | 8 | 2.7 | +3.49 |

実データで確認した例:

- `flamen — flaminica`: `Nahania Victoria`(flaminica) ＋ `Q. Pacuvius Saturus`(augur, flamen)
  — **夫婦・親族で祭司職を分担する**構図
- `legatus — proconsul`: `Fl. Eucsinus`(proconsul) ＋ `Fl. Clodianus`(legatus)
  — 属州総督と配下legatus の**指揮系統**
- `centurio — miles`: `Valerius Tertius`(centurio) ＋ `T. Cassius Maior`(miles)
  — **軍の階層**

いずれも「同一碑文に誰と誰が並ぶか」であって、個人の昇進ではない。
`curator — proconsul`（+7.67）は都市の財務監督官が総督と並記される構図で、
都市と属州行政の接点として読める。

> **母数**: 623碑文。恵与対象（495）より大きい。
> 単一 cursus の 5,085 碑文を捨ててなおこの規模がある。

#### 図（`plot_cooccurrence.py --source positions`）

| 図 | 内容 |
|---|---|
| **`fig8_position_deviation.png`** | **主図。** ペアごとの観測 vs 期待。§1-2 の fig5 と同じ読み方 |
| `fig9_position_network.png` | 共起グラフ。元老院・属州系（legatus–consul–praetor–proconsul）と都市系（flamen–flaminica–aedilis–duovir）が左右に分かれ、**両者を結ぶ唯一の青エッジ `legatus — flamen`**（z = −2.86）が境界として読める |

作図コードは §1-2 と共有している（`WORDING` で文言のみ差し替え）。
同じ測定なので図法を変える理由がなく、二重管理も避けられる。
`fig9` の副題には**「別人同士のみ」を明記**した。
cursus の段階と読み違えると図の意味が逆になるため。

`fig7`（再分類の回収量）は恵与対象固有なので役職版では生成しない。

#### 属州別 — ここで初めて帰無モデルを上回る

`--province` で分割できる。母数は両属州とも十分:

| 範囲 | 碑文 | ノード | 密度 | Q | 帰無 | z |
|---|---:|---:|---:|---:|---:|---:|
| 北アフリカ全域 | 623 | 72 | 0.082 | 0.286 | 0.304 | −0.39 |
| Africa proconsularis | 344 | 41 | 0.138 | 0.292 | 0.287 | **+0.11** |
| **Numidia** | **301** | **56** | 0.082 | **0.360** | 0.353 | **+0.30** |

**本ディレクトリで初めて z が正に転じた。** §1-1 では属州に絞ると
神格ネットワークの Q はむしろ下がったが、役職では逆に上がる。
ただし z は +0.11 / +0.30 で**有意ではない**（帰無の幅に収まる）。
「ランダムを超えた」とまでは言えず、「下回らなくなった」が正確。

**語彙構成が属州の統治形態をそのまま反映している:**

| | 最頻 | 特徴 |
|---|---|---|
| Africa proconsularis | **`proconsul` 103** | 元老院属州。総督は proconsul |
| Numidia | **`legatus` 106** | 軍団属州。`consularis` 24 が入る |

図の形も別物になる:

- **`fig9_..._africa_proconsularis.png`** — `flamen`（都市祭司）と
  `proconsul`–`legatus`（属州）の**2極構造**。両者を**2本の青エッジ**
  （`flamen—legatus` z = −2.65、`curator—flamen` z = −2.10）が分離する
- **`fig9_..._numidia.png`** — `legatus` を中心とする**単一ハブ**。
  有意な負のペアはゼロ

属州固有の所見:

| 属州 | ペア | 観測 | 期待 | z |
|---|---|---:|---:|---:|
| Numidia | **consularis — flamen** | 14 | 3.6 | **+6.28** |
| Numidia | curator — praeses | 8 | 1.2 | +6.31 |
| Africa proc. | pontifex — praetor | 13 | 1.2 | +10.67 |
| Africa proc. | flamen — flaminica | 13 | 3.8 | +5.67 |

`consularis — flamen` は Numidia にのみ現れる。実データでも
`consularis p(rovinciae)` と確認でき、3世紀に同州が
**consularis 統治の属州として分離した**史実と符合する。

> **注意 — `curator — praeses`（Numidia, z = +6.31）は過大評価。**
> 8件中3件が**同一人物ペアの綴り異表記**
> （`Iulius Lambesius` / `Iul(ius) Lambesius` / `Iul(ius) Lambesio`
> ＋ `Valerius Florus`）で、別碑文として3回数えられている。
> 人物の名寄せは未実装で、n が小さいペアではこの影響が無視できない。
> `entity_resolution/` の成果を使えば改善できるはずだが未着手。

> **母数の下限について**: Numidia の 301 碑文で `--min-pair-obs 8` を課すと
> 検定対象は14ペアまで減る。これ以上の細分（都市単位など）は
> 検定が成立しなくなるため行っていない。

### 1-4. 氏族名の共起（`build_nomen_cooccurrence.py`）

調査日: 2026-10-14

#### 皇帝は「人物として」除外、氏族名は残す

ここが §1-0 の場所ベース分析と決定的に違う点。

`build_nomen_network.py` は `Iulius` / `Aurelius` / `Flavius` を
**氏族名ごと除外**している。これらは市民権付与に伴って授与されたもので、
「いつ市民権を得たか」を示すだけで地域性を示さないため、
場所ベースの分析では正当な除外である。

**共起では前提が変わる。** 問いは「どの家門が同じ碑文に並ぶか」であって、
212年に市民権を得た Aurelius も**実在する一つの家門**として
別の家門の隣に立っている。氏族名は残すべき。

除外すべきは**皇帝その人**だけ。全献辞が皇帝を名指すため、
残すと全碑文が相互に結ばれる。実際 `--include-imperial` では:

| ペア | 観測 | 期待 | z |
|---|---:|---:|---:|
| Nerva — Traianus | 71 | 3.0 | **+41.4** |
| Cocei(us/a) — Ulpi(us/a) | 52 | 2.2 | +36.6 |
| Hadrianus — Nerva | 23 | 0.5 | +33.7 |

§3 の飽和がそのまま再現する。

**判定は `social_status` で行う。** `emperor` / `empress` /
`imperial-family` に完全一致させる（部分一致は不可。`augustalis` は
市の祭司職、`imperial-slave` は皇帝家の奴隷で、いずれも皇帝ではない）。

> **`build_deity_network.is_imperial` は使っていない。** 神格判定用に
> 名前トークンで照合する関数で、人物レコードに当てると
> `Iulia Saturnina` `Iulia Rogata`（属州の一般女性）、
> `Marcus` `Lucius`（プラエノーメン）、`Saturnus Augustus`（神名）まで
> 皇帝扱いする。status が皇帝でない 4,409 person-record を誤検出していた。
> 修正後に残った13件は `Helvia Commoda` `Maria Commoda` のように
> Commodus/Hadrianus をコグノーメンに持つ**私人**で、皇帝本人の漏れはない。

この修正で母数は **1,453 → 2,680 碑文**に増えた。

#### 氏族名の正規化

`nomen` フィールド自体がほぼ正規形（4,108形のうち編集記号・空白を含むのは
978件＝2.4%）。`canonical()` で以下を行う:

1. 編集記号の除去（`[Iul]ius` → `Iulius`。`build_nomen_network.py` と同じ）
2. 重子音の正規化（`Aurellius` → `Aurelius`）
3. **男女形の統合**（`Sittius` / `Sittia` → `Sitti(us/a)`）

> `person_name_normalized` は**氏族名の正規化ではない**。
> Wikidata 連携による著名人物の同定で
> （`"Imp(erator) Caes(ar) M(arcus) Aurelius Antoninus..."` → `"Caracalla"` / `Q1446`）、
> 85,118 person-record 中 8,665件（10%）しか埋まらず、ほぼ皇帝に限られる。
> 氏族名の名寄せには使えない。

男女形の統合は **`-ius`/`-ia` の交替のみ**に限定した。

> 当初は語尾 `-us`/`-a` も削る規則を書いたが、実データで検証すると
> `Sabinus`→`Sabinia`、`Titus`→`Titia`、`Verus`→`Verria` と
> **コグノーメン・プラエノーメンまで氏族に畳み込んでいた**。
> 保守的な規則に差し替え、744グループで誤統合がないことを確認した。
> `--no-merge-gender` では上位が `domitia — domitius`(+10.0)、
> `clodia — clodius`(+9.3) で埋まり、形態論のアーティファクトだと分かる。

#### family 関係の除外

家族墓碑の同語反復を避けるため、`person_relationships` で
`family` と宣言されたペアを落とす。

> 異なる氏族名のペアに限ると family は 3,404 / 17,673 = **20%** にすぎず、
> 70%（12,035件）は明示的な関係を持たない共同奉献者等である。母数は十分残る。
> `--keep-family` では §1-3 で見た flamen/flaminica 夫婦
> （`Nahani(us/a) — Pacuvi(us/a)`, z = +22.9）が最上位に来る。

#### 結果

| 範囲 | 碑文 | ノード | Q | 帰無 | 検定ペア | 有意(+) |
|---|---:|---:|---:|---:|---:|---:|
| 北アフリカ全域 | 2,680 | 195 | 0.186 | 0.226 | 92 | 8 |
| Africa proconsularis | 1,227 | — | 0.421 | 0.454 | 14 | 5 |
| Numidia | 1,526 | — | 0.172 | 0.201 | 56 | 7 |

Louvain はいずれも帰無を下回る。所見はペア単位にある。

**属州差が出る:**

| 属州 | ペア | 観測 | 期待 | z |
|---|---|---:|---:|---:|
| Africa proc. | Iuli(us/a) — Numisi(us/a) | 5 | 1.6 | +2.93 |
| Africa proc. | Iuli(us/a) — Pomponi(us/a) | 8 | 3.1 | +2.84 |
| Africa proc. | Fabi(us/a) — Iuli(us/a) | 8 | 3.6 | +2.63 |
| **Numidia** | **Corneli(us/a) — Gemini(us/a)** | 6 | 1.5 | **+3.94** |
| **Numidia** | **Aemili(us/a) — Gemini(us/a)** | 6 | 2.3 | **+2.52** |
| Numidia | Aureli(us/a) — Gemini(us/a) | 6 | 2.8 | +2.04 |

Africa proconsularis では `Iulius` が3ペアの軸になり、
Numidia では `Geminius` が3ペアの軸になる。
**氏族名を残したことで初めて見えた構図**で、除外していた前版では
`Iulius` 絡みのペアは存在しなかった。

Numidia の `Geminius` 系は**6件すべて別人**で、
termini のような同一人物反復ではない（目視確認済み）。

#### 残る限界 — 同一人物の反復

全域の上位2ペアは依然としてアーティファクト:

| ペア | 碑文数 | 実態 |
|---|---:|---|
| Fontei — Stertini (z=+35.6) | 5 | 全件が `Fonteius Frontinianus` ＋ `Stertinius Rufinus` |
| Rutili — Senti (z=+20.4) | 12 | 全件が `Rutilius Gallicus` ＋ `Sentius Caecilianus` |

いずれも**境界標（termini）の連作**で、同一の測量委員の名が各石に刻まれている。
`--dedupe-people` で同一人物集合の碑文を畳めるが、
人物同定は一般には困難なため既定では適用していない
（コーパス全体の重複は 4.1% にとどまり、大きな傾向には影響しない）。

#### 図

| 図 | 内容 |
|---|---|
| `fig10_nomen_deviation.png` | ペアごとの観測 vs 期待 |
| `fig11_nomen_network.png` | 共起グラフ |
| `fig10/fig11_*_numidia.png` 他 | 属州別 |

### 1-5. 経歴内の隣接役職 — 年代問題を構造的に回避できる唯一の方向（`build_cursus_network.py`）

調査日: 2026-10-14

#### なぜこれだけが年代の壁を越えるか

§1-2〜§1-4 は**すべて無向共起**で、外部から年代を与えない限り
時間構造がゼロだった。コーパスの年代付与率は **18.2%**（51,941件中9,466件）で、
しかも**無作為標本ではない**（年代付き碑文の経歴記載率32%に対し、
年代なしは11%。公的碑文に偏る）。年代で切ると碑文の性格でも切ることになる。

**cursus は一人の人生の内部に相対的な時間順序を持つ。**
`order` フィールドが「次にどの職に就いたか」を記録しており、
**絶対年代を必要としない**。1,603件の経歴が使え、
うち絶対年代があるのは604件（36%）にすぎないが、
残り999件も順序情報は完全に使える。

#### 隣接のみを結ぶ。方向は取らない

ラテン碑文の cursus は**昇順・降順の両方の書式**があり、
コーパスはどちらの慣行かを記録していない。
`order` を昇進方向と読むと所見を捏造することになる。

**隣接（adjacency）だけを取れば方向判定が不要になる。**
「隣り合って言及された」という事実のみを使う。

隣接は単なる共起と明確に異なる:

| | ペア数 |
|---|---:|
| 隣接したことのあるペア | **802** |
| 同一経歴に共起するペア | 1,428 |

`adj/cooc`（両職を持つ経歴のうち連続していた割合）で区別できる:

| ペア | adj/cooc | 解釈 |
|---|---:|---|
| quaestor — tribunus | **0.91** | ほぼ必ず連続＝段階 |
| aedilis — quaestor | 0.85 | 段階 |
| legatus — quaestor | **0.16** | 共起するが離れている |
| flamen — quaestor | 0.25 | 離れている |

#### 結果 — 役職レベル

82ペア中 **59ペアが z ≥ +1.96、5ペアが z ≤ −1.96**（Q=0.360、帰無0.409）。

| ペア | 観測 | 期待 | z | adj/cooc |
|---|---:|---:|---:|---:|
| consul — legatus | 136 | 25.7 | **+23.1** | 0.73 |
| aedilis — quaestor | 84 | 15.0 | **+20.4** | 0.85 |
| **aedilis — duovir** | 91 | 18.9 | **+19.2** | 0.75 |
| legatus — praetor | 59 | 9.7 | +17.4 | 0.69 |
| quaestor — tribunus | 61 | 9.1 | +17.4 | 0.91 |
| ⋯ | | | | |
| flamen — quaestor | 12 | 26.2 | **−3.11** | 0.25 |
| legatus — praefectus | 16 | 28.8 | −2.59 | 0.55 |

#### 結果 — セクターレベル（`--level type`）が最も明快

**ご指摘の「軍職から市政への移行」はここで見える。**
18ペア中 8正/6負。**負の値が出ることが決定的に重要**で、
単なる頻度効果ではないことを示す。

| ペア | 観測 | 期待 | z |
|---|---:|---:|---:|
| **local-admin — local-priesthood** | 426 | 142.8 | **+30.9** |
| **imperial-admin — provincial-admin** | 326 | 132.5 | **+22.1** |
| imperial-priesthood — provincial-admin | 99 | 39.9 | +11.2 |
| imperial-admin — military | 112 | 69.7 | +6.2 |
| local-priesthood — occupation | 11 | 5.3 | +2.9 |
| ⋯ | | | |
| imperial-priesthood — military | 8 | 20.8 | **−3.3** |
| **imperial-admin — local-priesthood** | 59 | 136.1 | **−8.8** |
| **local-admin — provincial-admin** | 49 | 139.6 | **−10.3** |
| **imperial-admin — local-admin** | 52 | 158.4 | **−11.2** |

**読み取れる構造は「二つの経路の分離」である:**

- **都市の経路** — `local-admin ↔ local-priesthood`(+30.9) が最強。
  市の官職と祭司職は同一人物の中で隣接する
- **帝国の経路** — `imperial-admin ↔ provincial-admin`(+22.1)、
  軍職とも接続(+6.2)
- **両者は接続しない** — `imperial-admin ↔ local-admin` が **z = −11.2**、
  `local-admin ↔ provincial-admin` が **−10.3**

つまり**地方エリートの経歴と帝国官僚の経歴は、同一人物の中でほとんど隣接しない**。
地方名士は市政と祭司職を往復し、帝国官僚は属州・軍を往復する。
両者の間に構造的な断絶がある。

> 軍職と市政の直接的な接続（`local-admin ↔ military` z = −0.75）は
> **有意ではない**。軍を経て市政に入る経路は、
> 帝国行政を経由する経路（軍 → imperial-admin → …）ほど一般的ではない。

#### 属州別 — 共通構造と、2つの差

| 範囲 | 経歴数 | 検定ペア | 有意(+/−) |
|---|---:|---:|---:|
| 北アフリカ全域 | 1,603 | 18 | 8 / 6 |
| Africa proconsularis | 604 | 16 | 7 / 6 |
| Numidia | 498 | 12 | 5 / 3 |

§1-3 の属州別（344/301碑文）より母数が大きい。

> **比較は z ではなく観測/期待比（o/e）で行う。**
> 母数が違えば同じ効果でも z は変わるため、z の大小を属州間で比べてはいけない。

**共通する骨格 — 二経路の分離は両属州で成立する:**

| ペア | Afr o/e | Num o/e |
|---|---:|---:|
| local-adm — local-priesthood | 2.85 | **3.19** |
| imperial-adm — provincial-adm | 2.36 | **2.47** |
| imperial-adm — local-adm | **0.23** | 0.45 |
| local-adm — provincial-adm | 0.38 | **0.34** |

§1-5 本体の所見は属州固有ではなく、**北アフリカに共通する構造**である。

**差その1 — 地方祭司と軍の関係が逆転する:**

| ペア | Afr o/e | Num o/e |
|---|---:|---:|
| **local-priesthood — military** | **0.59**（z=−3.0、有意に忌避） | **1.16**（z=+1.0、有意でない） |
| imperial-priesthood — local-adm | 0.47（z=−3.9） | 1.12（z=+0.5） |

Africa proconsularis では**市の祭司職と軍歴が有意に避け合う**が、
Numidia では避け合わない。

セクター構成比もこれと整合する:

| | 地方祭司 | 軍 | 属州行政 |
|---|---:|---:|---:|
| Africa proconsularis | **41.5%** | 20.7% | 26.9% |
| Numidia | 29.6% | **26.7%** | **38.2%** |

Numidia は軍団属州（legio III Augusta 駐屯）であり、
軍歴を持つ者が市政・祭司職に入る余地が大きい。
Africa proconsularis は元老院属州で軍団を持たず、
市の祭司職は非軍事的な名望家の領分だった、と読める。

> **ただし断定はできない。** 軍歴と市政を兼ねる経歴は
> **両属州とも59件で同数**であり、違うのはその内訳である:
>
> | | 将校級 | 下士官・兵卒 |
> |---|---:|---:|
> | Africa proconsularis | 40 | 10 |
> | Numidia | 29 | 18 |
>
> Numidia には `veteranus → flamen`、`miles → ...` のように
> **退役兵・一般兵が市の祭司職に就く**例が出るが、
> Africa は `praefectus` / `centurio` / `tribunus` と将校級に偏る。
> **Fisher 正確検定で p = 0.072**（OR 2.48）。
> 示唆的ではあるが**有意水準には達しない**。
> 「退役兵植民市 Numidia」という一般的な理解と整合する方向ではあるが、
> このデータだけでは主張できない。

**差その2 — Africa の方が分断が細かい。**
有意な負のペアは Africa 6本に対し Numidia 3本。
`fig13` を並べると、Africa は `local-priesthood` が
`military` `imperial-adm` `provincial-adm` の三方向と
同時に忌避関係を持つのに対し、Numidia では `imperial-adm` との
一方向に集約される。

#### 図

3つの粒度で出力できる（`--level`）:

| `--level` | ノード数 | 用途 |
|---|---:|---|
| `type` | 8 | セクター（既定の分析単位） |
| **`abstract`** | **34** | **個別役職。表記ゆれ・等価職を統合**（推奨） |
| `position` | 43 | 生の `position_abstract` |

`abstract` は 316 種の役職を 275 種に畳み、
**上位20職のカバー率を 73% → 81%** に上げる。統合したのは:

| グループ | 統合対象 |
|---|---|
| `duovir` | duumvir, iivir, duumviralicius, iiviralicius |
| `aedilis` | aedilicius |
| `board-magistrate` | triumvir, decemvir, quattuorvir, sevir, septemvir … |
| `minor-priest` | sodalis, fetialis, quindecimvir, septemvir epulonum … |
| `senatorial-rank` | clarissimus, consularis, sexfascalis, patricius, adlectus … |
| `soldier` | miles, veteranus, eques, duplicarius … |
| `nco` | centurio, optio, signifer, beneficiarius, cornicularius … |

> **統合しなかったもの。** `flamen` / `pontifex` / `sacerdos` / `augur` は
> 分けたまま残した。4つの実質的な祭司職であり、畳むと §1-5 の根拠である
> 地方祭司の構造が消える。`praefectus` / `tribunus` も軍・民の両義で使われるが、
> **コーパスはどちらの意味かを記録していない**ので、推測で分けるより
> そのまま残す方が安全。

| 図 | 内容 |
|---|---|
| **`fig12_cursus_deviation_type.png`** | **最も明快。** セクター間の隣接。正負が明瞭に分かれる |
| **`fig12_cursus_deviation_abstract.png`** | **個別役職レベル。** 82ペア中57正/6負 |
| **`fig13_cursus_network_abstract.png`** | **個別役職の隣接グラフ。3領域が分離して見える** |
| `fig13_cursus_network_type_*.png` | 属州別（セクター） |

`fig13_cursus_network_abstract.png` では**3つの領域が分かれて読める**:

- **元老院系** — proconsul / consul / legatus / praetor / quaestor / tribunus
- **都市系** — duovir / aedilis / flamen / quinquennalis / pontifex
- **軍系** — soldier / nco / decurio / praepositus

> ノード数は `--max-nodes` で制限できる（既定は無制限）。
> 役職レベルは約100ノードあり、力学配置では毛玉になるため、
> **|z| の合計が大きい順に24ノード**へ絞って描画している。
> 頻度ではなく偏りの強さで残すので、稀でも特徴的なペアは落ちない。

#### 個別役職レベルでも属州差が再現する

| ペア | Afr o/e | Num o/e |
|---|---:|---:|
| **flamen — soldier** | **1.89** | **3.40** |
| flamen — sacerdos | 2.20 | 3.32 |
| legatus — praetor | **10.54** | 4.00 |
| consul — legatus | 1.95 | **5.39** |
| aedilis — duovir | 4.37 | 5.00 |

`flamen — soldier` が Numidia で 1.8 倍強いのは、
セクターレベルで見た `local-priesthood — military` の差
（Afr 0.59 / Num 1.16）と**同じ現象を役職レベルで捉えたもの**。
軍団属州 Numidia では兵士・退役兵が市の祭司職に就く。

#### 留保

- **同一人物の反復**は依然として残る（`Octavius Festus` の
  `decurio → praepositus` が4碑文に重複）。セクターレベルでは
  69件に希釈されるため結論は動かないが、役職レベルの小さい n では影響する
- `order` は LLM 抽出であり、碑文の記載順をそのまま採っている。
  隣接のみを使うことで方向の誤りは回避したが、
  **記載順が経歴順と異なる碑文**（親族の経歴が混在する等）の影響は残る
- `--all-pairs` で隣接制約を外すと181ペア中118が有意になるが、
  これは「同じ経歴に現れた」だけの関係を含むため、**隣接版の方が厳密**

---

---

## 2. Chen の手法（複製データで確認済み）

論文本体は MDPI が自動取得を拒否するため、Zenodo の複製データ
([10004109](https://zenodo.org/records/10004109)) から手法を特定した。
`data/REFERENCE_chen_readme.md` に原典の README を保存してある。

実データ（エッジリスト・ノードリスト）から確認した仕様:

| 項目 | 内容 |
|---|---|
| 二部グラフ | **場所 × 信仰**（place × cult） |
| エッジ | **無向・重みなし**（`type=undirected, weight=1`） |
| 規模 | 56 places × 83 cults、378 ties（密度 0.081） |
| 足切り | **1か所にしか現れない信仰を除外**（56x83 行列は cult の次数 ≥ 2） |
| 一部グラフ化 | 共有相手数を重みとする投影（論文 Fig.7） |
| クラスタ検出 | **Louvain**（NodeList に `LouvainCluster` 列、I〜VII の7クラスタ） |
| 補助分析 | Newman Community Detection、コア/周縁ブロック |
| 可視化 | Gephi 0.10、Force Atlas 2（Lin-Log） |

「信仰そのものは互いに関係を持たないが、同じ場所に共在することで結ばれる」
という変換が核心。

---

## 3. 本データへの対応

`divinity_type` は 500 種あり、Chen の「信仰」に正しく対応する。
二部グラフの密度も Chen と同水準になった。

| | 種類数 | 場所数 | 二部密度 | 投影密度 |
|---|---:|---:|---:|---:|
| Chen | 83 cults | 56 places | 0.081 | — |
| **本データ（神のみ）** | **125 deities** | **127 places** | **0.047** | 0.520 |

> **経緯**: 当初は恵与対象（`object_type` / `subtype` 41種）で試作したが、
> 場所 363 に対し型が 41 しかなく、投影が**密度 0.945 のほぼ完全グラフ**に
> なって Louvain が機能しなかった。「彫像」「神殿」はどこにでもあり、
> 地点を弁別しない。Chen の「信仰」が**固有名**であるのに対し、
> `object_type` は**カテゴリ**だったことが原因。
> この試作（`build_network.py` と関連出力）は役に立たないため削除した。
> 神格版が Chen の構造に対応する正しい実装。

---

## 4. なぜ地域クラスタが出ないか

クラスタの中身を見ると、意味のあるまとまり自体は出ている:

- `Petrus, Paulus`（キリスト教）
- `Bacacis, Bacax`（北アフリカ土着神）

しかしこれらは **n=2 の孤立した小クラスタ**で、大半の神は
`Saturnus, Iuppiter, Mercurius, Victoria, Genius, Hercules...` という
63 ノードの巨大クラスタに吸収される。

主要な神々が**全属州に遍在する**ためで、サトゥルヌスはヌミディアにも
アフリカ・プロコンスラリスにも現れる。Chen の蔣子文信仰のような
「特定地域にしかない信仰」が、ローマ期北アフリカでは主流でない可能性がある。

> 歴史的には「ローマ化した北アフリカの宗教が、地域差より帝国共通の
> パンテオンに統合されていた」とも読める。ただし現時点では、
> 出土の偏り・LLM 抽出の偏りと実態を切り分けられていない。
> **この解釈を主張するには §6 の条件を満たす必要がある。**

## 4-2. なぜ Louvain では捉えられないのか

氏族名の結果（§1-0）が診断を与えてくれる。**地域性は実在するのに Q は低い。**
したがって問題はデータではなく、**手法とデータ構造の不整合**にある。

Chen のデータは**ほぼ対称**（83 cults × 56 places、比 1.48）で、
信仰も場所も同程度に「選択的」だった。本データは違う:

- Carthago は 448 種の氏族名を持つ（≒全部入り）
- 小村は 2〜3 種しか持たない
- 小村の持つ名は、ほぼ必ず大都市の部分集合

この**入れ子構造（nestedness）**では、どの分割を取っても
大都市が全クラスタに接続してしまう。モジュラリティは
「クラスタ内が密／クラスタ間が疎」を測る指標なので、
入れ子に対しては原理的に低い値しか返さない。
帰無モデルを**下回る**のはそのためで、ランダム化すると
入れ子が壊れてモジュール性が偶然生じる。

Chen の長江下流域では県同士が比較的対等だったため、この問題が起きなかった。
**手法の限界ではなく、適用対象の構造が違う。**

### 4-3. 上位都市を除けば機能するか → **しない**（検証済み）

入れ子構造が原因なら、その頂点（Carthago、Lambaesis 等）を除けば
Louvain が機能するはず——という仮説を検証した。

氏族名の種類数が多い順に地点を除去していくと、**Q は単調に上昇する**:

| 除去数 | 残り地点 | 投影密度 | Q |
|---:|---:|---:|---:|
| 0 | 643 | 0.253 | 0.073 |
| 20 | 599 | 0.227 | 0.103 |
| 80 | 524 | 0.143 | 0.230 |
| 160 | 426 | 0.087 | 0.393 |
| **200** | **379** | **0.073** | **0.457** |
| 320 | 247 | 0.056 | 0.565 |

200地点を除くと Q = 0.457 で、「構造あり」の目安 0.30 を大きく超える。
**数値だけ見れば成功に見える。**

#### しかし帰無モデルを通すと全滅する

| 除去数 | Q | 帰無モデル | z | 判定 |
|---:|---:|---:|---:|---|
| 0 | 0.073 | 0.116 | −15.07 | 下回る |
| 80 | 0.231 | 0.270 | −6.53 | 下回る |
| 160 | 0.394 | 0.426 | −2.23 | 下回る |
| **200** | **0.456** | **0.477** | **−2.17** | **下回る** |
| 320 | 0.549 | 0.606 | −3.36 | 下回る |

**Q の上昇はグラフが疎になったことの機械的な帰結**であって、
構造が現れたのではない。ランダム化しても同じだけ（むしろそれ以上）
Q が上がるため、観測値は常に帰無分布を下回ったままになる。

#### クラスタの中身を見ても地理的でない

drop=200（Q=0.457）のクラスタを地理座標で検算した:

| クラスタ | n | 重心 | 平均広がり |
|---|---:|---|---:|
| 1 | 58 | (35.7, 8.5) | 188km |
| 2 | 47 | (35.6, 8.4) | 203km |
| 3 | 46 | (35.4, 9.0) | 192km |
| 4 | 45 | (35.7, 7.0) | 283km |

**重心がほぼ同一で、広がりが 140〜283km。**
地理的に分かれているのではなく、同じ空間に相互貫入している。
Chen の7クラスタが地図上で別々の地域を占めたのとは対照的。

→ **上位都市の除去では解決しない。** 入れ子性は一部の大都市に
由来するのではなく、都市規模の連続的な階層そのものに由来する。
Lambaesis 648 種から末端の 2 種まで切れ目なく続いており、
「どこかで切れば対等なネットワークになる」境界が存在しない。

---

## 5. 成果物と実行方法

```
chen_method/
├── README.md                     このファイル
├── build_deity_network.py        神格版（Chen の手順に準拠）
├── build_nomen_network.py        氏族名版
├── build_cooccurrence_network.py 同一碑文内の恵与対象共起（§1-2・唯一の積極的所見）
├── plot_cooccurrence.py          共起の図（fig5-7）
├── build_position_cooccurrence.py 役職の共起（§1-3・別人同士のみ）
├── build_nomen_cooccurrence.py   氏族名の共起（§1-4・非血縁のみ）
├── build_cursus_network.py       経歴内の隣接役職（§1-5・年代不要）
│                                 図は plot_cooccurrence.py --source positions
├── concentration.py              集中度分析（Louvain の代替・推奨）
├── plot_concentration.py         地図と散布図
├── plot_network.py               図の生成
├── data/
│   └── REFERENCE_chen_readme.md  Chen の複製データ README（CC BY 4.0）
└── output/
    ├── report_deity.txt                      北アフリカ全域・神のみ（既定）
    ├── report_deity_with_imperial.txt        全域・皇帝込み
    ├── report_deity_africa_proconsularis.txt 属州別
    ├── report_deity_numidia.txt              属州別
    ├── report_nomen.txt                      氏族名版
    ├── report_cooc*.txt / cooc*.json         同一碑文内の共起（§1-2）
    ├── report_pos*.txt / pos*.json           役職の共起（§1-3）
    ├── fig8_position_deviation.png           役職ペアの観測 vs 期待（主図）
    ├── fig9_position_network.png             役職の共起グラフ
    ├── fig8/fig9_*_africa_proconsularis.png  属州別（§1-3 末尾）
    ├── fig8/fig9_*_numidia.png               属州別
    ├── report_nomen_cooc*.txt / *.json       氏族名の共起（§1-4）
    ├── fig10_nomen_deviation.png             氏族名ペアの観測 vs 期待
    ├── fig11_nomen_network.png               氏族名の共起グラフ
    ├── report_cursus*.txt / cursus*.json     経歴内の隣接（§1-5）
    ├── fig12_cursus_deviation_type.png       セクター間の隣接（最も明快）
    ├── fig12/fig13_*_abstract.png            個別役職（表記ゆれ統合済み）
    ├── fig13_cursus_network*.png             隣接グラフ
    │                                         （*_withunspec = unspecified 込み）
    ├── fig5_pair_deviation.png               ペアごとの観測 vs 期待（主図）
    ├── fig6_cooc_network.png                 共起グラフ（エッジ = z）
    ├── fig7_remap_gain.png                   再分類による回収量
    ├── concentration.txt / .json             集中度分析の結果
    ├── map1_overview.png                     集中型氏族名の重心分布
    ├── map2_examples.png                     個別例の小多重図
    ├── fig4_dispersion_entropy.png           分散距離 × エントロピー
    ├── fig1_two_mode_*.png                   二部グラフ（Chen Fig.1 に対応）
    ├── fig2_deity_*.png                      deity–deity 投影、Louvain 着色
    ├── fig3_null_*.png                       帰無モデルとの比較
    └── *.graphml                             Gephi 用（再生成物のため git 管理外。
                                              build_*_network.py の再実行で数秒で復元）
```

### 図

| 図 | 内容 |
|---|---|
| `fig1_two_mode_*` | 場所（青・四角）× 神格（橙・丸）の二部グラフ。Chen の Fig.1 に対応 |
| `fig2_deity_*` | deity–deity 投影。Louvain クラスタで着色。**2つの大クラスタが分離せず相互貫入している**ことが読み取れる |
| `fig3_null_*` | **論旨の中心。** 観測 Q が次数保存ランダムグラフの分布から外れて**低い**側にあることを示す |

否定的な所見なので、`fig3` が最も重要になる。「クラスタが出ない」だけでは
手法の失敗と区別できないが、帰無分布との位置関係を見せれば
「偶然より均質」という積極的な所見として読める。

`fig2` では巨大連結成分のみを描画している。孤立した対（`Bacax–Bacacis` 等）は
力学配置で本体を隅に押しやるため、図から外して件数のみ注記した。

色は検証済みのカテゴリカル配色（blue/orange/aqua/yellow/magenta）。
`validate_palette.js` で全項目 PASS（最悪隣接 CVD ΔE 9.1 protan、
通常視 19.6）。低コントラスト警告には直接ラベルで対応している。

```bash
venv/bin/python network_analysis/chen_method/plot_network.py
venv/bin/python network_analysis/chen_method/plot_network.py --province Numidia
```

```bash
BD=network_analysis/chen_method/build_deity_network.py
venv/bin/python $BD                                        # 北アフリカ全域・神のみ
venv/bin/python $BD --include-imperial                     # 皇帝込み
venv/bin/python $BD --province "Africa proconsularis"      # 属州別
venv/bin/python $BD --province "Numidia"
venv/bin/python $BD --min-deity-places 3                   # 足切りを強める
venv/bin/python $BD --null-trials 0                        # 帰無モデル省略（高速）

BN=network_analysis/chen_method/build_nomen_network.py
venv/bin/python $BN                                        # 氏族名版
venv/bin/python $BN --include-imperial                     # 皇帝系氏族名を含める
venv/bin/python $BN --province "Numidia"

# 同一碑文内の共起（§1-2・場所軸で出なかった所見が出る）
BC=network_analysis/chen_method/build_cooccurrence_network.py
venv/bin/python $BC                      # 再分類あり・カテゴリ粒度
venv/bin/python $BC --level subtype      # subtype 粒度（推奨。所見が最も明瞭）
venv/bin/python $BC --no-remap           # 生の object_type（再分類の効果を見る）
venv/bin/python $BC --level subtype --province Numidia
venv/bin/python $BC --level subtype --keep-unspecified   # *.unspecified を残す
venv/bin/python network_analysis/chen_method/plot_cooccurrence.py   # 図

# 役職の共起（§1-3）
BP=network_analysis/chen_method/build_position_cooccurrence.py
venv/bin/python $BP                      # 別人同士・皇帝除外（既定）
venv/bin/python $BP --level type         # position_type の粗い粒度
venv/bin/python $BP --include-imperial   # 皇帝称号を含める（飽和の確認用）
venv/bin/python $BP --any-person         # 単一 cursus も含める（非推奨）
venv/bin/python network_analysis/chen_method/plot_cooccurrence.py --source positions  # 図

# 属州別（§1-3 末尾）
for P in "Africa proconsularis" "Numidia"; do
  venv/bin/python $BP --province "$P"
  venv/bin/python network_analysis/chen_method/plot_cooccurrence.py \
      --source positions --province "$P"
done

# 氏族名の共起（§1-4）
BN2=network_analysis/chen_method/build_nomen_cooccurrence.py
venv/bin/python $BN2                      # 非血縁・男女形統合・皇帝除外（既定）
venv/bin/python $BN2 --dedupe-people      # 同一人物の反復を畳む（推奨）
venv/bin/python $BN2 --keep-family        # family を残す（同語反復の確認用）
venv/bin/python $BN2 --no-merge-gender    # Sittius/Sittia を分ける
venv/bin/python $BN2 --include-imperial   # 皇帝を含める（飽和の確認用）
venv/bin/python $BN2 --province Numidia
venv/bin/python network_analysis/chen_method/plot_cooccurrence.py --source nomina

# 経歴内の隣接役職（§1-5・最有望）
BC2=network_analysis/chen_method/build_cursus_network.py
venv/bin/python $BC2                      # 役職レベル
venv/bin/python $BC2 --level type         # セクターレベル
venv/bin/python $BC2 --level abstract     # 個別役職・統合版（推奨）
venv/bin/python $BC2 --all-pairs          # 隣接制約を外す（比較用）
venv/bin/python $BC2 --level type --province Numidia
PLT=network_analysis/chen_method/plot_cooccurrence.py
venv/bin/python $PLT --source cursus --level type
venv/bin/python $PLT --source cursus --level abstract --max-nodes 24

# 集中度分析（推奨）
CC=network_analysis/chen_method/concentration.py
venv/bin/python $CC                      # 全域、n>=30
venv/bin/python $CC --min-count 20       # 閾値を下げる
venv/bin/python $CC --bandwidth 50       # Moran の近傍距離を変える
venv/bin/python $CC --province "Numidia"
venv/bin/python network_analysis/chen_method/plot_concentration.py   # 地図
```

`networkx` が必要（`venv` に 3.6.1。Louvain は同梱）。
GraphML は Gephi で開ける（Chen と同じく Force Atlas 2 / Lin-Log を想定）。

### 皇帝の扱い

既定で**神格化された皇帝を除外**する（`--include-imperial` で包含）。
`Nerva` 511 / `Traianus` 463 / `Hadrianus` 405 が上位3件を占め、
皇帝崇拝は帝国全土に一様に広がるため、含めると全地点が相互に接続されて
§3 の恵与対象版と同じ飽和が起きる。FEASIBILITY.md が役職遷移ネットワークに
皇帝除外を必須としているのと同じ理由。

除外は語幹マッチ（`IMPERIAL_TOKENS`）で、51 名・2,355 件が該当。
`Saturnus` `Caelestis` `Mercurius` などの神は保持される（目視検証済み）。

`Unknown deity` 等のプレースホルダも除外している。これを信仰として扱うと、
神名が判読できない全地点が相互に結ばれてしまうため。

---

## 6. 次の一手

~~1. 属州内に絞る~~ — **実施済み。改善しなかった（§1-1）。**

0. **【最優先】エントロピー／集中度による分析に切り替える** — §1-0 が示すとおり、
   地域性は Louvain では見えないが**氏族名ごとの分布の偏り**としては明瞭に出る。
   Sittius → キルタ連合、Gabinius → Dougga のように、歴史的に検証可能な
   結果が既に得られている。コミュニティ検出に固執せず、
   「どの氏族名がどこに集中するか」を指標化する方が生産的。

   具体的には: 正規化エントロピー H、局所 Moran's I（地理座標を使う）、
   あるいは地点ペアの Jaccard 類似度に基づく階層クラスタリング。

2. **「地域クラスタは出ない」を結果として報告する** — 現時点で最も妥当な選択。
   全域・属州別・皇帝の有無を通じて**6構成すべてで Q < 0.15**、
   うち5構成が帰無モデルを下回るという所見は一貫している。
   パラメータ選択の産物ではない。

   「ローマ期北アフリカの宗教landscape は地域分節的でない」という
   主張の根拠になりうるが、**出土バイアスの統制が前提**。
   現状では以下を切り分けられていない:
   - 実際に神格分布が均質だった
   - 碑文の遺存・発掘が大都市に偏っている
   - LLM 抽出が有名な神を拾いやすい

3. **年代分割** — 2世紀と4世紀では神格分布が大きく異なるはず
   （特にキリスト教の登場）。数値年代が 17% しかない制約
   （FEASIBILITY.md §5）の明示が必要。残る未検証の変数はこれ。

4. **入れ子性（nestedness）の定量化** — 帰無モデルを下回るという所見は、
   モジュール構造ではなく**入れ子構造**を示唆する
   （大都市が小都市の神格を包含する）。NODF 等の指標で測れば、
   「地域差がない」より踏み込んだ積極的な主張になる。

---

## 7. 既存調査との関係

`FEASIBILITY.md`（10-05）は恵与の Object–Object 投影を**人物を介した共起**で
構成していた（延べ 1,552 件）。人物同定が 6% しかないことが
最大の制約と記されている。

Chen 方式は媒介を**場所**にするため人物同定が不要で、
制約を迂回できる点は当初の見込みどおりだった。
ただし本試作が示すとおり、**データ量が増えてもクラスタは出ない**。
ボトルネックは人物同定ではなく、神格分布そのものの地域性の薄さにある。

また FEASIBILITY.md §4 は神格分析に
「`person_relationships` の `dedication` 型を経由する再設計が必要」と
していたが、実際には `persons[].divinity_type` を直接読むだけで
二部グラフを構成できた。
