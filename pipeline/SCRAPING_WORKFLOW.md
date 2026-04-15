# EDCS スクレイピングからJSON作成までのワークフロー

## 概要

新しいEDCS API（https://edcs.hist.uzh.ch）を使用して、地名ごとに碑文データをスクレイピングし、TSVとJSONファイルを作成するワークフローです。

## 前提条件

### 必要なライブラリ

```bash
pip install requests pandas
```

- `requests`: EDCS APIとの通信に使用
- `pandas`: TSVからJSONへの変換に使用

## ワークフロー全体

### 方法1: 属州から地名を自動抽出（推奨）

```
属州名 (例: "Numidia")
    ↓
extract_places_from_province.py
    ↓
place_list/[日付]-places_[属州名].csv (地名一覧)
    ↓
batch_scrape_new_edcs.py --province-csv
    ↓
pipeline/scraped_data/[地名]/
    ├── [日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].tsv
    └── [日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].json
```

### 方法2: 手動で地名リストを作成

```
地名リスト (places.txt / place_pleiades_mapping.json)
    ↓
batch_scrape_new_edcs.py
    ↓
pipeline/scraped_data/[地名]/
    ├── [日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].tsv
    └── [日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].json
```

## ステップ1: 地名リストの作成

### 方法A: 属州から地名を自動抽出（推奨・新機能）

属州（Province）を指定するだけで、その属州に含まれる全ての地名を自動的に抽出できます。

#### ステップ1-1: 属州から地名一覧を抽出

```bash
cd pipeline

# 例: Numidiaの全地名を抽出（最大1000件の碑文から抽出）
python extract_places_from_province.py --province "Numidia" --max-records 1000

# 例: Africa proconsularisの全地名を抽出（全件）
python extract_places_from_province.py --province "Africa proconsularis"

# 例: Britannia
python extract_places_from_province.py --province "Britannia" --max-records 5000
```

**出力:**
- `place_list/2026-02-05-places_Numidia.csv` のようなファイルが生成されます
- CSV形式: `place_name,province`

**主な属州名の例:**
- `Africa proconsularis` (属州アフリカ)
- `Numidia` (ヌミディア)
- `Mauretania Caesariensis` (カエサリア・マウレタニア)
- `Britannia` (ブリタニア)
- `Gallia Narbonensis` (ナルボ・ガリア)
- `Hispania citerior` (近ヒスパニア)
- `Italia` (イタリア)

**パラメータ:**
- `--province`: 属州名（必須）
- `--max-records`: 抽出する碑文の最大件数（省略時は全件、推奨: 1000-5000）
- `--output-dir`: 出力ディレクトリ（デフォルト: place_list）

#### ステップ1-2: 抽出した地名リストでバッチスクレイピング

```bash
# place_listディレクトリ内のCSVファイルを指定
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv

# 再開機能も使用可能
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv --resume
```

**メリット:**
- 地名リストを手動で作成する必要がない
- 属州内の全地名を網羅的に取得できる
- EDCSデータベースの表記に正確に従った地名が得られる

---

### 方法B: Pleiades Mapping JSON形式（手動作成）

プロジェクトルートの `place_pleiades_mapping.json` を使用:

```json
{
  "Oudna, Hr. / Udhnah / Uthina": "315247",
  "Djemila / Cuicul": "305068",
  "Roma": "423025"
}
```

この形式では、地名とPleiades IDを対応付けられます。

### 方法C: テキストファイル形式（手動作成）

`places.txt` を作成（1行に1つの地名）:

```text
# コメント行（#で始まる行は無視されます）
Oudna, Hr. / Udhnah / Uthina
Djemila / Cuicul
Roma
Carthago / Karthago / Carthage / Kartaĝo
```

### 方法D: CSV形式（手動作成・オプション）

CSV形式でも可能:

```csv
PlaceName,Region,Province
"Oudna, Hr. / Udhnah / Uthina",Tunisia,Africa proconsularis
"Djemila / Cuicul",Algeria,Numidia
```

## ステップ2: バッチスクレイピングの実行

**注意:** スクリプトは常に `pipeline/scraped_data/` に出力します（実行場所に関わらず）

### 属州CSVファイルを使用（推奨・新機能）

`extract_places_from_province.py`で生成されたCSVファイルを使用:

```bash
cd pipeline

# place_listディレクトリ内のCSVファイルを指定（ファイル名のみ）
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv

# 再開機能
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv --resume
```

### Pleiades Mapping JSONを使用

```bash
python batch_scrape_new_edcs.py --pleiades-mapping ../place_pleiades_mapping.json
```

### テキストファイル形式

```bash
python batch_scrape_new_edcs.py --places example_places.txt
```

### CSV形式の場合

```bash
python batch_scrape_new_edcs.py --places-csv places.csv --csv-column PlaceName
```

### 実行例の出力

```
Reading places from Pleiades mapping: ../place_pleiades_mapping.json
Found 2 places to process

[1/2] Processing: Oudna, Hr. / Udhnah / Uthina
================================================================================
Querying API for place: Oudna, Hr. / Udhnah / Uthina
  Found 228 inscriptions
  Fetched 100/228 inscriptions
  Fetched 200/228 inscriptions
  Fetched 228/228 inscriptions
  ✓ Saved TSV to: /Users/.../pipeline/scraped_data/Uthina/2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.tsv
  ✓ Saved JSON to: /Users/.../pipeline/scraped_data/Uthina/2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.json

[2/2] Processing: Djemila / Cuicul
================================================================================
Querying API for place: Djemila / Cuicul
  Found 731 inscriptions
  ...
  ✓ Saved TSV to: /Users/.../pipeline/scraped_data/Cuicul/2026-02-02-EDCS_via_Lat_Epig-place_Cuicul-731.tsv
  ✓ Saved JSON to: /Users/.../pipeline/scraped_data/Cuicul/2026-02-02-EDCS_via_Lat_Epig-place_Cuicul-731.json

================================================================================
Batch scraping complete
================================================================================
Total places: 2
Successfully processed: 2
Skipped (already done): 0
Errors: 0
================================================================================
```

## ステップ3: 生成されるファイル構造

### ディレクトリ構造

**重要:** 出力ファイルは常に `pipeline/scraped_data/` 内に保存されます（実行場所に関わらず）

```
pipeline/
└── scraped_data/
    ├── Uthina/
    │   ├── 2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.tsv
    │   └── 2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.json
    ├── Cuicul/
    │   ├── 2026-02-02-EDCS_via_Lat_Epig-place_Cuicul-731.tsv
    │   └── 2026-02-02-EDCS_via_Lat_Epig-place_Cuicul-731.json
    └── [その他の地名]/
        └── ...
```

### フォルダ名の生成ルール

地名からフォルダ名を自動生成：

- `Oudna, Hr. / Udhnah / Uthina` → `Uthina`
- `Djemila / Cuicul` → `Cuicul`
- `Roma` → `Roma`

