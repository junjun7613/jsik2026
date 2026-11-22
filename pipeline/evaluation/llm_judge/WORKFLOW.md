# LLM-as-a-Judge 評価ワークフロー

Claude による抽出結果（`validated_career_graphs/claude`）のうち、EDCS 由来のメタデータ以外の全項目を対象に、人手で確認すべき箇所の優先順位を決める。

正解データを作る仕組みではない。judge の出力は人手確認の順番を決めるためだけに使い、`validated_career_graphs` や `provenance/edits` には書き込まない。

---

## 全体フロー

```
validated_career_graphs/claude/**/*.json
        │
        ├──[1] validation/validate_career_graphs.py   形式チェック（決定的・LLMなし）
        │
        ├──[2] run_judge.py                           3モデルによる意味的判定
        │        prepare → estimate → run
        │        runs/<run_id>/{claude,gpt,gemini}.jsonl
        ▼
[3] build_review_queue.py                             優先度の算出・監査サンプル抽出
        │   runs/<run_id>/review_queue.json
        │   runs/<run_id>/agreement.json（judge間一致率）
        ▼
[4] export_for_editor.py                              校訂エディタ向けに地名ごとに書き出し
        │   editor_export/（ai_epigraphy_editor が data/judge として読む）
        ▼
    ai_epigraphy_editor                               指摘を入力欄の横に表示
            校訂 → provenance/edits/pending/（従来どおり）
            指摘への判定 → runs/<run_id>/human/
```

---

## [1] 形式チェック

```bash
cd pipeline/validation
python validate_career_graphs.py --summary --output validated_report.json
```

既存の型・必須フィールド検査に、統制語彙の検査を加えた。語彙は定義元から読み込む（`vocab.py`）。

| 対象 | 語彙の定義元 |
|---|---|
| `social_statuses[].category / subtype / rank / certainty` | `network_analysis/mapping/status_category_map.json` |
| `career_path[].position_canonical / position_tier` | `network_analysis/mapping/position_canonical_map.json` |
| `benefactions[].objects[].object_category / object_subtype` | `network_analysis/mapping/object_category_map.json` |
| `person_name_normalized / person_name_link` | `prompt_template.py` の `roman_emperors` |
| `communities[].community_type` | 抽出プロンプトの COMMUNITY TYPES（`vocab.py` に転記） |
| `social_status`（生の値） | 抽出プロンプトの STANDARDIZED SOCIAL STATUS LABELS（警告のみ） |

プロンプトにしかない語彙は `vocab.py` に転記している。`python vocab.py` を実行すると、転記した語彙がプロンプトから消えていないかを確認できる。

生の `social_status` は `social_statuses[]` に置き換えられているため、語彙外の値はエラーではなく警告にしている。

追加した欠落検査:
- enrichment フィールド（`divinity`, `life_events`, `vital_events_reasoning`）の欠落
- `benefactions[].objects` の欠落（プロンプトで必須）
- `position_canonical` と `position_tier` の片方だけがある状態
- `subtype` が `category` と整合しない状態

---

## [2] 意味的判定（run_judge.py）

### 設計

- **非エージェント型**: 固定プロンプトで、碑文1件につき1回呼び出し、JSON スキーマで制約した出力を受け取る。ツール使用や多段の探索はさせない。3モデルが同じ材料だけを見て独立に判定するので、判定が割れた理由をモデルの判断の違いに帰せる。
- **入力は3モデル共通**: system に「judge の指示」「抽出プロンプト本体（碑文部分を除く）」「抽出後の各パスの規約」を、user に EDCS メタデータ・碑文・抽出結果を入れる。抽出結果は `path = value` の1行1項目に展開して渡し、judge にはその path を引用させる。
- **ブラインド**: どのモデルが抽出したかは judge に伝えない。
- **報告するのは問題点だけ**: 指摘されなかった項目は正しいとみなす。出力トークンを抑えるため。
- **判定対象外**: `original_data`・`edcs_id`・`bibliography_parsed`（EDCS 由来）、`_provenance`、トップレベルの旧スキーマのミラー（`person_name`, `career_path` 等）。`*_reasoning`・`notes`・`*_source` などは文脈として見せるが、判定対象にはしない（`judge_common.CONTEXT_ONLY_KEYS`）。
- **重複**: 同じ EDCS-ID が複数の地名ファイルに入っている（2026-11 時点で 4,846 件）。既定ではパス順で最初の1件だけを判定する（`--include-duplicates` で全件）。
- **巨大な碑文**: 展開後に 600 行を超える碑文は送らず、`unjudged` として人手確認に回す。

### 再現性について

判定に使ったモデル ID・設定・SDK バージョン・プロンプトのハッシュは `runs/<run_id>/run_meta.json` に、system プロンプトの全文は `system_prompt.txt` に記録する。途中でプロンプトを変えると、同じ run_id では実行を拒否する。

Claude の現行モデル（Opus 5.5 など）はサンプリングパラメータ（`temperature` 等）を受け付けないため、`temperature=0` で固定できない。Gemini だけは `temperature=0` を指定している。判定のぶれは、同じ対象で run を繰り返して測る（`prepare --copy-targets-from`）。

### 使い方

