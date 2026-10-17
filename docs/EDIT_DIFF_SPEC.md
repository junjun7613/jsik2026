# 校訂差分フォーマット仕様 v1.0

策定日: 2026-10-16
対象: `ai_epigraphy_editor`（外部エディタ）と `apply_edits_to_json.py`（本体）の契約

## 1. 背景と方針

### 1.1 従来の構成とその問題

```
JSON → create_rdf_himiko.py → Fuseki → エディタ(SPARQL) → 差分
                                ↑                           ↓
                                └─── apply_editor_json.py ──┘
                                             ↓
                            export_corrections_to_json.py → JSON
```

校訂が RDF を経由して JSON に戻る往復構造だった。`export_corrections_to_json.py`
の docstring が自ら述べるとおり、書き戻しが滞ると「次の enrichment が未校訂値に
対して走り、再取り込みでタイムスタンプが機械グラフに負ける」。
**JSON が単一の真実であるべきなのに、往復の途中だけ別の真実が存在する**。

さらに実装上、エディタは `SPARQL_UPDATE_ENDPOINT` に対して
`DELETE WHERE` を直接発行していた。`apply_editor_json.py` の docstring は
「ブラウザから直接書けないので差分を出力する」としており、設計意図と実装が
乖離していた。

### 1.2 新しい構成

```
validated_career_graphs (JSON)
        ↓ 読み込み（地名単位）
   ai_epigraphy_editor
        ↓ 差分ファイル
   edits/pending/ → apply_edits_to_json.py → edits/applied/
        ↓
validated_career_graphs (JSON)   ← 単一の真実
        ↓ create_rdf_himiko.py
      Fuseki (RDF)               ← 派生物。一方向
```

- エディタは **RDF と直接やり取りしない**
- RDF は JSON からの派生物に徹する（競合が構造的に発生しない）
- 差分は **反映済み / 未反映** をディレクトリで分離して管理する

### 1.3 移行にあたっての確認（2026-10-16 実施）

Fuseki に人手校訂が残っていないことを確認した。残っていれば JSON に
吸い出す必要があったが、その作業は不要。

| 確認項目 | 結果 |
|---|---|
| `hmkia:InterpretationAct` の件数 | **0** |
| JSON 内の `manual_edit` activity | **0** |
| WORK_LOG_2026-10-07 §2.2 | 試験用 editor グラフ2本は `DROP GRAPH` 済み |

したがって `apply_editor_json.py` / `export_corrections_to_json.py` は
**削除してよい**（データの取り残しが発生しない）。

---

## 2. 差分ファイル

### 2.1 ファイル名

```
edit_<EDCS_ID>_<editor>.json
```

例: `edit_EDCS-24501137_junogawa.json`

1ファイル = 1碑文（1 EDCS ID）。複数碑文をまたぐ差分は作らない。
適用の成否を碑文単位で切り分けられるようにするため。

**同一碑文の未適用差分は上書き統合する。** 適用前の差分は作業途中の
状態であり、`pending/` に複数並ぶと適用順序に依存した競合が起きる。
ファイル名に時刻を含めないのはこのため。`applied/` へ移った時点の
最終形が記録として残る。

サーバ経由で保存できない場合のダウンロード名には時刻を含める
（ダウンロードフォルダでの衝突を避けるため）。

### 2.2 構造

```json
{
  "format_version": "1.0",
  "edcs_id": "EDCS-24501137",
  "source_file": "claude/Africa_proconsularis/Aine_el_Asker/Aine_el_Asker_career.json",
  "record_index": 3,
  "editor": "junogawa",
  "timestamp": "2026-10-16T12:00:00Z",
  "note": "参事会員と祭司職の両方が明示されているため多軸化",
  "edits": [
    {
      "path": "persons[0].social_status",
      "op": "replace",
      "old_value": "decurio",
      "new_value": "citizen"
    }
  ]
}
```

| フィールド | 必須 | 意味 |
|---|---|---|
| `format_version` | ✓ | 本仕様のバージョン |
| `edcs_id` | ✓ | 対象碑文 |
| `source_file` | ✓ | `validated_career_graphs/` からの相対パス |
| `record_index` | ✓ | ファイル内のレコード位置（同一 edcs_id の重複対策） |
| `editor` | ✓ | 校訂者の識別子 |
| `timestamp` | ✓ | 差分作成時刻（UTC, ISO8601） |
| `note` | | 校訂意図。`_provenance` に記録される |
| `edits` | ✓ | 変更の配列。空配列は不正 |

### 2.3 edits[] の要素

| フィールド | 必須 | 意味 |
|---|---|---|
| `path` | ✓ | 変更箇所（§3） |
| `op` | ✓ | `replace` / `add` / `remove` |
| `old_value` | `replace`/`remove` で必須 | 変更前の値。競合検出に用いる（§4） |
| `new_value` | `replace`/`add` で必須 | 変更後の値 |

---

## 3. パス記法

`_provenance.activities[].generated_fields` が既に使っている記法に揃える。
ただし差分では**具体的な添字**を伴う。

```
persons[0].social_status
persons[0].social_statuses[1].subtype
persons[2].career_path[0].position_type
persons[0].benefactions[1].objects[0].object_category
communities[0].community_type
person_relationships[3].relationship_type
notes
```

規則:

- ドット区切りでオブジェクトのキーを辿る
- `[n]` は 0 起点の配列添字
- 配列要素そのものを対象にする場合、末尾が `[n]` になる（`add` / `remove`）

### 3.1 配列の add / remove

可変長配列（`social_statuses[]`, `objects[]`, `career_path[]` 等）の
要素追加・削除は添字の意味が変わるため、以下の規則で扱う。

**add** — 指定位置に挿入する。末尾追加は現在の長さを指定する。