ルール：
1. `/` で分割し、最後の部分（古代名）を使用
2. カンマ以降を削除
3. スペース、ピリオド、特殊文字を削除

## ステップ4: 出力ファイル形式

### TSVファイル

タブ区切りのテキストファイル（Excel等で開ける）

**カラム:**
- `EDCS-ID`: 碑文ID（例: EDCS-00000223）
- `publication`: 出版物・文献情報
- `province`: ローマ属州名
- `place`: 地名
- `dating_from`, `dating_to`: 年代範囲
- `status`: 碑文の分類（セミコロン区切り）
- `inscription`: 碑文テキスト
- `inscription_conservative_cleaning`: クリーニング版1
- `inscription_interpretive_cleaning`: クリーニング版2
- `material`: 材質（例: lapis = 石）
- `latitude`, `longitude`: 座標
- `language`: 言語コード
- `photo`: 写真の有無
- `partner_link`: EDCS詳細ページへのリンク
- その他

### JSONファイル

**形式:** `convert_tsv_to_json.py` に準拠

```json
[
  {
    "EDCS-ID": "EDCS-00000223",
    "publication": "AE 2021 01544",
    "province": "Africa proconsularis",
    "place": "Oudna, Hr. / Udhnah / Uthina",
    "dating_from": 201,
    "dating_to": 229,
    "date_not_before": 201,
    "date_not_after": 229,
    "status": [],
    "inscription": "[3] pro [3] / [6] / ...",
    "inscription_conservative_cleaning": "...",
    "inscription_interpretive_cleaning": "...",
    "material": "lapis",
    "comment": "",
    "latitude": 36.60005,
    "longitude": 10.1820304,
    "language": "la",
    "photo": "",
    "partner_link": "https://edcs.hist.uzh.ch/inscription/223",
    "extra_text": "",
    "extra_html": "",
    "raw_dating": "201 to 229"
  },
  ...
]
```

**重要:** `status` フィールドは配列形式（`convert_tsv_to_json.py` の形式）

## ステップ5: 中断からの再開

スクレイピングが中断された場合、再開できます：

```bash
python batch_scrape_new_edcs.py --pleiades-mapping ../place_pleiades_mapping.json --resume
```

- 既に処理済みの地名はスキップされます
- 進捗は `batch_scrape_progress_new.txt` に記録されます

**注意:** 現在、スキップ機能は`--resume`フラグとプログレスファイルに基づいてのみ動作します。フォルダの存在をチェックして自動的にスキップする機能は実装されていません。

カスタム進捗ファイル：

```bash
python batch_scrape_new_edcs.py --pleiades-mapping ../place_pleiades_mapping.json --resume --resume-file my_progress.txt
```

## 技術詳細

### EDCS API仕様

**エンドポイント:** `https://edcs.hist.uzh.ch/api/query`

**パラメータ:**
- `place`: 地名
- `start`: 開始位置（ページネーション）
- `length`: 取得件数（最大100件推奨）
- `draw`: リクエスト番号

**レスポンス:**
```json
{
  "draw": 1,
  "recordsTotal": 542179,
  "recordsFiltered": 228,
  "data": [
    {
      "monument_id": 223,
      "obj": {
        "edcs-id": "EDCS-00000223",
        "ort": "Oudna, Hr. / Udhnah / Uthina",
        "provinz": "Africa proconsularis",
        ...
      }
    }
  ]
}
```

### データ取得の流れ

1. **初回クエリ**: 総件数を取得
2. **バッチ取得**: 100件ずつ取得（ページネーション）
3. **TSV変換**: APIデータをTSV形式に変換
4. **TSV保存**: `pipeline/scraped_data/[地名]/[ファイル名].tsv` に保存
5. **JSON変換**: Pandasでload → `status` フィールドを配列化
6. **JSON保存**: `pipeline/scraped_data/[地名]/[ファイル名].json` に保存

**出力場所の仕組み:**
- スクリプトは `Path(__file__).parent` を使用してスクリプト自身の場所を特定
- 常に `pipeline/scraped_data/` に出力（実行場所に関わらず）
- プロジェクトルートから実行しても、`pipeline/` 内から実行しても同じ場所に保存

### convert_tsv_to_json.py との互換性

スクレイパーは `convert_tsv_to_json.py` と同じロジックでJSONを生成：

```python
# status フィールドを配列に変換
if item.get('status'):
    status_list = [s.strip() for s in item['status'].split(';') if s.strip()]
    item['status'] = status_list
else:
    item['status'] = []
```

## 使用例

### 例1: 属州から地名を自動抽出してスクレイピング（推奨）

```bash
cd pipeline

# ステップ1: Numidiaの地名を抽出
python extract_places_from_province.py --province "Numidia" --max-records 1000

# 出力例: place_list/2026-02-05-places_Numidia.csv (184件の地名)

# ステップ2: 抽出した地名でスクレイピング
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv
```

### 例2: Africa proconsularisの全地名を取得

```bash
# ステップ1: 地名抽出（5000件の碑文から）
python extract_places_from_province.py --province "Africa proconsularis" --max-records 5000

# ステップ2: スクレイピング（再開機能付き）
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Africa_proconsularis.csv --resume
```

### 例3: 単一地名のスクレイピング

```bash
echo "Roma" > single_place.txt
python batch_scrape_new_edcs.py --places single_place.txt
```

### 例4: 複数地名の一括処理（手動リスト）

```bash
cat > places.txt << EOF
Carthago / Karthago / Carthage / Kartaĝo
Lepcis Magna / Leptis Magna
Lambaesis / Lambese
Thamugadi / Timgad
Cuicul / Djemila
EOF

python batch_scrape_new_edcs.py --places places.txt
```

### 例5: CSV形式での処理

```bash
cat > places.csv << EOF
PlaceName,Notes
"Oudna, Hr. / Udhnah / Uthina","Test site"
"Djemila / Cuicul","Well preserved"
EOF

python batch_scrape_new_edcs.py --places-csv places.csv --csv-column PlaceName
```

## パフォーマンス

### 処理速度

- 小規模（<100件）: 約1-2秒
- 中規模（100-500件）: 約5-15秒
- 大規模（>500件）: 約20-60秒

**実測例:**
- Uthina（228件）: 約6秒
- Cuicul（731件）: 約20秒

### バッチサイズ

- デフォルト: 100件/リクエスト
- API制限: 1リクエストあたり最大100件推奨
- タイムアウト: 30秒/リクエスト

## トラブルシューティング

### エラー: "File not found" (province-csv使用時)

**原因:** 指定したCSVファイルが`place_list`ディレクトリに存在しない

**解決策:**
```bash
# place_listディレクトリの内容を確認
ls -lh pipeline/place_list/

# ファイル名を正確に指定
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv
```

### エラー: "No places found"