```bash
cd pipeline/evaluation/llm_judge

# 対象の確定（全 judge 共通）
python run_judge.py prepare --run-id pilot01 --sample 30 --seed 42
python run_judge.py prepare --run-id uthina01 --place Uthina   # 地名（ファイルパス）で絞り込み

# 入力トークンの見積もり（Anthropic の count_tokens、無料）
python run_judge.py estimate --run-id pilot01

# 実行（再開可能。成功済みの碑文は飛ばす）
python run_judge.py run --run-id pilot01 --judges claude,gpt,gemini --workers 4

# ぶれの測定：同じ対象でもう一度
python run_judge.py prepare --run-id pilot01_rep2 --copy-targets-from pilot01
python run_judge.py run --run-id pilot01_rep2
```

judge のモデルは `judge_config.json` で指定する。API キーはプロジェクト直下の `.env`（`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`）。

出力 `runs/<run_id>/<judge>.jsonl` の `status`:

| status | 意味 | 再実行時 |
|---|---|---|
| `ok` | 判定成功 | 飛ばす |
| `refusal` | モデルが応答を拒否 | 飛ばす |
| `skipped_large` | 600 行超で送信せず | 飛ばす |
| `truncated` / `parse_error` / `api_error` | 失敗 | 再実行する |

Claude の拒否時にほかのモデルへ切り替える fallback は使っていない。judge のモデルが途中で変わらないようにするため。

---

## [3] 優先度（build_review_queue.py）

```bash
python build_review_queue.py --run-id pilot01            # 監査は後回しにした碑文の 10%
python build_review_queue.py --run-id full01 --audit-n 300
```

「major の合意」とは、2つ以上の judge がその項目を major と判定していることを指す。

| 区分 | 条件 | 並び順 |
|---|---|---|
| `format` | 形式エラーがある | 1 |
| `agree_all` | major の合意がある項目を、結果を返した全 judge が指摘 | 2 |
| `agree_2` | major の合意がある項目を、2つの judge が指摘 | 3 |
| `single` | 1つの judge だけが major とした項目がある | 4 |
| `unjudged` | judge の結果がない | 5 |
| `audit` | 後回しにした碑文（`minor_only` と `clean`）からの無作為抽出 | 6 |
| `minor_only` | minor の指摘しかない | 監査経由でのみキューに入る |
| `clean` | 指摘なし | 監査経由でのみキューに入る |

同じ区分の中では、major の合意がある項目の多い順、次に major の指摘数、最後に指摘された項目数の多い順に並べる。

重大度で区分を決めているのは、パイロット（pilot02, 2026-11-22）の結果による。どの碑文にも共通する minor な欠陥（`gender_evidence` や `ethnicity_evidence` が引用ではなく言い換えになっている）を全 judge が一致して指摘したため、一致だけで並べると30件中26件が最上位に集まった。こうしたコーパス全体に繰り返し現れる指摘は、碑文ごとに確認するより抽出プロンプトの問題として扱うべきなので、`agreement.json` の `recurring_patterns` に一度だけ出す。

`audit` は judge の見落とし率を推定するためにある。これがないと「全 judge が問題なしと判断した」のか「全 judge が同じ誤りを見落とした」のかを区別できない。エディタでは judge の出力を表示しない（ブラインド）。抽出元の区分は `audit_origin` に残す。

`agreement.json` には、全 judge が結果を返した碑文に限った judge 間の一致率を出す。
- path 単位の Jaccard（ペアごと）
- 碑文単位の「major の指摘があるか」に対する Fleiss の κ
- judge ごとの指摘数と、存在しない path の引用数
- `recurring_patterns`: 全 judge が指摘した項目を、添字を除いた path ごとに集計したもの（2件以上の碑文に現れたもの）

---

## [4] 人手確認（ai_epigraphy_editor）

judge の指摘は、校訂エディタ `ai_epigraphy_editor` に重ねて表示する。地名ごとに書き出し、エディタは symlink（`data/judge` → `editor_export/`）で読む。

```bash
python export_for_editor.py --run-id pilot02 --run-id uthina01
```

- `editor_export/manifest.json`: run ごとの judge モデル・プロンプトのハッシュ・区分の件数、judge 済みの地名
- `editor_export/places/<province>/<place>.json`: 地名ファイルのレコード位置ごとの指摘

`editor_export/` は `runs/` から作る派生物なので、git には入れない。

エディタ上での操作は ai_epigraphy_editor の README（「LLM-as-a-Judge の指摘」）を参照。指摘への人の判定は、エディタのサーバー（`tools/serve.py`）が `runs/<run_id>/human/review_<EDCS-ID>_<校訂者>.json` に保存する。校訂差分（`provenance/edits/`）とは分けている。校訂差分は「データをどう直したか」、こちらは「judge の指摘が正しかったか」の記録で、「直す必要はないが指摘は正しかった」という判定は差分では表せないためである。

### judge 時の値

judge の行（`<judge>.jsonl`）には、指摘したパスの judge 時の値（`flagged_values`）と入力のハッシュ（`input_sha`）を記録する。エディタは今のデータと比べ、judge の後に値が変わった指摘に「データ更新済み」と表示する。値を記録しているのは末端の値だけで、オブジェクトや配列を指す指摘は変化を判定しない。

pilot02 と uthina01 は、この記録を始める前に実行した。値は `backfill_judge_time_values.py` で、position_canonical_map v1.1 を適用する直前（2026-11-22T06:36Z）に取ったバックアップから補った。両 run の judge とこの適用の間に、データはほかに変わっていない。

### 単独のエディタ

`build_judge_review_editor.py` は、judge の結果だけを見る単独の HTML を作る（`docs/evaluation/judge_review_<run_id>.html`）。校訂を伴わない確認や、ai_epigraphy_editor を起動できない環境向け。人の判定はブラウザに保存され、JSON でダウンロードする。
