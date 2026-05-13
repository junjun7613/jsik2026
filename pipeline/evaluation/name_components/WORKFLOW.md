# 人名評価ワークフロー

career_graphs（LLM出力）の人名構成要素（praenomen / nomen / cognomen / gender）を EDH（Epigraphic Database Heidelberg）の正解データと照合し、精度を評価する処理フロー。

---

## 全体フロー

```
EDH Linked Data (TTL)
        │
        ▼
[1] convert_edh_ttl_to_csv.py
        │  edh_people.csv
        │  edh_inscriptions.csv
        │  edh_geography.csv
        ▼
[2] parse_roman_names.py
        │  edh_people_parsed.csv
        │  （PersonalName → praenomen/nomen/cognomen に分解）
        ▼
[3] EDH_id_extracted.csv  ←── 外部ツールで EDCS-ID を補完
        │  （HD番号 ↔ EDCS-ID 対応表）
        ▼  ※ EDH_EDCS_corresp.csv として保存
[4] evaluate_name_components.py
        │  name_eval_result_claude.json
        │  name_eval_result_claude.txt
        │  name_eval_result_claude_errors.txt
        ▼
[5] build_eval_viewer.py
           eval_viewer.html
```

---

## 各ステップ詳細

### [1] EDH Linked Data → CSV変換
**スクリプト**: `convert_edh_ttl_to_csv.py`  
**入力**: `edh_linked_data/*.ttl`（EDH公開の Linked Data）  
**出力**: `edh_linked_data/edh_people.csv`, `edh_inscriptions.csv`, `edh_geography.csv`

人物の属州情報は person から直接取れないため、以下の連鎖で解決する：

```
person  --lawd:hasAttestation-->  碑文(HD番号)
碑文    --lawd:foundAt-->         地理(geographie/XXXXX)
地理    --skos:broader-->         属州(geographie/9XXXXX)
```

| ファイル | 行数 | 主なカラム |
|---|---|---|
| edh_geography.csv | 24,934 | geo_id, label, province_name, lat, lon |
| edh_inscriptions.csv | 79,608 | hd_number, province_name, date_start, date_end |
| edh_people.csv | 82,071 | hd_number, name, gender, social_status, province_name |

---

### [2] ローマ人名パーサー
**スクリプト**: `parse_roman_names.py`  
**入力**: `edh_linked_data/edh_people.csv`  
**出力**: `edh_linked_data/edh_people_parsed.csv`

EDH の PersonalName 文字列（例: `"C. Iulius Caesar"`）を praenomen / nomen / cognomen に分解する。

**規則**:
- トークン先頭が praenomen 略称（`C.`, `L.`, `Q.` など）であれば praenomen
- 残り1語: `-ius/-ianus` で終わる → nomen、そうでない → cognomen
- 残り2語: nomen + cognomen
- 残り3語以上: nomen + cognomen + extra（agnomen等）

**略称の正規化**: 評価時に `C.` = `Gaius`、`Q.` = `Quintus` 等として照合する（`PRAENOMEN_NORM` 辞書、`evaluate_name_components.py` 内）。

| 信頼度 | 件数 | 割合 |
|---|---|---|
| high | 17,181 | 20.9% |
| medium | 59,862 | 72.8% |
| low | 5,028 | 6.3% |

---

### [3] HD ↔ EDCS 対応表の作成
**ファイル**: `EDH_id_extracted.csv` → `EDH_EDCS_corresp.csv`

EDH の HD番号と碑文データベース EDCS の ID を紐づける対応表。HD番号冒頭の `HD` プレフィックスは除去して6桁数字で記録する。

- 対象: Africa Proconsularis + Numidia で人物記録のある碑文 **2,041件**
- EDCS列の補完は外部ツールで実施
- 1つの HD に複数 EDCS-ID が対応する場合あり（碑文断片が分割記録されているケース）

---