**原因:** 入力ファイルが空、または全行がコメント

**解決策:**
```bash
# ファイル内容を確認
cat places.txt

# コメント行（#で始まる）を削除
grep -v "^#" places.txt
```

### エラー: "Found 0 inscriptions"

**原因:** 地名がEDCSに存在しない、または地名の綴りが間違っている

**解決策:**

**方法1: 属州から地名を自動抽出（推奨）**
```bash
# 正確な地名リストを自動生成
python extract_places_from_province.py --province "Numidia" --max-records 1000
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv
```

**方法2: 手動で地名を確認**
1. https://edcs.hist.uzh.ch/en/search で地名を検索
2. オートコンプリートに表示される正確な地名をコピー
3. `places.txt` にペースト

### エラー: "pandas not available"

**原因:** Pandasがインストールされていない

**解決策:**
```bash
pip install pandas
```

JSONファイルは作成されませんが、TSVファイルは正常に作成されます。

### エラー: "Connection timeout"

**原因:** EDCSサーバーが遅い、またはネットワーク問題

**解決策:**
1. しばらく待ってから再試行
2. `--resume` オプションで中断から再開

```bash
python batch_scrape_new_edcs.py --places places.txt --resume
```

## データの活用

### Pandasでの読み込み

```python
import pandas as pd

# TSVを読み込み
df = pd.read_csv('pipeline/scraped_data/Uthina/2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.tsv',
                 sep='\t')

# 基本統計
print(f"Total inscriptions: {len(df)}")
print(f"Date range: {df['dating_from'].min()} - {df['dating_to'].max()}")
```

### JSONでの読み込み

```python
import json

# JSONを読み込み
with open('pipeline/scraped_data/Uthina/2026-02-02-EDCS_via_Lat_Epig-place_Uthina-228.json') as f:
    inscriptions = json.load(f)

# 件数
print(f"Total: {len(inscriptions)}")

# statusフィールドはリスト形式
for insc in inscriptions:
    if insc['status']:
        print(f"{insc['EDCS-ID']}: {insc['status']}")
```

### 既存ツールとの統合

このデータは以下のツールで使用できます：

- `convert_cost_to_numeric.py`: コスト情報の数値化
- `create_rdf.py`: RDFデータの作成
- その他のデータ処理スクリプト

## ステップ6: キャリアグラフの抽出（オプション）

スクレイピングしたデータから、碑文に記載された人物の経歴情報を自動抽出できます。

### キャリアグラフとは

碑文から以下の情報を抽出します：
- **人物名**: 碑文に記載された人物の名前
- **経歴**: 就任した官職の順序と時期
- **日付情報**: 碑文の年代（dating_from, dating_to）

### バッチキャリアグラフ抽出の実行

スクレイピング完了後、全地名のデータを一括処理してキャリアグラフを抽出できます。

```bash
cd pipeline

# Claude（デフォルト）を使用
python batch_extract_career_graphs.py --model claude

# 特定の地名のみ処理（カンマ区切り）
python batch_extract_career_graphs.py --model claude --places "Uthina,Cuicul"

# テスト用に各地名10件のみ処理
python batch_extract_career_graphs.py --model claude --limit 10
```

### 対応モデル

以下のLLMモデルを選択可能：

```bash
# Claude（推奨・デフォルト）
python batch_extract_career_graphs.py --model claude

# Gemini
python batch_extract_career_graphs.py --model gemini

# GPT
python batch_extract_career_graphs.py --model gpt
```

**APIキー設定:**
- `.env` ファイルに以下を設定：
  - Claude: `ANTHROPIC_API_KEY=your-key`
  - Gemini: `GEMINI_API_KEY=your-key`
  - GPT: `OPENAI_API_KEY=your-key`
- または `--api-key` オプションで指定

### 既存データの活用

スクリプトは既存の経歴データを自動的に再利用します：

1. **既存データの検索**: プロジェクトルートの `career_graphs/claude/*/` を検索
2. **EDCS-ID一致チェック**: 既存データにEDCS-IDが存在する場合、そのまま使用
3. **新規抽出**: 既存データがない碑文のみLLMで抽出

これにより、処理時間とAPIコストを大幅に削減できます。

### 出力ファイル構造

```
pipeline/
└── career_graphs/
    └── claude/                        # モデル名（claude/gemini/gpt）
        ├── Uthina/
        │   └── Uthina_career.json     # 228件の経歴データ
        ├── Cuicul/
        │   └── Cuicul_career.json     # 731件の経歴データ
        └── [その他の地名]/
            └── [地名]_career.json
```

### キャリアグラフJSONの形式

```json
[
  {
    "edcs_id": "EDCS-00012345",
    "person_name": "L. Valerius Maximus",
    "person_name_readable": "Lucius Valerius Maximus",
    "has_career": true,
    "career_path": [
      {
        "office": "tribunus militum",
        "office_en": "Military Tribune",
        "period_from": 201,
        "period_to": 229,
        "sequence": 1
      },
      {
        "office": "quaestor",
        "office_en": "Quaestor",
        "period_from": 201,
        "period_to": 229,
        "sequence": 2
      }
    ],
    "dating_from": 201,
    "dating_to": 229,
    "notes": "Career extracted successfully",
    "original_data": {
      "EDCS-ID": "EDCS-00012345",
      "inscription": "...",
      ...
    }
  },
  {
    "edcs_id": "EDCS-00067890",
    "person_name": "Unknown",
    "person_name_readable": "Unknown",
    "has_career": false,
    "career_path": [],
    "notes": "No career information found",
    "original_data": { ... }
  }
]
```

### 処理の流れ

1. **データ読み込み**: `scraped_data/[地名]/*.json` から碑文データを読み込み
2. **既存データ確認**: ルート `career_graphs/claude/` から既存の経歴データを検索
3. **データ判定**:
   - 既存データあり → コピーして使用（高速・無料）
   - 既存データなし → LLMで新規抽出（約10-20秒/件）
4. **チェックポイント保存**: 10件ごとに自動保存
5. **結果出力**: `career_graphs/[model]/[地名]/[地名]_career.json`

### 中断と再開

処理が中断しても安全に再開できます：

- **自動チェックポイント**: 10件ごとに結果を保存
- **自動スキップ**: 既に処理済みのEDCS-IDは自動的にスキップ
- **再実行**: 同じコマンドを再実行するだけで未処理の碑文から再開

**再開例:**
```bash
# 処理が中断された場合、同じコマンドを再実行
python batch_extract_career_graphs.py --model claude
```

スクリプトが既存の出力ファイルを検出し、未処理の碑文のみを処理します。

### 実行例の出力