```json
{
  "path": "persons[0].social_statuses[2]",
  "op": "add",
  "new_value": {
    "category": "religious",
    "subtype": "religious.flamen_standing",
    "evidence": "flam(en) perp(etuus)",
    "certainty": "explicit",
    "source": "manual"
  }
}
```

**remove** — `old_value` に削除対象の値を完全に記載する。

```json
{
  "path": "persons[0].social_statuses[1]",
  "op": "remove",
  "old_value": { "category": "ordo", "subtype": "ordo.decurio_cavalry", "...": "..." }
}
```

**1ファイル内で同一配列に対する add/remove を複数含める場合、
添字は「適用前の状態」を基準とし、`apply_edits_to_json.py` が
降順に処理する。** 昇順だと先行する挿入で後続の添字がずれるため。

---

## 4. 競合検出

RDF 版は Fuseki に問い合わせて `prov:generatedAtTime` を比較していた。
JSON 版では**適用時に現在値と `old_value` を照合する**。

```
現在値 == old_value  → 適用
現在値 != old_value  → 競合。そのファイルは適用せず conflict/ に退避する
```

差分は `timestamp`（編集した時刻）の古い順に適用する。同じ碑文に複数の
校訂者の差分があるとき、先に編集したものが採られ、後のものは競合になる。
新しい方を自動で優先（後勝ち）にはしない。後の校訂者は先の校訂を見ずに
書いており、上書きすると先の校訂が気づかれずに消えるため。競合した差分は
人が両方を見て判断する。エディタは、他の校訂者の未適用の差分がある碑文を
開いたときに警告し、競合を起こりにくくする。

これにより、差分作成後に enrichment や別の校訂が同じ箇所を変更した場合を
検出できる。`old_value` を必須にしているのはこのためである。

`add` は照合対象がないため、配列長のみ検証する（指定添字 <= 現在の長さ）。

---

## 5. 反映済み / 未反映の管理

```
edits/
├── pending/     未反映。エディタはここに出力する
├── applied/     反映済み。apply_edits_to_json.py が移動する
│   └── 2026-10-16/          適用日ごとのサブディレクトリ
├── conflict/    競合により適用できなかったもの
└── apply_log.jsonl          適用の記録（追記のみ）
```

**ディレクトリ移動で状態を表現する。** 理由:

- ファイル移動は原子的で、中断しても中間状態が残らない
- `ls edits/pending/ | wc -l` で未反映件数が即座に分かる
- 差分ファイル自体を書き換えないため、内容が常に作成時のまま

`apply_log.jsonl` には1行1適用で記録する。

```json
{"file":"edit_EDCS-24501137_20261016T120000Z_junogawa.json","result":"applied","edits":1,"timestamp":"2026-10-16T12:05:00Z"}
{"file":"edit_EDCS-99999999_...json","result":"conflict","reason":"persons[0].social_status: expected 'decurio', found 'citizen'","timestamp":"..."}
```

---

## 6. 適用時の provenance 記録

適用した差分は `_provenance.activities` に `manual_edit` として記録する。
`create_rdf_himiko.py` が人手校訂として RDF に反映できるようにするため。

```json
{
  "activity_id": "manual_edit-junogawa-2026-10-16T120500Z",
  "script": "apply_edits_to_json.py",
  "type": "manual_edit",
  "editor": "junogawa",
  "timestamp": "2026-10-16T12:05:00Z",
  "note": "参事会員と祭司職の両方が明示されているため多軸化",
  "source_diff": "edit_EDCS-24501137_20261016T120000Z_junogawa.json",
  "generated_fields": ["persons[0].social_status"]
}
```

`generated_fields` には実際に変更した path を列挙する。
機械生成の activity と同じ形式であり、`create_rdf_himiko.py` の
フィールド登録表がそのまま機能する。

**既存の enrichment activity は削除しない。** 校訂は上書きではなく
追記であり、「機械がこう判定し、人がこう直した」という履歴を保つ。

---

## 7. エディタ側の読み込み単位

地名単位（`*_career.json` 1ファイル）で読み込む。

実測した規模:

| | |
|---|---:|
| 地名数 | 2,042 |
| 合計 | 534.7 MB |
| 中央値 | 22.9 KB |
| 1MB 超 | 68地名 |
| **最大（Carthago）** | **69.8 MB / 9,082 records** |

> 69.8MB はディスク上のサイズ（indent=2 で整形済み）。整形を除いた
> 実データは 54.1MB。内訳は `_provenance` 23.0MB(42.4%)、
> `persons` 15.3MB(28.3%)、`original_data` 5.9MB(10.9%)。

中央値は 22.9KB で問題ないが、**最大の Carthago は 69.8MB あり
ブラウザに一括で載せるのは現実的でない**。以下のいずれかが要る。

1. **レコード単位の遅延読み込み** — 一覧は軽量インデックスから作り、
   碑文を開いたときに当該レコードのみ取得する
2. **事前の分割配信** — ビルド時に地名を N 件ずつのチャンクに割る
3. **`_provenance` の除外** — Carthago 実測で **42.4%** を占め、
   `persons`(28.3%) より大きい。編集に不要なので配信から外すだけで
   **4割強が落ちる**

少なくとも 3 は必須。1 または 2 との併用を推奨する。

---

## 8. 本仕様で扱わないもの

| 項目 | 扱い |
|---|---|
| 認証・権限 | エディタは差分を出力するだけ。適用は本体側の手動実行 |
| 複数校訂者の同時編集 | 競合検出（§4）で後勝ちを防ぐに留める |
| 差分の取り消し | `applied/` から差分を読み、逆向きの差分を生成する運用で対応 |
| RDF への反映 | `create_rdf_himiko.py` の再実行。差分とは独立 |
