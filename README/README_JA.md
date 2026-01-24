# PriceEstimated 📈

[English](./README.md) | [简体中文](./README/README_ZH.md) | [日本語]

精密な価格推定と財務データ処理のための強力な株式分析モデルの統合ツール。

---

## はじめに
PriceEstimatedは、複数の株式評価モデルを統合するために設計されたPythonベースの計量分析フレームワークです。生データの取得から最終的な価格推定までのパイプラインを簡素化し、モジュール設計と厳密な計算により高精度を実現します。

## 主な機能
* **マルチモデル統合**: DCF法や相対評価法などの様々な評価手法を一つのインターフェースに統合。
* **データ管理**: `data_manager.py` を介して `financial_data.json` やローカルCSVデータセットを自動処理。
* **高度な設定**: ハイパーパラメータやモデルの重み付けを `config.md` で簡単に管理可能。
* **自動ワークフロー**: GitHub Actionsによる継続的インテグレーションとユニットテストを内蔵。

## インストール
1.  **リポジトリのクローン**:
    ```bash
    git clone [https://github.com/Seanyim/PriceEstimated.git](https://github.com/Seanyim/PriceEstimated.git)
    cd PriceEstimated
    ```
2.  **環境構築**:
    ```bash
    pip install -r requirements.txt
    ```

## 使い方
主要な分析を実行し、価格推定を生成するには：
```bash
python main.py