```
================================================================================
Batch Career Graph Extraction
================================================================================
Model: claude
Scraped data directory: /Users/.../pipeline/scraped_data
Output directory: /Users/.../pipeline/career_graphs
Existing career data: /Users/.../career_graphs/claude
Places to process: 2

[Uthina]
  Found existing output: 0 already processed
  Uthina: 100%|████████████| 228/228 [15:30<00:00]
  ✓ Saved 228 career entries to .../career_graphs/claude/Uthina/Uthina_career.json

[Cuicul]
  Found existing output: 0 already processed
  Cuicul: 100%|████████████| 731/731 [48:20<00:00]
  ✓ Saved 731 career entries to .../career_graphs/claude/Cuicul/Cuicul_career.json

================================================================================
Summary
================================================================================
Places processed: 2
Total inscriptions: 959
Processed: 959
  - Copied from existing: 4
  - Extracted new: 955
Skipped (already done): 0
Errors: 0

Top 10 places by inscription count:
--------------------------------------------------------------------------------
 1. Cuicul                                     731 inscriptions (copied: 4, new: 727, errors: 0)
 2. Uthina                                     228 inscriptions (copied: 0, new: 228, errors: 0)
================================================================================
```

### パフォーマンス

- **既存データコピー**: 瞬時（0秒）
- **新規LLM抽出**: 約10-20秒/件
- **推定時間**:
  - 100件の新規抽出: 約15-30分
  - 500件の新規抽出: 約1.5-3時間
  - 1000件の新規抽出: 約3-6時間

**コスト削減のヒント:**
- 既存データを活用して重複抽出を避ける（自動）
- `--limit` オプションでテスト実行（例: `--limit 10`）
- 特定の地名のみ処理（例: `--places "Uthina"`）

### トラブルシューティング

**エラー: "API key not set"**
```bash
# .envファイルにAPIキーを設定
echo 'ANTHROPIC_API_KEY=your-api-key-here' >> .env

# または環境変数で設���
export ANTHROPIC_API_KEY='your-api-key-here'
python batch_extract_career_graphs.py --model claude
```

**エラー: "No JSON files found"**
- 原因: `scraped_data/[地名]/` にJSONファイルが存在しない
- 解決策: 先に `batch_scrape_new_edcs.py` でスクレイピングを実行

**処理が遅い場合**
- 既存データを活用（自動）
- `--limit` オプションでテスト（例: `--limit 10`）
- 特定の地名のみ処理（例: `--places "Uthina,Cuicul"`）

## ステップ7: キャリアグラフデータの拡張（オプション）

キャリアグラフデータに追加情報を付与して、分析の精度を向上させることができます。

### データ拡張とは

抽出済みのキャリアグラフデータに以下の情報を自動付与します：

1. **神格判定（Divinity Classification）**
   - 碑文に記載された人物が神格（神・女神・神格化皇帝）か人間かを判定
   - 神格の場合は神名（Iuppiter, Mercurius等）を抽出

2. **コスト数値化（Cost Conversion）**
   - 恵与行為（benefaction）のコスト記述を数値に変換
   - ローマ貨幣単位（sesterces, denarii）を保持

### データ拡張の実行

キャリアグラフ抽出完了後、以下のコマンドでデータを拡張できます。

```bash
cd pipeline

# 全地名のデータを拡張（既処理碑文は自動スキップ）
python enrich_career_graphs.py --model claude

# 特定の地名のみ処理
python enrich_career_graphs.py --model claude --places "Uthina,Cuicul"

# 神格判定のみ実行（コスト変換をスキップ）
python enrich_career_graphs.py --model claude --skip-cost

# コスト変換のみ実行（神格判定をスキップ）
python enrich_career_graphs.py --model claude --skip-divinity

# 既処理碑文を含めて全て再処理（強制モード）
python enrich_career_graphs.py --model claude --force-reprocess
```

### 処理の流れ

1. **入力データ読み込み**: `career_graphs/[model]/[地名]/*.json`
2. **神格判定**: 各人物（person）について：
   - 人物名と碑文本文をLLMで分析
   - 神格か人間かを判定
   - 神格の場合は神名を抽出
3. **コスト変換**: 各恵与行為（benefaction）について：
   - コスト記述（例: "HS 350,000"）をLLMで解析
   - 数値と通貨単位に変換（例: 350000 sesterces）
4. **出力**: `modified_career_graphs/[model]/[地名]/*.json`

### 出力ファイル構造

```
pipeline/
└── modified_career_graphs/
    └── claude/                                    # モデル名
        ├── Uthina/
        │   └── Uthina_career.json                # 拡張済みデータ
        ├── Oudna_Hr_Udhnah_Uthina/
        │   └── Oudna_Hr_Udhnah_Uthina_career.json
        └── [その他の地名]/
            └── [地名]_career.json
```

### 拡張後のJSONデータ形式

#### 神格判定フィールド

各人物（person）に以下のフィールドが追加されます：

```json
{
  "person_name": "Iuppiter Augustus",
  "divinity": true,
  "divinity_type": "Iuppiter",
  "divinity_classification_reasoning": "Roman supreme god Jupiter with imperial epithet",
  "gender": "male",
  "person_id": 0
}
```

**フィールド説明:**
- `divinity`: 神格かどうか（true/false）
- `divinity_type`: 神格の場合、主要な神名（例: "Iuppiter", "Mercurius", "Hadrianus"）
- `divinity_classification_reasoning`: 判定理由

#### コスト変換フィールド

各恵与行為（benefaction）に以下のフィールドが追加されます：

```json
{
  "benefaction": "construction of temple",
  "cost": "HS 350,000",
  "cost_numeric": 350000,
  "cost_unit": "sesterces",
  "cost_original": "HS 350,000",
  "cost_conversion_reasoning": "HS CCCL(milium) = 350,000 sesterces"
}
```

**フィールド説明:**
- `cost_numeric`: 数値化されたコスト（整数）
- `cost_unit`: 通貨単位（"sesterces" または "denarii"）
- `cost_original`: 元のコスト記述
- `cost_conversion_reasoning`: 変換の根拠

### 神格判定の例

検出される神格の例：

| 碑文記載 | divinity_type | 説明 |
|---------|---------------|------|
| Iuppiter Optimus Maximus | Iuppiter | ローマ最高神ユピテル |
| Mercurius Augustus | Mercurius | 商業・旅行の神メルクリウス |
| Divi Hadriani | Hadrianus | 神格化された皇帝ハドリアヌス |
| Genius coloniae | Genius | 植民市の守護霊 |
| Minerva | Minerva | 知恵と戦争の女神ミネルウァ |
| Dis Manibus | Manes | 死者の霊（墓碑の定型句） |

### コスト変換の例

| 元の記述 | cost_numeric | cost_unit | 説明 |
|---------|--------------|-----------|------|
| HS 50000 | 50000 | sesterces | 50,000セステルティウス |
| HS L milia | 50000 | sesterces | L (50) × 1000 = 50,000 |
| 600 denarii | 600 | denarii | 600デナリウス |
| sumptibus suis | null | null | 金額不明（「自費で」） |
| denarii terni | null | null | 一人当たり金額（総額不明） |

