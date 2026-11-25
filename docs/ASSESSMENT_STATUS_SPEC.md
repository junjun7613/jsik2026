# 評価状態の仕様 v1.0

策定日: 2026-11-25
対象: Claude の抽出結果（`pipeline/provenance/validated_career_graphs/claude`）の各項目が、
どこまで評価されているかを表す状態。計算は `pipeline/evaluation/assessment/compute_assessment_status.py`、
RDF への出力は `pipeline/provenance/create_rdf_himiko.py`。

## 1. 背景と方針

### 1.1 なぜ状態を持たせるか

LLM-as-a-Judge（`pipeline/evaluation/llm_judge/`）と人手確認を始めたことで、
データの項目ごとに「誰も見ていない」「LLM が判定した」「人が確認した」「人が直した」の違いが
生じた。これまではこの違いがどこにも表されておらず、判定済みかどうかは judge の実行結果の
ファイルを開かないと分からなかった。Fuseki やエディタから引くこともできなかった。

### 1.2 方針

1. **状態は保存せず、評価の記録から計算する。** 状態を JSON や RDF に書き込むと、
   再抽出・enrich・移植・復元のたびに実態とずれる（2026-11-25 の関係の移植と共同体関係の
   復元で、judge 済み 25 碑文の値が judge の後に変わった）。評価の事実は既に記録されている
   （§2.3）ので、そこから毎回計算する。
2. **評価は RDF の URI ではなく「碑文・JSON の項目・値」に結び付ける。**
   statement の URI（`mk/EDCS-…/career/0_v0`）は碑文内の連番で、作り直すと同じ URI に
   別の内容が入りうる（2026-11-25 の重複コピー除去で実際に起きた）。
3. **judge の結果を `validated_career_graphs` に書き込まない**（2026-11-21 の決定）を維持する。
   人の判定と校訂差分を分けて持つ（2026-11-22 の決定）も維持する。

## 2. 状態の定義

### 2.1 四段階

評価の単位は **項目の現在の値** である。項目は judge が判定対象とする葉のパス
（`judge_common.flatten` の judged paths。`persons` / `communities` / `person_relationships` の下で、
context-only のキーを除く）。例: `persons[0].career_path[2].position_tier`。

| 順位 | 状態 | 意味 | 記録の所在 |
|---|---|---|---|
| 3 | `human_corrected` 人手校訂済み | 現在の値が人の校訂で入った | JSON `_provenance.activities[type=manual_edit].corrected_values` |
| 2 | `human_reviewed` 人手確認済み | 人が現在の値を確認し判定を記録した | `llm_judge/runs/<run_id>/human/review_<EDCS-ID>_<校訂者>.json` |
| 1 | `llm_judged` LLM判定済み | 指定された全 judge が現在の値を含む記録を判定した | `llm_judge/runs/<run_id>/{judge}.jsonl` |
| 0 | `unassessed` 未評価 | 上のいずれもない | — |

一つの項目に複数の評価があるときは、**現在の値に対してまだ有効な評価のうち最も高い段階**をとる。

### 2.2 決定事項（2026-11-25）

| 論点 | 決定 |
|---|---|
| 人手の二段階の順序 | `human_corrected` を `human_reviewed` より上とする。校訂値の再確認段階は設けない |
| 「確認済み」の範囲 | エディタで記録を「確認済み」（`done`）にしたら、その記録の全項目を `human_reviewed` とする。`done` でなくても、判定（verdict）を付けた指摘の項目は `human_reviewed` とする |
| 「LLM判定済み」の条件 | run の `run_meta.json` に指定された全 judge が `status: ok` を返した場合のみ。一部しか返らなかった場合は数えず、根拠（`evidence`）に `counted: false` で残す |
| 失効した評価 | 一段下に戻し、`stale_from` に失効した最も高い段階を残す |

### 2.3 判定の中身は状態と分ける

judge の区分（`agree_all` / `minor_only` / `clean` など）や、どの judge が指摘したか、重大度は、
状態とは別の属性（項目の `judge`、記録の `evidence[].tier`）として持つ。
状態は「どこまで確かめたか」、判定の中身は「何と言われたか」で、意味が違う。

### 2.4 碑文・statement の状態

複数の項目からなる単位（碑文、人物・共同体の EntityReference、statement）の状態は、
**含まれる項目のうち最も低い状態**とする。件数の内訳（`field_counts`）も併せて出す。
項目を一つも持たない記録（抽出結果が空）は、記録単位の評価（judge の判定、`done` の確認）から決める。