### [4] 評価スクリプト
**スクリプト**: `evaluate_name_components.py`  
**入力**:
- `edh_linked_data/edh_people_parsed.csv`（EDH正解データ）
- `EDH_EDCS_corresp.csv`（HD↔EDCS対応表）
- `pipeline/provenance/career_graphs/<model>/`（LLM出力）

**出力**:
- `name_eval_result_<model>.json`（全碑文・全人物ペアの詳細）
- `name_eval_result_<model>.txt`（サマリー）
- `name_eval_result_<model>_errors.txt`（FP/FNログ）

#### 処理手順

1. **対象絞り込み**: EDH_EDCS_corresp.csv で対象 HD を特定し、属州（Africa Proconsularis / Numidia）に絞る
2. **CG側マージ**: 複数 EDCS-ID に対応する場合、すべてのレコードの persons を統合し、正規化名で重複排除
3. **人物アライメント（グリーディ1対1）**:
   - EDH 人物 × CG 人物の全ペアの名前トークン重複スコアを計算
   - スコア降順にソートし、双方未使用のペアを順に確定
   - 使用されなかった CG 人物は `unmatched_cg` として記録
4. **フィールド比較**: アライメントされたペアについて praenomen / nomen / cognomen / gender を照合
   - `match` / `mismatch` / `missing`（いずれかが空）で分類
   - praenomen は略称↔完全形を `PRAENOMEN_NORM` で正規化してから比較
5. **特異碑文の除外**: EDH 人物数 > 8（名前一覧・兵士名簿等）は集計から除外

#### 評価指標（claudeモデル、Africa Proconsularis + Numidia）

| フィールド | Precision | Recall | F1 |
|---|---|---|---|
| praenomen | 98.5% | 98.8% | 98.6% |
| nomen | 93.0% | 89.3% | 91.1% |
| cognomen | 82.5% | 89.7% | 86.0% |
| gender | 98.7% | 100.0% | 99.4% |

- 対象碑文: 430件（うち CG照合成功: 423件 / 98.4%）
- 人物ペア数: 1,085

---

### [5] HTMLビューア生成
**スクリプト**: `build_eval_viewer.py`  
**入力**: `name_eval_result_claude.json`, `pipeline/provenance/career_graphs/claude/`  
**出力**: `eval_viewer.html`（スタンドアロン HTML）

各碑文カードに以下を表示：
- 碑文本文テキスト
- EDH正解 vs CG出力の人物ごと対照表
- セル色分け: 緑=一致、赤=FP（誤り）、黄=FN（EDHあり・CGなし）、グレー=両方なし
- CG側のみの未対応人物（`unmatched_cg`）を赤枠テーブルで表示
- フィルター: エラーのみ表示、HD番号検索

---

## ファイル一覧

| ファイル | 種別 | 説明 |
|---|---|---|
| `convert_edh_ttl_to_csv.py` | スクリプト | EDH TTL → CSV変換 |
| `parse_roman_names.py` | スクリプト | ローマ人名パーサー |
| `evaluate_name_components.py` | スクリプト | メイン評価スクリプト |
| `build_eval_viewer.py` | スクリプト | HTMLビューア生成 |
| `sample_for_manual_eval.py` | スクリプト | 手動評価用サンプリング |
| `edh_linked_data/` | データ | EDH TTL・変換済みCSV |
| `EDH_id_extracted.csv` | データ | 対象HD番号一覧（2,041件）|
| `EDH_EDCS_corresp.csv` | データ | HD↔EDCS対応表（430件） |
| `hd_to_edcs_cache.json` | キャッシュ | TexRelations API結果 |
| `name_eval_result_claude.json` | 出力 | 評価結果（詳細） |
| `name_eval_result_claude.txt` | 出力 | 評価サマリー |
| `name_eval_result_claude_errors.txt` | 出力 | FP/FNエラーログ |
| `eval_viewer.html` | 出力 | HTMLビューア |
| `manual_eval_sample.csv` | 出力 | 手動評価サンプル100件 |