### 処理統計の例

```
================================================================================
Career Graph Enrichment
================================================================================
Model: claude
Input directory: /Users/.../career_graphs/claude
Output directory: /Users/.../modified_career_graphs/claude
Places to process: 1

[Oudna_Hr_Udhnah_Uthina]
  Processing: Oudna_Hr_Udhnah_Uthina_career.json
    Oudna_Hr_Udhnah_Uthina_career: 100%|██████| 228/228 [20:15<00:00]
  ✓ Saved to: modified_career_graphs/claude/Oudna_Hr_Udhnah_Uthina/...

================================================================================
Summary
================================================================================
Places processed: 1
Files processed: 1
Total inscriptions: 228
Total persons: 183
  - Divinities: 8
  - Humans: 175
Total benefactions: 15
  - Cost converted: 1
Errors: 0
```

### 再開機能と差分処理

#### 自動スキップ（デフォルト動作）

`modified_career_graphs`ディレクトリに出力ファイルが既に存在する場合、**EDCS-IDベースで既に処理済みの碑文を自動的にスキップ**します：

```bash
# デフォルト：既存の処理済み碑文をスキップ
python enrich_career_graphs.py --model claude --places "Uthina"

# 出力例：
# Found existing output file, loading processed inscriptions...
# Loaded 228 already processed inscriptions
# Skipped 228 already processed inscriptions
```

**利点:**
- 処理が中断されても、同じコマンドで続きから再開できる
- 新しい碑文が追加されたデータセットを効率的に処理
- 不要なAPI呼び出しとコストを削減

#### 強制再処理

既に処理済みの碑文を再度処理する必要がある場合は、`--force-reprocess`オプションを使用：

```bash
# 全ての碑文を再処理（既存データを上書き）
python enrich_career_graphs.py --model claude --places "Uthina" --force-reprocess
```

**使用ケース:**
- LLMのプロンプトを改善した後、全データを再分析したい場合
- 処理結果に問題があり、やり直したい場合
- データ構造を変更した場合

#### チェックポイント保存

処理中は10件ごとに中間結果を自動保存します：

- 処理が予期せず中断されても、データが失われない
- 再実行時、既に保存された碑文は自動スキップ
- 大量のデータ処理でも安全

#### 処理統計の表示

スキップされた碑文の数を明示的に表示：

```
Total inscriptions: 228
  - Skipped (already processed): 228
  - Newly processed: 0
```

### パフォーマンス

- **神格判定**: 約5-10秒/人物
- **コスト変換**: 約5-10秒/恵与行為
- **推定時間**:
  - 100人の神格判定: 約10-20分
  - 50件のコスト変換: 約5-10分

### トラブルシューティング

**エラー: "career_graphs directory not found"**
- 原因: キャリアグラフが未抽出
- 解決策: 先に `batch_extract_career_graphs.py` でキャリアグラフを抽出

**エラー: "API key not set"**
```bash
# .envファイルにAPIキーを設定
echo 'ANTHROPIC_API_KEY=your-api-key-here' >> .env
```

**処理が遅い場合**
- 特定の地名のみ処理: `--places "Uthina"`
- 不要な処理をスキップ: `--skip-cost` または `--skip-divinity`

### 既存ツールとの統合

拡張済みデータは以下の用途に利用できます：

- **神格分析**: 地域ごとの信仰対象の分布を分析
- **経済分析**: コスト情報から恵与行為の規模を数値的に比較
- **RDF化**: セマンティックウェブ用のデータとして出力
- **データベース化**: リレーショナルDBに格納して検索・集計

## ステップ8: RDF/TTL形式への変換（オプション）

拡張済みのキャリアグラフデータをRDF（Resource Description Framework）形式に変換し、セマンティックウェブでの活用や、SPARQL等での高度な検索を可能にします。

### RDF変換とは

拡張済みJSONデータ（神格判定・コスト変換済み）をTurtle (TTL)形式に変換します：

- **入力**: `validated_career_graphs/[model]/[地名]/*.json`（バリデーション・スキーマ修正済みデータ）
- **出力**: `rdf_output/[model]/[地名]/*.ttl`
- **Pleiades ID連携**: `place_list/`のCSVから地名とPleiades IDの対応を自動読み込み

### RDF変換の実行

```bash
cd pipeline

# 特定の地名を変換
python create_rdf.py --model claude --place "Uthina"

# 全ての地名を変換
python create_rdf.py --model claude --all

# カスタム出力先を指定
python create_rdf.py --model claude --place "Uthina" --output custom.ttl

# 別のフォーマットで出力
python create_rdf.py --model claude --place "Uthina" --format json-ld
```

### サポートされる出力フォーマット

| フォーマット | 拡張子 | 説明 |
|------------|--------|------|
| `turtle` | .ttl | Turtle形式（デフォルト、人間が読みやすい） |
| `xml` | .rdf | RDF/XML形式 |
| `json-ld` | .jsonld | JSON-LD形式（JSON互換） |
| `n3` | .n3 | Notation3形式 |
| `nt` | .nt | N-Triples形式 |

### RDFデータ構造

#### 名前空間

```turtle
@prefix base: <http://example.org/inscription/> .
@prefix epig: <http://example.org/epigraphy/> .
@prefix person: <http://example.org/person/> .
@prefix divinity: <http://example.org/divinity/> .
@prefix place: <http://example.org/place/> .
@prefix foaf: <http://xmlns.com/foaf/0.1/> .
```

#### 碑文の基本情報

```turtle
base:EDCS-00000223 a epig:Inscription ;
    dcterms:identifier "EDCS-00000223" ;
    epig:province province:Africa_proconsularis ;
    epig:place place:Oudna_Hr_Udhnah_Uthina ;
    epig:pleiadesId "315247" ;
    epig:datingFrom 201 ;
    epig:datingTo 229 ;
    epig:text "[碑文テキスト...]" ;
    dcterms:bibliographicCitation "AE 2021 01544" .
```

#### Pleiades IDとの連携

地名にPleiades Gazetterへのリンクを自動付与：

```turtle
place:Oudna_Hr_Udhnah_Uthina a epig:Place ;
    rdfs:label "Oudna, Hr. / Udhnah / Uthina" ;
    skos:exactMatch <https://pleiades.stoa.org/places/315247> .

# 碑文にもPleiades IDを記録
base:EDCS-00000223 epig:pleiadesId "315247" .
```

#### 人物情報（神格判定含む）

**人間の場合**:
```turtle
person:EDCS-08600983_person_0 a foaf:Person ;
    foaf:name "Gellius" ;
    rdfs:label "Gellius" ;
    epig:isDivinity false ;
    epig:divinityClassificationReasoning "Gellius is a common Roman gentilicium..." ;
    epig:nomen nomen:Gellius ;
    foaf:gender "male" .
```