## 3. 評価と値の照合

### 3.1 fingerprint

値の fingerprint は、値を正準化した JSON（`json.dumps(value, ensure_ascii=False, sort_keys=True)`）の
SHA-256 の先頭 12 桁とする。計算は `pipeline/provenance/_provenance_utils.py` の
`field_fingerprint` / `leaf_fingerprints` の一か所にまとめ、書き込み側と計算側の両方がこれを使う。

### 3.2 書き込み側が残すもの

| 記録 | 残すもの | 実装 |
|---|---|---|
| judge の行 | `value_shas`: 判定した全項目の `{パス: fingerprint}` | `run_judge.py`（2026-11-25 以降の run） |
| judge の行 | `input_sha`: judge に渡した入力全体のハッシュ | `run_judge.py`（既存。pilot02 / uthina01 は backfill 済み） |
| 人の判定 | 指摘ごとの `judged_value`（judge が見た値の表示文字列）、`saved_at` | `ai_epigraphy_editor`（既存） |
| 人手校訂 | `corrected_values`: 入れた値の `{パス: fingerprint}` | `apply_edits_to_json.py`（2026-11-25 以降） |

### 3.3 有効かどうかの判定

| 記録 | 判定の仕方 | 粒度 |
|---|---|---|
| judge（`value_shas` あり） | 全 judge の fingerprint が現在値と一致する項目が有効。一致しない項目は失効 | 項目 |
| judge（`input_sha` のみ） | 全 judge の `input_sha` が現在の入力のハッシュと一致すれば全項目が有効、違えば全項目が失効 | 記録 |
| judge（どちらもない） | 判定した値が分からないので失効として扱う | 記録 |
| 人の判定（指摘ごと） | `judged_value` が現在値の表示と一致すれば有効 | 項目 |
| 人の判定（`done`） | `saved_at` の後に `manual_edit` 以外の処理が記録に走っていなければ有効 | 記録 |
| 人手校訂 | `corrected_values` の fingerprint が現在値と一致すれば有効 | 項目 |

`input_sha` だけの judge 結果は保守的に扱っている。その後に一項目でも変われば、記録全体が失効する。

## 4. 計算

```
python pipeline/evaluation/assessment/compute_assessment_status.py           # 書き出す
python pipeline/evaluation/assessment/compute_assessment_status.py --check   # 集計の表示のみ
```

出力 `pipeline/evaluation/assessment/assessment_status.json`（派生物。git 管理外）:

```json
{
  "format_version": "1.0",
  "summary": { "inscriptions": 51941, "by_status": {...}, "unassessed_stale": 25, ... },
  "records": {
    "EDCS-21000578": {
      "status": "unassessed", "highest": "unassessed", "stale_from": "llm_judged",
      "field_counts": {"unassessed": 88, "llm_judged": 0, ...}, "stale_fields": 88,
      "input_sha": "…",
      "evidence": [{"kind": "llm_judge", "run_id": "uthina01", "complete": true,
                    "counted": true, "match": "record", "fresh": false, "tier": "single", ...}],
      "fields": {"persons[0].cognomen": {"state": "unassessed", "stale_from": "llm_judged",
                                         "judge": {"flagged_by": ["gpt"], "severity": "minor"}}, ...}
    }
  }
}
```

`records` には評価の記録が一つでもある碑文だけを載せる。載っていない碑文は全項目 `unassessed`。

## 5. RDF

### 5.1 語彙（`hmk_ontology` の `himiko_interpretation.ttl`）

| 語 | 種別 | 用途 |
|---|---|---|
| `hmkia:AssessmentAct` | クラス（`hmkia:InterpretationAct` の下位、`earl:Assertion` に対応） | judge の判定・人の確認 |
| `hmkia:AssessmentStatus` | クラス | 状態 |
| `hmkia:status_unassessed` / `_llm_judged` / `_human_reviewed` / `_human_corrected` | 個体 | 四段階 |
| `hmkia:assesses` | 目的語プロパティ | 評価行為 → 評価対象（現状は `epig:Inscription`） |
| `hmkia:assessmentStatus` | 目的語プロパティ | リソース → 現在の状態 |
| `hmkia:staleAssessmentStatus` | 目的語プロパティ | リソース → 失効した最も高い状態（現在より上のときだけ） |
| `hmkia:assessmentOutcome` | データ型プロパティ | judge の区分など |
| `hmkia:assessmentCurrent` | データ型プロパティ（boolean） | 評価行為が現在の値になお有効か |

