# Social Status 評価ワークフロー

career_graphs（LLM出力）の `social_status` フィールドを EDH の正解データと照合し、精度を評価する処理フロー。

人名評価（name_components）と同じアライメント済みペアデータを入力として使用するため、TTL変換・人名パーサー・アライメントの再実行は不要。

---

## 全体フロー

```
name_components/name_eval_result_claude.json
（アライメント済み人物ペア）
        │
        ▼
[1] status_mapping.json で正規化
    EDH値・CG値を共通の EDH カテゴリに変換
        │
        ▼
[2] evaluate_status.py
    ペア単位で match / FP / FN を判定
        │
        ├── status_eval_result.txt（テキストサマリー）
        │
        ▼
[3] build_status_viewer.py
        │
        └── status_viewer.html（HTMLビューア）
```

---

## 各ステップ詳細

### [1] 正規化マッピング
**ファイル**: `status_mapping.json`

EDH の social_status は10カテゴリだが、CG 出力は約90種の細粒度値を持つ。両者を EDH カテゴリに正規化してから比較する。

**マッピング対象 EDH カテゴリと CG 値**

| EDH カテゴリ | CG 値（主なもの） |
|---|---|
| `imperial_household` | emperor, empress, imperial-family, imperial-administration, imperial-freedman-or-slave, imperial-slave-or-freedman |
| `senatorial` | senator, senator-clarissimus, senator-consularis, senator-praetorius, consul, legatus, quaestor, pontifex, augur, patricius, provincial-governor, curator |
| `equestrian` | equestrian, equestrian-perfectissimus, equestrian-egregius, equestrian-splendidus, equestrian-excellentissimus, equestrian-eminentissimus, equestrian-decurio |
| `decurial` | decurio, decurion, municipal-magistrate, municipal-elite, duovir, aedilis, quinquennalis, promagister, flamen-decurio, veteran-decurio |
| `military` | military, soldier, veteran, centurio, tribunus, military-commander |
| `freedman` | freedman, freedwoman |
| `slave` | slave, imperial-slave |
| `augustalis` | augustalis, sevir |
| `local_official` | local_official, local, local-administration, provincial-administration |
| `foreign_ruler` | local-ruler, king |

**マッピング対象外（評価から除外）**:
- `citizen`, `freeborn`, `unknown`, `other`, `occupation` — 身分不問・不明
- キリスト教関連（`martyr`, `deacon`, `monk`, `bishop` 等）— EDH にカテゴリなし
- 職業系（`artisan`, `merchant`, `medicus`, `actor` 等）— EDH にカテゴリなし
- `deity`, `deceased-spirit`, `gladiator`, `charioteer` — 帰属が曖昧

**正規化ロジック**（`evaluate_status.py` / `build_status_viewer.py` 内 `normalize()`）:
- 小文字化 → そのまま lookup → アンダースコア↔ハイフン変換後 lookup の順に試行

---

### [2] 評価スクリプト
**スクリプト**: `evaluate_status.py`  
**入力**: `../name_components/name_eval_result_claude.json`, `status_mapping.json`  
**出力**: `status_eval_result.txt`

#### 判定ロジック

アライメント済みペア（`aligned=True`）のみを対象とする。

| 条件 | 判定 |
|---|---|
| EDH・CG ともにマッピング外または空欄 | `missing`（除外） |
| EDH がマッピング外または空欄（CG に値あり） | `skip`（除外） |
| 正規化後 EDH == CG | `match` → TP |
| 正規化後 EDH ≠ CG（CG に値あり） | `mismatch` → FN（EDH側）+ FP（CG側） |
| CG がマッピング外または空欄（EDH に値あり） | `fn` → FN（EDH側） |

#### 評価指標

3種の平均を出力する。

| 方式 | 説明 |
|---|---|
| **MICRO avg** | 全ペアの TP/FP/FN を合算してから P/R/F1 を計算。件数の多いカテゴリの性能を反映 |
| **MACRO avg** | カテゴリごとの F1 を単純平均。件数の少ないカテゴリも均等に扱う |
| **WEIGHTED MACRO avg** | EDH 側の実件数（TP+FN）で重みづけして平均。カテゴリ間の件数差を考慮 |

#### 評価結果（claudeモデル、Africa Proconsularis + Numidia）

| カテゴリ | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| augustalis | 0 | 5 | 0 | 0.0% | 0.0% | 0.0% |
| decurial | 34 | 5 | 11 | 87.2% | 75.6% | 81.0% |
| equestrian | 34 | 4 | 4 | 89.5% | 89.5% | 89.5% |
| freedman | 6 | 2 | 1 | 75.0% | 85.7% | 80.0% |
| imperial_household | 355 | 7 | 5 | 98.1% | 98.6% | 98.3% |
| military | 52 | 3 | 12 | 94.5% | 81.2% | 87.4% |
| senatorial | 281 | 5 | 52 | 98.3% | 84.4% | 90.8% |
| slave | 1 | 0 | 2 | 100.0% | 33.3% | 50.0% |
| **MICRO avg** | 763 | 31 | 87 | **96.1%** | **89.8%** | **92.8%** |
| **MACRO avg** | | | | **80.3%** | **68.5%** | **72.1%** |
| **WEIGHTED MACRO avg** | | | | **96.7%** | **89.8%** | **92.9%** |

- 対象アライメント済みペア: 2,401件
- 評価対象（双方マッピング可能）: 850件
- `augustalis` の TP=0 は Africa Proc. + Numidia の EDH データに augustalis が存在しないため

---

### [3] HTMLビューア
**スクリプト**: `build_status_viewer.py`  
**入力**: `../name_components/name_eval_result_claude.json`, `status_mapping.json`, EDH テキスト CSV, EDCS テキスト  
**出力**: `status_viewer.html`（スタンドアロン HTML）

- サマリーテーブル（カテゴリ別 + 3種平均）
- 碑文カードにLLM入力テキスト（EDCS）と EDH edition text を2列表示
- 人物ごとに EDH name / CG name / EDH status（生値→正規化）/ CG status（生値→正規化）を対照表示
- セル色分け: 緑=match、赤=FP、黄=FN
- フィルター: エラーのみ表示、HD番号検索、カテゴリ絞り込み

---

## ファイル一覧

| ファイル | 種別 | 説明 |
|---|---|---|
| `status_mapping.json` | データ | CG値 → EDH カテゴリ 正規化マッピング |
| `evaluate_status.py` | スクリプト | メイン評価スクリプト |
| `build_status_viewer.py` | スクリプト | HTMLビューア生成 |
| `status_eval_result.txt` | 出力 | 評価サマリー（テキスト） |
| `status_viewer.html` | 出力 | HTMLビューア |
