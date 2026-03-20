# TechRxiv (IEEE) 投稿ガイド — FaultRay

> **作成日**: 2026-03-21
> **ステータス**: TechRxiv は 2026年3月9日よりプラットフォーム移行のため投稿受付を一時停止中。
> 新プラットフォームへの移行完了後（2026年4月予定）に投稿可能になる見込み。
> 既存コンテンツは引き続きアクセス可能で、DOIも有効。

---

## 1. TechRxiv とは

TechRxiv は IEEE が運営する、電気工学・コンピュータサイエンス・関連技術分野向けのオープンなプレプリントサーバーである。査読前の研究成果を迅速に公開し、DOI を付与することで引用可能な学術記録として残せる。Figshare をバックエンドに使用し、CrossRef・Google Scholar によるインデキシングに対応している。

- 公式サイト: https://www.techrxiv.org/
- IEEE 紹介ページ: https://www.ieee.org/publications/techrxiv.html

---

## 2. 現在の投稿状況（重要）

| 項目 | 内容 |
|------|------|
| 投稿受付 | **一時停止中**（2026年3月9日〜） |
| 理由 | Authorea から新プラットフォームへの移行 |
| 移行完了予定 | 2026年4月 |
| 既存コンテンツ | 引き続きアクセス可能、DOIは有効 |
| 移行後の注意 | DOI 付きで公開済みのプレプリントのみ新プラットフォームへ移行される |

**対応**: 投稿再開の通知を受け取るために https://www.techrxiv.org/ を定期的に確認すること。

---

## 3. 事前準備チェックリスト

投稿前に以下をすべて準備する。

- [ ] **ORCID ID の取得** — アカウント登録に必須。https://orcid.org/ で無料登録可能
- [ ] **PDF ファイルの最終確認** — `/home/user/repos/faultray/paper/faultray-paper.pdf`
- [ ] **メタデータの確認** — 下記セクション 5 を参照
- [ ] **ライセンスの選択** — 下記セクション 6 を参照
- [ ] **GitHub URL の確認** — https://github.com/mattyopon/faultray

---

## 4. アカウント登録手順

1. https://www.techrxiv.org/ にアクセスする
2. "Sign Up" または "Register" をクリック
3. 以下の情報を入力する:
   - 氏名: Yutaro Maeda
   - メールアドレス: ymaeda.it@gmail.com
   - ORCID ID: （事前に取得しておくこと）
4. メール認証を完了する
5. ログイン後、投稿ページへ進む

---

## 5. 投稿手順（投稿再開後）

### ステップ 1: カテゴリ選択

投稿開始時に、論文のトピックに最も適したカテゴリを選択する。

**推奨カテゴリ**: Computing and Processing（コンピューティング・処理）
（または "Systems Science" / "Information Theory" も候補）

### ステップ 2: ファイルアップロード

- **メインファイル（必須）**: `faultray-paper.pdf`
  - パス: `/home/user/repos/faultray/paper/faultray-paper.pdf`
  - 形式: **PDF が推奨**（TechRxiv はすべての形式を受け付けるが、PDF が標準）
  - `.tex` ソースファイルは補足資料として追加アップロード可能
- **補足資料（任意）**: `faultray-paper.tex` を追加ファイルとしてアップロード可能

> **ファイル形式について**: TechRxiv はあらゆるファイル形式を受け付け、ブラウザでのプレビューを試みる。arXiv と異なり、PDF のみの投稿で問題ない。LaTeX ソースの提出は必須ではない。

### ステップ 3: メタデータ入力

以下のメタデータをそのままコピーして使用すること。

---

#### タイトル（Title）

```
FaultRay: In-Memory Infrastructure Resilience Simulation with Graph-Based Cascade Analysis, Multi-Layer Availability Limits, and AI Agent Failure Modeling
```

#### 著者（Authors）

| フィールド | 値 |
|-----------|-----|
| 氏名 | Yutaro Maeda |
| 所属 | Independent Researcher |
| 所在地 | Chigasaki, Japan |
| メール | ymaeda.it@gmail.com |
| ORCID | （登録後に取得したID） |

#### アブストラクト（Abstract）

```
Modern distributed systems and AI agent architectures lack tools that simulate infrastructure failures entirely in memory while simultaneously modeling the failure modes unique to large language model (LLM)-based agents. We present FaultRay, a zero-risk chaos engineering platform that introduces three innovations: (1) a graph-based cascade propagation engine formalized as a Labeled Transition System (LTS) over a 4-tuple state space, enabling deterministic replay and formal correctness proofs; (2) an N-layer availability limit model that decomposes a system's theoretical availability ceiling into five independent layers---hardware, software, theoretical physics, operational, and external SLA; and (3) the first cross-layer failure model for AI agents that quantifies hallucination probability as a function of infrastructure health, data source availability, and agent chain composition. We validate FaultRay against 18 real-world cloud incidents spanning 2017--2023 (AWS, GCP, Azure, Meta, Cloudflare), achieving an average F1 = 1.000 for cascade path prediction and severity accuracy of 0.819. The open-source implementation comprises 441 source files, 29,640 tests, and over 100 simulation engines, and is available on PyPI. To our knowledge, FaultRay is the first system to bridge infrastructure resilience simulation and AI agent reliability analysis within a single, formally verified framework.
```

