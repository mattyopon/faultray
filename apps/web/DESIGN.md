# FaultRay Design System

FaultRayのデザインは **Stripe（信頼感・B2B SaaS）** と **Linear（ミニマル・開発ツール）** を参考にする。

## 参考デザインシステム

以下の2ファイルを参照してUIを構築すること:
- `design/stripe-DESIGN.md` — 料金ページ、CTA、信頼感の演出
- `design/linear-DESIGN.md` — ダッシュボード、ミニマルUI、開発者向けの硬質感

## FaultRay固有のルール

### ターゲット
日本の中小IT企業のCTO/開発責任者。「SRE採用に年1,000万かける前にFaultRayで月4.5万」が訴求軸。

### トーン
- Stripeの「信頼感・プロフェッショナル」を基調
- Linearの「余計なものを削ぎ落とす」ミニマリズム
- 日本語ページでは「カオスエンジニアリング」ではなく「障害リスク診断」「システム健康診断」と表現

### カラー
現在のCSS変数を維持（Findy風ライトテーマ適用済み）:
- Primary: `#055ec1` (Blue)
- Background: `#ffffff` / `#f9fafb` / `#f2f3f5`
- Text: `#1d1d1f` / `#6e6e73`
- Accent: Stripeのgradient感は控えめに。Linearのモノクロ+1色を優先

### やってはいけないこと
- グロー/ネオン効果
- 3Dアニメーション
- 過剰なgradient
- ダークテーマをLPに使う（ダッシュボードはダーク可）
