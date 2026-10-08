# inscription_llm — Claude向け開発ガイド

## オントロジー参照先

**スキーマの正典（最新版）は常に以下を参照すること：**

```
/Users/junogawa/Dropbox/PC/Projects/hmk_ontology/ontology/
```

| ファイル | 名前空間プレフィックス | URN |
|---|---|---|
| `epig_ontology.ttl` | `epig:` | `http://epigraphic-careers.org/ontology#` |
| `hmk_owl/himiko_physical.ttl` | `hmkp:` | `urn:himiko:ontology:physical:` |
| `hmk_owl/himiko_physical_tei.ttl` | `hmktei:` | `urn:himiko:ontology:physical:tei:` |
| `hmk_owl/himiko_intrinsic.ttl` | `hmki:` | `urn:himiko:ontology:intrinsic:` |
| `hmk_owl/himiko_extrinsic.ttl` | `hmke:` | `urn:himiko:ontology:extrinsic:` |
| `hmk_owl/himiko_interpretation.ttl` | `hmkia:` | `urn:himiko:ontology:interpretation:` |
| `hmk_owl/himiko_i18n_en.ttl` | — | 英語ラベル定義 |

- データ構造の修正・追加時は必ずこれらのTTLを確認し、クラス・プロパティの定義に従うこと。
- `inscription_llm/pipeline/provenance/ontology/` は存在しない（削除済み）。このプロジェクト内にオントロジーファイルのコピーはない。
- オントロジーの編集は `hmk_ontology` リポジトリ側で行い、`inscription_llm` 側では読み取り専用で参照する。
- `pipeline/epig_ontology.ttl` は `create_ontology.py` がRDFデータから**生成する**ファイルであり、スキーマ定義ではない。スキーマは上記 `hmk_ontology` 側の `epig_ontology.ttl` を参照すること。