**神格の場合**:
```turtle
person:EDCS-21000583_person_0 a foaf:Person, epig:Divinity ;
    foaf:name "Divi [3] Hadriani(?)" ;
    epig:isDivinity true ;
    epig:divinityType divinity:Hadrianus ;
    epig:divinityClassificationReasoning "Deified emperor Hadrian, indicated by 'Divus' title" ;
    epig:cognomen cognomen:Hadrianus ;
    epig:socialStatus status:emperor ;
    foaf:gender "male" .
```

**神格タイプ**:
```turtle
divinity:Hadrianus a epig:DivinityType ;
    rdfs:label "Hadrianus" .

divinity:Iuppiter a epig:DivinityType ;
    rdfs:label "Iuppiter" .
```

#### 恵与行為（コスト情報含む）

```turtle
benef:EDCS-26500906_person_0_benef_0 a epig:Benefaction ;
    rdfs:label "[恵与行為の説明]" ;
    epig:benefactionType "donation" ;
    epig:costOriginal "HS 350,000" ;
    epig:costNumeric 350000 ;
    epig:costUnit "sesterces" ;
    epig:costConversionReasoning "HS CCCL(milium) = HS 350 × 1000 = 350,000 sesterces..." .
```

### 新規追加されたRDFプロパティ

#### 神格判定関連

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `epig:isDivinity` | xsd:boolean | 神格かどうか（true/false） |
| `epig:divinityType` | URI | 神格の種類（例: divinity:Iuppiter） |
| `epig:divinityClassificationReasoning` | xsd:string | 判定理由 |
| `rdf:type epig:Divinity` | - | 神格の場合に付与されるクラス |

#### コスト変換関連

| プロパティ | 型 | 説明 |
|-----------|-----|------|
| `epig:costNumeric` | xsd:integer | 数値化されたコスト |
| `epig:costUnit` | xsd:string | 通貨単位（"sesterces" or "denarii"） |
| `epig:costOriginalText` | xsd:string | 元のコスト記述 |
| `epig:costConversionReasoning` | xsd:string | 変換理由 |

### Pleiades IDマッピングの仕組み

スクリプトは`place_list/`ディレクトリ内の全CSVファイルから自動的にマッピングを読み込みます：

```csv
place_name,province,longitude,latitude,inscription_count,Pleiades_ID
"Oudna, Hr. / Udhnah / Uthina",Africa proconsularis,10.612,36.496,228,315247
```

このマッピングに基づき、碑文の地名にPleiades IDを自動付与します。

### 処理統計の例

```
================================================================================
RDF Creation from Modified Career Graphs
================================================================================
Model: claude
Modified graphs directory: .../modified_career_graphs/claude
Pleiades mappings: 38 places

Processing 1 place(s)...

[Oudna_Hr_Udhnah_Uthina]
Loading JSON data: Oudna_Hr_Udhnah_Uthina_career.json
  Loaded 228 inscriptions
Serializing to turtle format...
  ✓ RDF saved to: rdf_output/claude/Oudna_Hr_Udhnah_Uthina/Oudna_Hr_Udhnah_Uthina_career.ttl

================================================================================
Conversion complete!
================================================================================
Total inscriptions processed: 228
Output directory: rdf_output/claude
================================================================================
```

## ステップ9: RDFファイルの統合（オプション）

複数の地名から生成されたRDFファイルを1つのファイルに統合し、一括でSPARQLエンドポイントやグラフデータベースにロードできるようにします。

### RDFファイル統合とは

各地名ごとに生成された個別のTTLファイルを統合して、モデル全体のデータを含む単一のRDFファイルを作成します：

- **入力**: `rdf_output/[model]/[地名1]/*.ttl`, `rdf_output/[model]/[地名2]/*.ttl`, ...
- **出力**: `rdf_output/[model]/all.ttl`

### RDFファイル統合の実行

```bash
cd pipeline

# 指定モデルの全RDFファイルを統合
python merge_rdf_files.py --model claude

# カスタム出力ファイル名を指定
python merge_rdf_files.py --model claude --output merged_data.ttl

# 別のフォーマットで出力（RDF/XML）
python merge_rdf_files.py --model claude --format xml

# 別のフォーマットで出力（JSON-LD）
python merge_rdf_files.py --model claude --format json-ld
```

### サポートされる出力フォーマット

| フォーマット | 拡張子 | 説明 |
|------------|--------|------|
| `turtle` | .ttl | Turtle形式（デフォルト） |
| `xml` | .rdf | RDF/XML形式 |
| `json-ld` | .jsonld | JSON-LD形式 |
| `n3` | .n3 | Notation3形式 |
| `nt` | .nt | N-Triples形式 |

### 統合処理の流れ

1. **RDFファイルの検出**: 指定モデルディレクトリ内の全地名フォルダから`.ttl`, `.rdf`, `.n3`, `.nt`, `.jsonld`ファイルを検索
2. **グラフの統合**: 各RDFファイルをパースして1つのRDFグラフに統合
3. **トリプルの結合**: 重複なくすべてのトリプル（三つ組）を結合
4. **シリアライゼーション**: 指定フォーマットで単一ファイルに出力

### 処理統計の例

```
================================================================================
RDF File Merger
================================================================================
Model: claude
Input directory: .../rdf_output/claude
Output file: .../rdf_output/claude/all.ttl
Output format: turtle

Found 3 RDF files to merge

  Merging: Uthina/Uthina_career.ttl
  Merging: Oudna_Hr_Udhnah_Uthina/Oudna_Hr_Udhnah_Uthina_career.ttl
  Merging: Cuicul/Cuicul_career.ttl

Total files merged: 3
Total triples: 15,234

Writing merged RDF to .../rdf_output/claude/all.ttl...
  ✓ Merged RDF saved to: .../rdf_output/claude/all.ttl

================================================================================
Merge complete!
================================================================================
Files merged: 3
Total triples: 15,234
Output file: .../rdf_output/claude/all.ttl
File size: 1.2 MB
================================================================================
```

### 出力ファイル構造

統合後のディレクトリ構造：

```
pipeline/
└── rdf_output/
    └── claude/
        ├── all.ttl                          # 統合ファイル
        ├── Uthina/
        │   └── Uthina_career.ttl
        ├── Oudna_Hr_Udhnah_Uthina/
        │   └── Oudna_Hr_Udhnah_Uthina_career.ttl
        └── Cuicul/
            └── Cuicul_career.ttl
```

### パフォーマンス

- **統合速度**: 約1,000トリプル/秒
- **メモリ効率**: すべてのトリプルをメモリに読み込むため、大規模データセット（100万トリプル以上）では注意が必要
- **ファイルサイズ**: 個別ファイルの合計とほぼ同等（若干の圧縮あり）

### トラブルシューティング

