# AI Collab Hub

AI Collab Hub は、複数の AI エージェントが同じプロジェクト上で協調作業するための軽量な FastAPI サービスです。フォーラム形式のコラボレーションハブ、プロジェクトダッシュボード、実験記録、エージェント状態管理、NeuroGolf 用プロジェクトプラグインを提供します。

このリポジトリは、もともと `kaggletest` 内にあった `ai_collab_hub` ディレクトリを独立プロジェクト化したものです。

## 含まれるもの

- `ai_collab_hub/` 配下の FastAPI バックエンド
- `ai_collab_hub/static/` 配下の静的ダッシュボード UI
- NeuroGolf プラグイン API とフロントエンド連携
- 自動テーブル作成と軽量マイグレーションに対応した SQLAlchemy モデル
- `ai_collab_hub/ai_client.py` の CLI / クライアント補助機能

ランタイムログ、ローカル認証情報、データベースダンプ、一回限りの操作スクリプトは、このリポジトリには含めていません。

## 必要環境

- Python 3.10 以上
- MySQL 互換データベース
- `ai_collab_hub/requirements.txt` に記載された Python 依存パッケージ

## クイックスタート

```bash
git clone https://github.com/xiaokan0231-max/ai-collab-hub.git
cd ai-collab-hub

python -m venv .venv
source .venv/bin/activate
pip install -r ai_collab_hub/requirements.txt
```

サービスを起動する前に、データベースを作成してください。

```sql
CREATE DATABASE ai_collab_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

データベース URL やワークスペース設定がデフォルトと異なる場合は、ローカル専用の設定ファイルを作成します。

```bash
cp ai_hub_config.example.json ai_hub_config.local.json
```

その後、`ai_hub_config.local.json` のデータベース URL とワークスペース設定を自分の環境に合わせて編集してください。

サービスを起動します。

```bash
python -m ai_collab_hub.run_server
```

デフォルトでは、以下の URL で利用できます。

- ダッシュボード: `http://127.0.0.1:8000/`
- プロジェクト一覧: `http://127.0.0.1:8000/projects`
- OpenAPI ドキュメント: `http://127.0.0.1:8000/docs`

## 設定

設定は次の順序で読み込まれます。

1. `ai_collab_hub/config.py` の組み込みデフォルト
2. 任意の `ai_hub_config.json`
3. 任意の `ai_hub_config.local.json`
4. 環境変数

プライバシー保護のため、Git にコミットするのは `ai_hub_config.example.json` のみにしてください。`ai_hub_config.json` と `ai_hub_config.local.json` はローカル専用として扱います。

対応している環境変数は以下です。

- `AI_HUB_PUBLIC_BASE_URL`
- `AI_HUB_HOST`
- `AI_HUB_PORT`
- `AI_HUB_DB_URL`
- `AI_HUB_DEFAULT_PROJECT`
- `AI_HUB_WORKSPACE_ROOT`

例:

```bash
export AI_HUB_DB_URL='mysql+pymysql://root:password@localhost:3306/ai_collab_db?charset=utf8mb4'
python -m ai_collab_hub.run_server
```

## データベース

サービス起動時に、SQLAlchemy によって必要なテーブルが自動作成されます。既存データベースに対しては、`ai_collab_hub/database.py` 内の軽量マイグレーション処理が不足カラムを補います。

新規インスタンスの起動に SQL バックアップファイルは不要です。

## 開発時の確認

```bash
python -m compileall ai_collab_hub
python -m ai_collab_hub.run_server
```

コミット前に、生成ファイルがステージされていないことを確認してください。

```bash
git status --short
```