評価行為の主体は既存の仕組みで表す。judge は `hmkia:associatedWith` → モデルの `SoftwareAgent`、
人の確認は `hmkia:associatedWith` → `HumanAgent`。人手校訂は値を変える行為なので
`AssessmentAct` には含めない。provenance グラフの `InterpretationUpdateAct`（`manual_edit`）のままとする。
`hmkia:supports` / `hmkia:critiques` は行為と行為の関係で、抽出行為全体への評価になって
粗すぎるので使わない。

### 5.2 出力

`create_rdf_himiko.py` が `assessment_status.json` を読み、
`rdf_output_himiko/claude/assessment_status.trig` に、グラフ `<…/graph/assessment-status>` として出す。
`all.trig` には含めない。

| 対象 | 付けるもの |
|---|---|
| 全碑文の `epig:Inscription` | `hmkia:assessmentStatus`（評価のない碑文は `status_unassessed`） |
| 評価のある碑文の人物・共同体の EntityReference | その下の項目（`career_path` / `benefactions` を除く）の最低状態 |
| 評価のある碑文の最新版の statement（経歴・恵与・関係） | その statement を作った JSON 要素の下の項目の最低状態 |
| 評価のある碑文 | judge の run・人の確認ごとに一つの `hmkia:AssessmentAct` |

statement の URI と JSON パスの対応は、`_build_*_statements` が最新版の URI を作るときに
`_STMT_PATHS` に記録する。同一の恵与を複数の人物から一つに統合した statement は、統合した
すべての JSON 要素の最低状態をとる。評価のない碑文の statement には状態を付けない
（碑文が `status_unassessed` なので、その下もすべて未評価）。

**項目単位の状態は RDF に出さない。** JSON のパスと RDF の述語は一対一に対応しない
（統合された恵与、版で分かれる項目、context-only の項目）。項目単位の状態は
`assessment_status.json` とエディタで扱う。

### 5.3 Fuseki の更新

状態だけを更新するときは、全件の入れ替えは不要である。

```
1. compute_assessment_status.py を実行
2. create_rdf_himiko.py --model claude --merge を実行（all.trig は変わらない）
3. DROP GRAPH <http://epigraphic-careers.org/graph/assessment-status>
4. assessment_status.trig を POST /data（gzip）
```

### 5.4 問い合わせの例

```sparql
PREFIX hmkia: <urn:himiko:ontology:interpretation:>
PREFIX epig:  <http://epigraphic-careers.org/ontology#>

# 状態ごとの碑文数（epig:Inscription の型は source グラフにある）
SELECT ?status (COUNT(?i) AS ?n) WHERE {
  GRAPH ?src { ?i a epig:Inscription }
  GRAPH <http://epigraphic-careers.org/graph/assessment-status> { ?i hmkia:assessmentStatus ?status }
} GROUP BY ?status

# judge の後に値が変わって失効した statement
SELECT ?stmt ?was WHERE {
  GRAPH <http://epigraphic-careers.org/graph/assessment-status> {
    ?stmt hmkia:staleAssessmentStatus ?was .
    FILTER(CONTAINS(STR(?stmt), "/mk/"))
  } }
```

## 6. 2026-11-25 時点の状態

| 状態 | 碑文数 |
|---|---|
| `unassessed` | 51,708（うち `stale_from=llm_judged` が 25） |
| `llm_judged` | 233 |
| `human_reviewed` | 0 |
| `human_corrected` | 0 |

- 失効した 25 碑文は、2026-11-25 の関係の移植（`reextract_relationships` の結果）と
  共同体関係の復元で値が変わったもの。uthina01 / pilot02 は `input_sha` のみなので、記録全体が失効している。
- pilot01 は Gemini が 2 件とも API エラーで、条件を満たさない。対象の 2 碑文は pilot02 で判定済み。

## 7. 本仕様で扱わないもの・今後

- **エディタでの表示。** `ai_epigraphy_editor` に、項目ごとの状態を表示する機能はまだない。
  `assessment_status.json` を読めば表示できる。
- **人の確認時の fingerprint。** 現在は `done` の有効性を、記録単位で時刻から判定している。
  エディタのサーバー（`tools/serve.py`）が保存時に `value_shas` を残せば、judge と同じく項目単位で判定できる。
- **既存 run の項目単位の照合。** pilot02 / uthina01 には `value_shas` がない。judge が見た時点のデータの
  写しがあれば、`backfill_judge_time_values.py` と同じ方法で後から付けられる。
- **項目単位の RDF 出力**（§5.2）。