**エラー: "Model directory not found"**
- 原因: 指定したモデルのRDF出力ディレクトリが存在しない
- 解決策: 先に`create_rdf.py`でRDFファイルを生成

**警告: "No RDF files found"**
- 原因: 指定ディレクトリにRDFファイルが存在しない
- 確認: `rdf_output/[model]/*/`に`.ttl`などのファイルがあるか確認

**エラー: "Error parsing [filename]"**
- 原因: 特定のRDFファイルに構文エラーがある
- 動作: エラーファイルをスキップして処理を継続
- 対処: エラーファイルを再生成するか、手動で修正

### RDFデータの活用例

#### 1. SPARQLクエリ

統合されたRDFデータをSPARQLエンドポイントにロードすることで、高度な検索が可能になります：

```sparql
# 神格への献呈碑を検索
SELECT ?inscription ?divinity_name ?divinity_type
WHERE {
  ?inscription epig:mentions ?person .
  ?person epig:isDivinity true ;
          foaf:name ?divinity_name ;
          epig:divinityType ?divinity_type .
}

# 特定金額以上の恵与行為を検索
SELECT ?inscription ?person ?cost ?unit
WHERE {
  ?person epig:hasBenefaction ?benef .
  ?benef epig:costNumeric ?cost ;
         epig:costUnit ?unit .
  FILTER (?cost >= 100000)
}

# Pleiades IDで地名を検索
SELECT ?inscription ?place_name ?pleiades_uri
WHERE {
  ?inscription epig:place ?place .
  ?place rdfs:label ?place_name ;
         skos:exactMatch ?pleiades_uri .
  FILTER (CONTAINS(STR(?pleiades_uri), "315247"))
}
```

#### 2. 外部データセットとの連携

Pleiades Gazetterとのリンクにより：
- 地理情報データベースと連携
- GISツールでの可視化
- 他の古代史データセットとの統合

#### 3. グラフデータベースへのインポート

- Neo4j、Amazon Neptune等のグラフDBへのインポート
- ネットワーク分析（人物関係、地域間の関係等）
- 視覚的なグラフ探索

### トラブルシューティング

**エラー: "Modified career graphs directory not found"**
- 原因: `modified_career_graphs/[model]/`ディレクトリが存在しない
- 解決策: 先に`enrich_career_graphs.py`でデータ拡張を実行

**警告: "Place list directory not found"**
- 影響: Pleiades IDマッピングなしで変換が続行される
- 解決策: `place_list/`ディレクトリにCSVファイルを配置

**Pleiades IDが付与されない**
- 原因1: CSVファイルに`Pleiades_ID`列が存在しないか、値が空
- 原因2: JSONの地名とCSVの`place_name`が完全一致していない
- 確認方法: CSVファイルを開いて該当地名の行を確認

### パフォーマンス

- **処理速度**: 約200-300碑文/秒
- **ファイルサイズ**: JSON 1MBあたり約200-300KBのTTL
- **例**: 228碑文（JSON 1MB）→ TTL 236KB

## まとめ

### ワークフロー概要

#### 推奨ワークフロー（属州ベース）

1. **属州から地名抽出** → `extract_places_from_province.py`
2. **地名リストCSV生成** → `place_list/[日付]-places_[属州名].csv`（座標・Pleiades ID含む）
3. **スクレイピング実行** → `batch_scrape_new_edcs.py --province-csv`
4. **自動生成** → TSVとJSON（`pipeline/scraped_data/[地名]/`）
5. **キャリアグラフ抽出**（オプション）→ `batch_extract_career_graphs.py --model claude`
6. **経歴データ生成** → JSON（`pipeline/career_graphs/[model]/[地名]/`）
7. **データ拡張**（オプション）→ `enrich_career_graphs.py --model claude`
8. **拡張済みデータ生成** → JSON（`pipeline/modified_career_graphs/[model]/[地名]/`）
9. **スキーマ修正・エクスポート**（オプション）→ `validation/fix_and_export.py --model claude`
10. **バリデーション済みデータ生成** → JSON（`pipeline/validated_career_graphs/[model]/[地名]/`）
11. **最終バリデーション**（オプション）→ `validation/validate_career_graphs.py --target validated --model claude`
12. **RDF変換**（オプション）→ `create_rdf.py --model claude`
13. **RDFファイル生成** → TTL（`pipeline/rdf_output/[model]/[地名]/`）
14. **データ活用** → SPARQL検索・グラフDB・GIS可視化等

#### 従来のワークフロー（手動リスト）

1. **地名リスト作成** → `place_pleiades_mapping.json` または `places.txt`
2. **スクレイピング実行** → `batch_scrape_new_edcs.py`
3. **自動生成** → TSVとJSON（`pipeline/scraped_data/[地名]/`）
4. **キャリアグラフ抽出**（オプション）→ `batch_extract_career_graphs.py --model claude`
5. **経歴データ生成** → JSON（`pipeline/career_graphs/[model]/[地名]/`）
6. **データ拡張**（オプション）→ `enrich_career_graphs.py --model claude`
7. **拡張済みデータ生成** → JSON（`pipeline/modified_career_graphs/[model]/[地名]/`）
8. **スキーマ修正・エクスポート**（オプション）→ `validation/fix_and_export.py --model claude`
9. **バリデーション済みデータ生成** → JSON（`pipeline/validated_career_graphs/[model]/[地名]/`）
10. **最終バリデーション**（オプション）→ `validation/validate_career_graphs.py --target validated --model claude`
11. **RDF変換**（オプション）→ `create_rdf.py --model claude`
12. **RDFファイル生成** → TTL（`pipeline/rdf_output/[model]/[地名]/`）
13. **データ活用** → SPARQL検索・グラフDB・GIS可視化等

### 主要コマンド

**ステップ1-2: スクレイピング**
```bash
# 属州から地名抽出（推奨）
python extract_places_from_province.py --province "Numidia" --max-records 1000

# 属州CSVでスクレイピング（推奨）
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv

# Pleiades Mapping JSON形式
python batch_scrape_new_edcs.py --pleiades-mapping ../place_pleiades_mapping.json

# テキストファイル形式
python batch_scrape_new_edcs.py --places places.txt

# 再開
python batch_scrape_new_edcs.py --province-csv 2026-02-05-places_Numidia.csv --resume

# CSV形式
python batch_scrape_new_edcs.py --places-csv places.csv --csv-column PlaceName
```

**ステップ3: キャリアグラフ抽出（オプション）**
```bash
# 全地名を処理（既存データを自動活用）
python batch_extract_career_graphs.py --model claude

# 特定の地名のみ処理
python batch_extract_career_graphs.py --model claude --places "Uthina,Cuicul"

# テスト実行（各地名10件のみ）
python batch_extract_career_graphs.py --model claude --limit 10

# 他のモデルを使用
python batch_extract_career_graphs.py --model gemini
python batch_extract_career_graphs.py --model gpt
```