#### キーワード（Keywords）

```
chaos engineering
infrastructure resilience
fault injection
availability modeling
AI agent reliability
graph-based simulation
labeled transition system
```

#### 関連リンク（Related Content / Links）

```
GitHub Repository: https://github.com/mattyopon/faultray
PyPI Package: https://pypi.org/project/faultray/
```

#### 資金援助（Funding）

```
（該当なし / None — independent research, no external funding）
```

---

### ステップ 4: ライセンス選択

**推奨**: **CC BY 4.0 (Attribution 4.0 International)**

| ライセンス | 説明 | 推奨度 |
|-----------|------|--------|
| CC BY 4.0 | 出典明記のみで自由に利用・改変・商用利用可能 | **推奨** |
| CC BY-SA 4.0 | 出典明記 + 同じライセンスでの再配布が必要 | 可 |
| CC BY-NC-SA 4.0 | 非商用に限定 | 商用利用を制限したい場合 |
| CC0 1.0 | パブリックドメイン（権利放棄） | 最大限のオープン性を求める場合 |

> IEEE との将来的なジャーナル投稿を見据えると **CC BY 4.0** が最も柔軟。

### ステップ 5: 投稿送信

すべての入力が完了したら "Submit" ボタンをクリックする。

---

## 6. 審査プロセスとタイムライン

| フェーズ | 所要時間 | 内容 |
|---------|---------|------|
| 確認メール | 即時 | 投稿受付を通知するメールが届く |
| モデレーション審査 | **4営業日以内** | 盗用・不適切コンテンツ・スコープ適合性の確認 |
| 公開 | 審査完了後 | DOI 付きでプレプリントが公開される |
| DOI 発行 | 公開と同時 | CrossRef 経由で登録、Google Scholar にインデキシング |

**審査基準**:
- 英語で書かれていること
- TechRxiv のスコープ内の未公開技術コンテンツであること
- 攻撃的・盗用コンテンツを含まないこと
- 既発表素材を使用する場合は再利用許可があること

---

## 7. DOI について

- **全プレプリントに DOI が付与される**（例: `10.36227/techrxiv.XXXXXXXX.vX`）
- CrossRef に登録され、Google Scholar・Web of Science でインデキシング可能
- 改訂版は同じ DOI + バージョン番号で管理される（例: `.v1`, `.v2`）
- DOI は恒久的に有効（プラットフォーム移行後も継続）

---

## 8. 投稿後の対応

1. **DOI をメモする** — README.md、論文本文、PyPI ページに追記
2. **GitHub リポジトリを更新する** — README に TechRxiv のリンクと DOI を追加
3. **arXiv との関係** — TechRxiv 投稿は arXiv 投稿と並行して行える（どちらかが先でも問題ない）
4. **改訂版の投稿** — 論文を更新した場合は同じ DOI で新バージョンとしてアップロード可能

---

## 9. よくある質問

**Q: LaTeX ソース（.tex）は提出する必要があるか？**
A: 不要。PDF のみで投稿可能。.tex を補足資料として追加してもよい。

**Q: arXiv と TechRxiv に両方投稿してよいか？**
A: 可能。TechRxiv は IEEE の技術分野向けに特化しており、arXiv と併用する研究者も多い。投稿する各サービスの規約を確認すること。

**Q: IEEE ジャーナルへの投稿に影響するか？**
A: TechRxiv はプレプリントサーバーであり、多くの IEEE ジャーナルはプレプリント投稿を問題としない。投稿予定のジャーナルのポリシーを事前に確認すること。

**Q: 投稿の取り下げは可能か？**
A: 公開後の取り下げは原則として行わない。ただし大きな誤りがある場合は TechRxiv 運営に連絡することで対応可能な場合がある。

**Q: 共著者なしで投稿可能か？**
A: 可能。単著での投稿に対応している。

---

## 10. 参考リンク

- [TechRxiv 公式サイト](https://www.techrxiv.org/)
- [TechRxiv 投稿ガイドライン](https://techrxiv.figshare.com/f/submission-guidelines)
- [TechRxiv FAQ](https://techrxiv.figshare.com/f/faqs)
- [IEEE TechRxiv 紹介ページ](https://www.ieee.org/publications/techrxiv.html)
- [ORCID 登録](https://orcid.org/)
- [Directory of Open Access Preprint Repositories: TechRxiv](https://doapr.coar-repositories.org/repositories/techrxiv/)

---

## 付録: FaultRay 論文ファイル一覧

| ファイル | パス | 用途 |
|---------|------|------|
| PDF | `/home/user/repos/faultray/paper/faultray-paper.pdf` | メイン投稿ファイル |
| LaTeX ソース | `/home/user/repos/faultray/paper/faultray-paper.tex` | 補足資料（任意） |
| GitHub | https://github.com/mattyopon/faultray | 関連リンクとして記載 |
