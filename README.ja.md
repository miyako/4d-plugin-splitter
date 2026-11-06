# Splitter

[English](README.md) | [日本語](README.ja.md)

[`miyako/4d-plugin-splitter`](https://github.com/miyako/4d-plugin-splitter) で開発している、4D 用のネイティブテキストツールキットです。
M1 は「最初の実装マイルストーン」を意味し、Apple M1 のことではありません。
M1 では、4D のネイティブコマンドと互換性のあるリテラル分割、複数のリテラル区切り文字、
リソース制限付き ICU 正規表現分割、明示的に選択する拡張書記素クラスタ分割を実装しています。
CSV/TSV とその他のツールキット機能は後続マイルストーンの対象であり、**実装済みの API ではありません**。

Splitter は [MIT ライセンス](LICENSE)で公開しています。配布バンドルには、プロジェクトの
ライセンスと、ICU/データおよび 4D Plug-in SDK の完全なライセンス通知を
`Contents/Resources/licenses/` に同梱しています。

## インストール

公開済みのダウンロードは [v0.1.0](https://github.com/miyako/4d-plugin-splitter/releases/tag/v0.1.0) にあります。
[`Splitter-macos-signed.dmg`](https://github.com/miyako/4d-plugin-splitter/releases/download/v0.1.0/Splitter-macos-signed.dmg)
と [`Splitter-macos-signed.zip`](https://github.com/miyako/4d-plugin-splitter/releases/download/v0.1.0/Splitter-macos-signed.zip)
は arm64/x86_64 ユニバーサル版で、Developer ID 署名および公証済みです。
DMG には公証チケットをステープルしていますが、ZIP にはステープルしていません。
[`Splitter-windows-x64.zip`](https://github.com/miyako/4d-plugin-splitter/releases/download/v0.1.0/Splitter-windows-x64.zip)
は未署名です。このリリースはビルド・署名ワークフローの実行後に手動で公開しました。
通常のプッシュ・PR ビルドは引き続き未署名の Actions アーティファクトとして保存されます。
新しいリリースは、手動実行する **Build** が検証後に署名・公開します。署名済みダウンロードの検証には、
リリースに添付した外部の `signing-provenance.json`、`SHA256SUMS` と macOS の署名を使用してください。
内部の `build-manifest.json` は、意図的に署名前の入力の来歴を記録したままにしています。
未署名パッケージ専用の `scripts/unpack.py` は署名済み ZIP を拒否します。

ホストを終了し、適切なパッケージを展開または開いて、**`Splitter.bundle` 全体**を
ホストプロジェクトの `Plugins/` フォルダーにコピーし、ホストを再起動してください。

```text
Host/
  Project/
  Plugins/
    Splitter.bundle/
      Contents/
        MacOS/Splitter              # macOS package: arm64 + x86_64
        Windows64/Splitter.4DX      # Windows package: x64
        Resources/
          manifest.json
          icudt79l.dat
          licenses/
          dependencies.lock.json
          build-manifest.json
```

各プラットフォームのパッケージには、そのプラットフォーム用の実行ファイルディレクトリが入っています。
専用の ICU 79.1 コードは静的リンクされ、対応する完全な分割用データと
上流の完全なライセンス通知を同梱しています。実行時のダウンロードや OS/ホストの ICU の使用はありません。
データが欠落していると正規表現・書記素の呼び出しは Null を返して失敗しますが、
ネイティブのリテラル分割はそのデータに依存しません。

コンポーネント、名前空間ファサード、CLI サブプロセス、コンポーネント専用のプラグインローダーは使用しません。
コマンドはホストのグローバルなプラグインコマンド空間に登録されます。
ホストに既存の `Split_string_Ex` コマンドやプラグイン ID 20371 がないか確認してください。
クリーンなテスト環境での確認は、任意のインストール環境での一意性を保証するものではありません。

## API

マニフェストのシグネチャ: **`Split_string_Ex(&T;&T;&L;&J):C`**。

```4d
$parts:=Split_string_Ex($text; $separator)
$parts:=Split_string_Ex($text; $separator; $nativeOptions)
$parts:=Split_string_Ex($text; $separator; $nativeOptions; $extensions)
```

最初の 3 引数は、**本書に記載したリソース制限の範囲内で**ネイティブの `Split string` の
セマンティクスを維持します。Text の区切り文字は文字列全体をリテラルとして扱い、
パターンや文字のリストとしては扱いません。空の区切り文字はネイティブの UTF-16 コード単位の
動作を維持し、書記素分割にはなりません。ネイティブフラグの値は変わりません。
`sk ignore empty strings` = 1、`sk trim spaces` = 2、両方 = 3 です。

第 3・第 4 引数のオプションは省略できます。確認した 20.7 コンパイラーでは、プラグイン引数の省略時に
参考警告 533.4 が出ますが、コンパイルは成功します。コンパイル済みコードで実際に省略した呼び出しも
検証しています。末尾の Variant は同じようには動作しないため、第 4 引数は意図的に Variant ではなく
Object にしています。区切り文字の Collection は必ずその Object **の中に**渡し、
第 4 引数に直接渡さないでください。

コンパイル済みコードでは、ホストは第 4 引数への Collection の直接指定を拒否します。
インタープリターモードでは、この誤った構造型をプラグインに渡す前に null Object 参照へ
変換する場合があり、省略と区別できなくなります。サポートするのは Object または Null のみです。
4D が既に変換してしまった型をプラグインが復元することはできません。

**成功時は、正当な空の Collection も含め、実際の Collection を返します。
失敗時は Null のみを返します。** `.length` の参照や反復処理の前に必ず確認してください。

```4d
$parts:=Split_string_Ex($text; ","; 0; {mode: "regex"})
If ($parts=Null)
    // Handle failure in the caller.
Else
    // Use the Collection, which may legitimately be empty.
End if
```

最終エラーを取得するコマンドや状態、診断用 Object、オプションの書き換えはなく、
`ON ERR CALL` の呼び出しも保証しません。この意図的に単純な契約では、不正なオプション・パターン、
リソース枯渇、ICU データの欠落、ネイティブ処理の失敗を区別できません。
C++ 例外はプラグイン境界で捕捉し、外へ伝播させません。

### 拡張 Object

| プロパティ | 意味 |
| --- | --- |
| `mode` | `"literal"`（既定）、`"literals"`、`"regex"`、`"graphemes"` |
| `separators` | 空でない Text 区切り文字の Collection。`mode` がなければリストモードを選択 |
| `maxSplits` | 非負整数。最大 N 個の区切り文字を消費し、残り全体を保持 |
| `regexFlags` | 明示的な Boolean の照合フラグを指定する Object。正規表現モード専用 |
| `limits` | 後述する有限のリソース上限を引き下げる Object |

未知のキー、不正なメンバー型、矛盾する設定、上限の引き上げは Null を返します。
第 4 引数が空の Object または Null ならネイティブの動作を維持します。
拡張モードが受け付けるネイティブフラグの組み合わせは 0/1/2/3 のみです。

### リテラル区切り文字リストと分割回数制限

リストモードでは第 2 引数の Text を空にし、Object 内の Collection で区切り文字を指定します。
**最も早い出現位置**、次に**最長の一致区切り文字**、それでも同順位なら
Collection 内の順序で選択します。
空のメンバーは不正です。空の Collection は元の文字列を分割せずに返します。

```4d
$parts:=Split_string_Ex("a---b::c"; ""; 0; {separators: New collection("-"; "---"; "::")})
// ["a","b","c"]

$parts:=Split_string_Ex("a,b,c"; ","; 0; {maxSplits: 1})
// ["a","b,c"], never ["a","b"] with the remainder discarded
```

`maxSplits:0` は、明示的に指定したトリミングや空文字列除外を行う前の段階で、
元の文字列を分割せずに返します。入力が空でも 1 個の空フィールドを含みます。
この拡張を明示しなければ、空入力・空区切り文字に対するネイティブの動作は変わりません。

### 正規表現

第 2 引数がパターンになるのは `mode:"regex"` を指定した場合**だけ**です。
M1 では区切り文字とキャプチャグループを結果に含めません。

```4d
$names:=Split_string_Ex("Bois-Joli / Morne-à-l’eau"; "\\s*/\\s*"; 0; {mode: "regex"})
// ["Bois-Joli","Morne-à-l’eau"]

$tokens:=Split_string_Ex("Bois-Joli Morne-à-l’eau"; "[-’\\s]+"; 0; {mode: "regex"})
// ["Bois","Joli","Morne","à","l","eau"]
```

`regexFlags` の Boolean キーは `caseInsensitive`、`multiline`、`dotAll`、`comments`、
`unicodeWords`、`unixLines` です。それ以外のキーや Boolean 以外の値は失敗になります。
未対応の正準等価フラグは公開していません。

空パターンなどのゼロ幅一致では Unicode コードポイント単位で安全に前進し、
出力用の別カーソルで元のデータを保持します。先頭・末尾の空フィールドは、
ネイティブオプションで除外を指定しない限り保持されます。
`maxSplits` はゼロ幅一致を含め、一致した区切り文字の数を数えます。
残りは、指定されたトリミングや空文字列除外を行う前にはそのまま保持されます。

### 書記素

第 2 引数を空にして、明示的に選択してください。

```4d
$clusters:=Split_string_Ex($text; ""; 0; {mode: "graphemes"})
```

固定バージョンの ICU の文字境界を使い、拡張書記素クラスタを実装しています。
サロゲートペア、分解されたアクセント付き文字、ZWJ 絵文字、肌色修飾、
地域指示記号による旗、CRLF シーケンスを一まとまりとして保持します。
空入力は空の Collection を返します。正規化はせず、結果は元の部分文字列です。
指定がある場合にのみ、フィールドごとにネイティブのトリミングを行い、次に空文字列を除外します。
書記素モードでは `maxSplits`、区切り文字リスト、正規表現フラグは不正です。

ネイティブ呼び出しと拡張フィールドには、実際のホストのトリミング・空文字列除外規則を使用します。
ASCII や Unicode の空白文字に関する推測で近似していません。
内部の範囲は 0 始まりの UTF-16 範囲で、確認したホストの 1 始まりの `Substring` 位置へ変換します。
M1 ではトークンのオフセットを公開していません。
コード単位、コードポイント、書記素クラスタは相互に置き換えられるものではありません。

## リソース制御

上限は引き下げることだけができ、すべて正整数で指定します。

| `limits` キー | ハード上限 |
| --- | ---: |
| `maxInputUnits` | 16,777,216 UTF-16 コード単位（第 2 引数の Text にも適用） |
| `maxPatternUnits` | 65,536 UTF-16 コード単位 |
| `maxItems` | 100,000 個の候補フィールド |
| `maxOutputUnits` | 候補フィールド全体で 33,554,432 UTF-16 コード単位 |
| `regexSteps` | 1,000 ICU 処理制限単位 |
| `regexStackBytes` | ICU のバックトラッキング用ヒープ領域 8,388,608 バイト |
| `operationBudgetMs` | 協調的にチェックする合計処理予算 5,000 ms |

リストにはさらに、区切り文字数 256 個以下、区切り文字の合計 65,536 コード単位以下の制限があります。
`maxSplits` は非負の 32 ビット整数に収まる必要があります。
候補に対する制限は、トリミングと空文字列除外の**前**に適用します。
そのため、除外後の最終 Collection が小さくなる場合でも呼び出しが失敗することがあります。

ICU 処理制限単位はエンジンの作業量であり、**実時間のミリ秒を保証するものではありません**。
合計予算のチェックは処理ステップの間に行います。単一のホストコマンド、
パターンのコンパイル、ブロック中のネイティブ呼び出しを中断することはできません。
プロセス分離や実時間の厳密なタイムアウトではありません。

## ビルドと検証

CMake 3.24 以降、C++17 コンパイラー、スクリプト用に Python 3.12 以降が必要です。
依存関係は [`dependencies.lock.json`](dependencies.lock.json) で変更不能な参照と
チェックサムにより固定しています。パッケージマネージャー、外部ランタイムプロセス、
ホストの ICU は不要です。

```sh
cmake -S . -B build/universal -DCMAKE_BUILD_TYPE=Release \
  '-DCMAKE_OSX_ARCHITECTURES=arm64;x86_64' -DCMAKE_OSX_DEPLOYMENT_TARGET=12.0
cmake --build build/universal --parallel 2
ctest --test-dir build/universal --output-on-failure
python3 -m unittest discover -s tests/python -v
python3 scripts/package.py --build-dir build/universal --output dist/Splitter-macos-universal.zip
python3 scripts/unpack.py dist/Splitter-macos-universal.zip build/unpacked
python3 scripts/test_m1.py --tool4d /path/to/tool4d.app/Contents/MacOS/tool4d \
  --plugin build/unpacked/Splitter.bundle --report build/host-report.json
```

4D 21 以降のホストでは、`--preemptive` を追加すると、コンパイル済みの 8 プロセスによる
ストレスチェックと `Process info` による実際の実行モードの確認を必須にできます。
このフラグがなければ、レポートにはプリエンプティブチェックを未実行と明記します。
ベースラインの 20.7 テスト環境には、これらの新しいコマンドを使うテストメソッドを含めません。

Windows x64 では `cmake -S . -B build -A x64` を実行し、続けて
`cmake --build build --config Release` と `ctest --test-dir build -C Release` を実行します。
`dumpbin` が使えるよう、パッケージ作成は MSVC 開発者環境で実行してください。
静的 CRT と ICU のコードは内部に留め、SDK のエントリーポイントだけをエクスポートします。

パッケージ作成ツールは再ビルドし、アーキテクチャ、外部依存、エクスポート、
対応データとライセンス通知を確認し、ソース・バイナリのハッシュとツールチェーンの来歴を記録します。
ZIP 展開時にはパス、権限、ファイルハッシュを検証します。
通常のビルドパッケージは未署名です。ローカルファイルまたは Actions アーティファクトであり、
自動的に公開されるリリースではありません。手動で公開した v0.1.0 のダウンロードは
[インストール](#インストール)に記載しています。

`scripts/fetch_host.py` は、公開ホストを**新しい隔離ディレクトリ**へ復元し、
アーカイブの SHA-256 とホストバージョンの両方を
[`tests/tool4d.lock.json`](tests/tool4d.lock.json) と照合します。
ダウンロード URL の内容は変更され得ますが、チェックサムが変われば失敗し、
新しいホストを黙って受け入れることはありません。任意指定の `--cache-dir` はアーカイブだけを
キャッシュし、復元のたびにチェックサムを検証します。ホスト自体は Splitter に同梱しません。
macOS では、固定したバンドルの plist でバージョンを特定します。
ホステッドランナー上で 21.1 の `--version` コマンドがバージョンを表示した後にクラッシュしたためです。
メタデータの検証だけで実行時の互換性が確認できるわけでは**ありません**。
実際のソース実行・コンパイル済みホスト実行が正常終了し、すべてのアサーションに合格する必要があります。

[`native.yml`](.github/workflows/native.yml) は macOS ユニバーサルパッケージをビルドし、
ネイティブ arm64 とネイティブ Intel のホストで確認し、Windows x64 のビルドとテストも行います。
Intel ジョブは arm64 ジョブで生成した**同じユニバーサルパッケージ**を確認します。
加えて、ネイティブ Intel ツールチェーンでも独立してビルドとテストを行います。
別の macOS 26 arm64 ジョブでは、固定した 21.1 上の実際のコンパイル済みプリエンプティブ
8 プロセスで同じパッケージを確認します。3 つのビルドプラットフォームすべてで、
固定した 20.7 のインタープリター実行とコンパイル済み実行の動作を確認します。
依存関係のキャッシュに含むのはチェックサム検証済みのソース・ホストアーカイブであり、
コンパイル済みライブラリや認証情報ではありません。
ビルド・署名の Actions は変更不能なリビジョンと読み取り専用権限を使用し、通常のビルドには署名シークレットを渡しません。
ビルドはプルリクエストと main へのプッシュで実行し、フィーチャーブランチへのプッシュで重複実行しません。
署名とリリース公開は、別途手動実行する **Build** パイプラインだけが行います。
プッシュ・PR の検証では行いません。
生成パッケージ、ホストのインストール、継続的な CI の検証結果は、Git 管理対象外の `build/`・`dist/`
または Actions アーティファクトに保存します。リポジトリに記録した小さな JSON レポートは、
元の歴史的な来歴を維持しています。

### バージョンの準備

**main** から **Bump version**（[`bump-version.yml`](.github/workflows/bump-version.yml)）
を手動実行し、`patch`（既定）・`minor`・`major` を選択します。
`CMakeLists.txt` の厳密な `X.Y.Z` 形式を検証し、`cmake/Info.plist` の
2 つのバンドルバージョンと `scripts/package.py` のパッケージ来歴バージョンが
一致することを要求します。4 フィールドを一緒に更新し、公開済みダウンロードのリンクや
過去の検証結果は変更しません。更新先の `vX.Y.Z` タグが存在すれば失敗します。
同時実行を直列化し、強制プッシュせず main にコミット・プッシュします。
`contents: write` 権限の `GITHUB_TOKEN` のみを使用するため、
リポジトリ・ブランチのルールで bot のプッシュを許可する必要があります。
PAT や追加シークレットは不要です。

バージョン更新では**タグ・ビルド・リリースを作成しません**。
`GITHUB_TOKEN` によるプッシュでは main プッシュ用ビルドが起動しないため、
更新後の main コミットで **Build**
（[`build.yml`](.github/workflows/build.yml)）を別途手動実行してください。
その 1 回の実行で、すべてのビルド・テスト・署名・公証・リリース公開を行います。
実行 ID のコピーや、2 回目の署名ワークフローの手動実行は不要です。
古いコミットからの更新でプッシュが拒否された場合は、最新の main から再実行してください。

### ビルド・署名・リリース

バージョン更新後、Actions → **Build** → **Run workflow** で **main** を選び、
1 回実行します。既存のバージョンタグがあれば失敗します。
再利用可能な [`native.yml`](.github/workflows/native.yml) で両プラットフォームを
ビルド・検証し、**すべてのネイティブ・実ホスト検証に成功した後だけ**
[`sign-macos.yml`](.github/workflows/sign-macos.yml) を呼び出します。
同じコミット・同じ実行の成果物を使用します。ネイティブジョブは読み取り専用権限で、
署名シークレットは受け取りません。署名ジョブだけに既存の 6 つの署名シークレットを渡します。
認証情報の不足、署名または公証の失敗時には実行を失敗させ、公開しません。

最後の独立したジョブでパッケージハッシュ、ソース・実行の来歴、公証の Accepted を確認し、
手動実行時のコミットに `vX.Y.Z` タグを作成して GitHub リリースを公開します。
添付ファイルは署名済み macOS ZIP/DMG、未署名 Windows x64 ZIP、
外部の `signing-provenance.json` と `SHA256SUMS` です。
このジョブだけに `contents: write` を付与します。`GITHUB_TOKEN` を直接使用し、
PAT やタグによる別ワークフローの起動は不要です。
リポジトリのタグルールでバージョンタグの作成を許可する必要があります。
既存のタグ・リリースは置き換えません。タグ作成後に公開が失敗した場合は、
失敗した実行を確認してそのリリースを手動で完了してください。
Build の再実行では、既存タグを意図的に拒否します。

署名済み出力と診断ログは Actions アーティファクトにも保存します。
DMG には公証チケットをステープルしますが、ZIP にはしません。
変更しない内部のビルドマニフェストは未署名入力を記述しています。
署名済み ZIP は意図的に未署名専用の `unpack.py` 検証に失敗するため、
代わりに外部の署名来歴と macOS の署名で検証する必要があります。

必要なリポジトリシークレット名は `APPLE_DEVELOPER_ID_CERTIFICATE`、
`APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`、`KEYCHAIN_PASSWORD`、
`NOTARYTOOL_APPLE_ID`、`NOTARYTOOL_PASSWORD`、`NOTARYTOOL_TEAM_ID` です。
ローカルのシークレット設定ヘルパーを実行するのはユーザー本人だけです。
通常のプッシュ・PR のビルド・テスト CI はこれらのシークレットに依存しません。
署名・公証の成立には、実際の認証情報を使った実行の成功が必要です。
[v0.1.0 の署名実行](https://github.com/miyako/4d-plugin-splitter/actions/runs/42151065472)は、
手動公開の前に両方の公証が Accepted となり成功しました。

### 検証結果とサポート範囲の境界

互換性の目標は **4D 20.7 LTS 以降**、macOS ユニバーサル arm64/x86_64、
Windows x64 です。macOS バイナリのターゲットは 12.0 以降です。
以後のすべての 4D・OS リリースに対する包括的な保証ではありません。
最小実行環境の macOS 12.0 と GUI ワークフローは検証していません。
下表は過去のローカル実行結果を維持したものであり、
[v0.1.0](https://github.com/miyako/4d-plugin-splitter/releases/tag/v0.1.0) にまとめた、
その後のリリース検証結果ではありません。

| macOS 26.7 上で確認したホスト | 実行方式 | ソース実行 / コンパイル済み実行 |
| --- | --- | --- |
| [20.7 build 20.101905, arm64](tests/evidence/m1-macos-arm64-20.7.json) | ネイティブ | 各モードで 1,294 アサーションに合格 |
| [21.1 build 21.100468, arm64](tests/evidence/m1-macos-arm64-21.1.json) | ネイティブ | 各モードで 1,294 アサーションに合格 |
| [20.7 build 20.101905, x86_64](tests/evidence/m1-macos-x86_64-translated-20.7.json) | Rosetta 変換 | 各モードで 1,294 アサーションに合格 |
| 物理 Intel / Windows x64 | CI 設定済み、このローカル環境では未実行 | この表では検証済みとしない |

ネイティブコアは arm64 と変換実行の x86_64 スライスで、8 スレッドのストレステストを含む
31,185 チェックに合格しました。変換実行はネイティブ Intel の検証ではありません。
リモートプラットフォームの結果とダウンロード可能な検証資料は
[native ワークフローの実行一覧](https://github.com/miyako/4d-plugin-splitter/actions/workflows/native.yml)にあります。
追加の観測結果を裏付けるのは、完了して成功したジョブだけです。

ホストランナーは、実際のインタープリター実行・コンパイル済み実行、各モード 1,248 ケースでの
ネイティブ互換性、拡張 Unicode・正規表現・リスト・エラー・制限のケース、
所有権処理の反復確認、ホスト ICU へのフォールバックを行わないデータ欠落・切り詰め時の明示的な失敗を検証します。
ソース実行・コンパイル済み実行の区別を起動フラグだけから推定することはありません。
製品用マニフェストはユーザーの明示的な要求により **`threadSafe:true`** を有効にしています。
この宣言はプリエンプティブ使用を許可しますが、それ自体がブリッジの安全性の証明にはなりません。
上表のレポートは、以前の `threadSafe:false` パッケージの来歴を維持しています。
`--preemptive` を指定すると、ホストランナーはさらにコンパイル済みプリエンプティブ 8 プロセスを確認し、
実際の実行モードを検証して、4 つすべての分割モード、失敗の分離、
ICU の初回使用時の並行初期化を実行します。
有効化後のパッケージの新しいレポートには、
[ネイティブ arm64 20.7](tests/evidence/m1-threadsafe-macos-arm64-20.7.json) と
[ネイティブ arm64 21.1](tests/evidence/m1-threadsafe-macos-arm64-21.1.json) で、
各モードのソース実行とコンパイル済み実行それぞれ 1,294 アサーションを記録しています。
21.1 ではさらに、実行時にプリエンプティブであることを確認した 8 プロセスで
9,600 アサーションに合格しました。20.7 の実行ではプリエンプティブ実行を検証して**いません**。
そのコンパイラーは、観測に使う新しい `Process info` に対応していないためです。
この限定的な macOS の検証結果は、一般的なブリッジ安全性の認証ではありません。
これらのローカルレポートは Windows、ネイティブ Intel、20.7 のプリエンプティブ対応を裏付けるものではありません。
リモートプラットフォームの観測については、対応する CI の検証結果を参照してください。

以前の SDK 調査は `tests/evidence/` に歴史的な観測結果として残しており、現在の阻害要因ではありません。
Variant の省略は失敗し、型指定した Longint と Object の省略は警告のみでコンパイルに成功し、
SDK のアサーションはホストのエラーハンドラーを呼び出しません。
過去の調査用プローブは `-DSPLITTER_BUILD_PROBES=ON` による明示的な選択で有効にし、
`build/probes/` 以下で別にビルドします。製品用バンドルには登録しません。

## 後続のツールキット

次のマイルストーンでも合意した範囲を維持します。構造化した位置情報と区切り文字・キャプチャの保持、
CRLF/LF/CR と末尾空要素ポリシーに対応する行処理、partition/rpartition と scan/extract、
厳密な増分 CSV/TSV **読み書き**、テキストを保持するフィールド、
明示的な方言・ヘッダー設定と任意の数式対策、ロケールに対応する単語・文と文書化した識別子規則、
制限付きでライフタイムが安全なハンドルを使う再利用可能なコンパイル済みパターンとバッチ API が対象です。
CSV ライブラリのライセンスと詳細な CSV 診断は、そのマイルストーンで決定します。
語幹処理、暗黙の型変換、性能、リリース準備の完了、未実行プラットフォームに関する主張はしていません。