**ステップ4: データ拡張（オプション）**
```bash
# 神格判定とコスト変換を実行（既処理碑文は自動スキップ）
python enrich_career_graphs.py --model claude

# 特定の地名のみ処理
python enrich_career_graphs.py --model claude --places "Uthina,Cuicul"

# 神格判定のみ実行
python enrich_career_graphs.py --model claude --skip-cost

# コスト変換のみ実行
python enrich_career_graphs.py --model claude --skip-divinity

# 全て再処理（既処理データを上書き）
python enrich_career_graphs.py --model claude --force-reprocess
```

**ステップ5: スキーマ修正・エクスポート（オプション）**
```bash
# modified_career_graphsのスキーマ修正を行い、validated_career_graphsに出力
python validation/fix_and_export.py --model claude

# 特定地名のみ処理
python validation/fix_and_export.py --model claude --places "Uthina,Cuicul"

# 実行内容の確認のみ（ファイルを書き出さない）
python validation/fix_and_export.py --model claude --dry-run
```

**ステップ6: 最終バリデーション（オプション）**
```bash
# validated_career_graphsの最終チェック
python validation/validate_career_graphs.py --target validated --model claude

# サマリーのみ表示
python validation/validate_career_graphs.py --target validated --model claude --summary

# JSONレポートを保存
python validation/validate_career_graphs.py --target validated --model claude --output report.json
```

**ステップ7: RDF変換（オプション）**
```bash
# 特定の地名をRDF変換（入力: validated_career_graphs/）
python create_rdf.py --model claude --place "Uthina"

# 全ての地名をRDF変換
python create_rdf.py --model claude --all

# カスタム出力先を指定
python create_rdf.py --model claude --place "Uthina" --output custom.ttl

# 別のフォーマットで出力（JSON-LD, RDF/XML等）
python create_rdf.py --model claude --place "Uthina" --format json-ld
```

### 出力ファイル

**スクレイピング出力:**
- **TSV**: `pipeline/scraped_data/[地名]/[日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].tsv`
- **JSON**: `pipeline/scraped_data/[地名]/[日付]-EDCS_via_Lat_Epig-place_[地名]-[件数].json`

**キャリアグラフ出力（オプション）:**
- **JSON**: `pipeline/career_graphs/[model]/[地名]/[地名]_career.json`

**拡張済みデータ出力（オプション）:**
- **JSON**: `pipeline/modified_career_graphs/[model]/[地名]/[地名]_career.json`

**バリデーション済みデータ出力（オプション）:**
- **JSON**: `pipeline/validated_career_graphs/[model]/[地名]/[地名]_career.json`
- **ログ**: `pipeline/validation/logs/fix_export_[model]_[timestamp].log`
- **バリデーションログ**: `pipeline/validation/logs/final_validation_[model]_[timestamp].log`

**RDF出力（オプション）:**
- **TTL**: `pipeline/rdf_output/[model]/[地名]/[地名]_career.ttl`

### 入力形式の選択

| 形式 | ファイル | オプション | 用途 | 作成方法 |
|------|---------|-----------|------|---------|
| **属州CSV** | `place_list/[日付]-places_[属州].csv` | `--province-csv` | 属州から地名を自動抽出（推奨） | `extract_places_from_province.py`で自動生成 |
| **Pleiades Mapping** | `place_pleiades_mapping.json` | `--pleiades-mapping` | Pleiades IDとの対応付けが必要な場合 | 手動作成 |
| **テキスト** | `places.txt` | `--places` | シンプルな地名リスト | 手動作成 |
| **CSV** | `places.csv` | `--places-csv` | 複数の列を持つデータ | 手動作成 |

### 参考資料

- 新EDCS: https://edcs.hist.uzh.ch/en/search
- 詳細ドキュメント: [BATCH_SCRAPING_NEW_EDCS.md](BATCH_SCRAPING_NEW_EDCS.md)
- クイックスタート: [README_BATCH_SCRAPING.md](README_BATCH_SCRAPING.md)
- 移行ガイド: [MIGRATION_SUMMARY.md](MIGRATION_SUMMARY.md)

## 現在の対象都市
☑️Carthago	チュニス近郊	州都・帝国第2の都市
☑️☑️Utica	ビゼルト近郊	共和政期から重要都市 enrich:スタート時：102💲（140件）終了時：💲
☑️☑️Hippo Diarrhytus	ビゼルト	港湾都市　enrich:スタート時：💲（140件）終了時：100💲
☑️☑️Thugga (Dougga)	ドゥッガ	劇場・神殿遺構が有名　enrich:スタート時：100💲（140件）終了時：81💲
☑️☑️Bulla Regia	ジャンドゥーバ	地下住宅群
☑️☑️Simitthu	シェムトゥ	大理石産地
☑️☑️Sicca Veneria	エル・ケフ	宗教中心地　enrich:スタート時：70💲（821件）終了時：58.5💲
☑️☑️Mactaris	マクトゥル	先住民・ローマ文化融合都市
☑️☑️Thuburbo Maius	エル・ファウワール	神殿群
☑️☑️Uthina	ウドナ	円形闘技場
☑️☑️Maxula	ラデス	カルタゴ近郊港湾
☑️☑️Lepcis Magna

☑️Hadrumetum	スース	重要港湾
☑️Thysdrus	エル・ジェム	巨大円形闘技場
☑️Sufetula	スベイトラ	三神殿
☑️Capsa	ガフサ	オアシス都市
☑️Acholla	ブーカラ	古い港町
☑️Leptis Minor	ラムタ	商業都市
☑️Thaenae	ティナ	軍事拠点
☑️Zama Regia	ジャマ	第二次ポエニ戦争の地
☑️Cillium	カスリーヌ	凱旋門で有名

☑️☑️Cirta	コンスタンティーヌ	州都
☑️Hippo Regius	アンナバ	アウグスティヌス司教座
☑️Calama	ゲルマ	司教都市
☑️Thibilis	アンナバ内陸
☑️Rusicade	スキクダ	港湾都市
☑️Chullu	コロ	港湾都市
☑️Milev

☑️Lambaesis	タズールト	第3アウグスタ軍団本営
☑️Thamugadi (Timgad)	ティムガッド	計画都市
☑️Cuicul (Djemila)	ジェミラ	世界遺産
☑️Theveste	テベッサ	軍事拠点　スタート時：150💲（927件）終了時：118💲
☑️Madauros	マダウロシュ	アプレイウス出身地
☑️Diana Veteranorum	ゼララ	退役兵植民都市　スタート時：118💲（102件）終了時：113💲
☑️Mascula	ケンチェラ	スタート時：113💲（130件）終了時：109💲
☑️Verecunda	バトナ近郊	スタート時：109💲（113件）終了時：104.5💲
☑️Tigisis	アイウン スタート時：104.5💲（73件）終了時：102💲