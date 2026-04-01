"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
  Download,
  ArrowRight,
  ChevronDown,
  ChevronRight,
  FileText,
  Rocket,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Inline i18n (extracted from app-dict.ts to reduce chunk size)
 * ============================================================ */

const DORA_DICT = {
  en: {
    title: "DORA Compliance Dashboard",
    subtitle: "Digital Operational Resilience Act — EU regulation for financial institutions",
    loading: "Loading DORA assessment...",
    overallScore: "DORA Compliance",
    compliantControls: "Compliant Controls",
    partialControls: "Partial",
    nonCompliantControls: "Non-Compliant",
    ofTotal: "of {n} controls",
    needsImprovement: "needs improvement",
    requiresRemediation: "requires remediation",
    compliant: "Compliant",
    partial: "Partial",
    nonCompliant: "Non-Compliant",
    pillarOverview: "5 Pillar Overview",
    controlAssessment: "Control Assessment",
    controlId: "Control ID",
    description: "Description",
    statusCol: "Status",
    lastAssessed: "Last Assessed",
    evidence: "Evidence",
    evidenceAvailable: "Evidence",
    noEvidence: "No Evidence",
    showAll: "Show all {n} controls",
    showLess: "Show less",
    pass: "Pass",
    fail: "Fail",
    gapAnalysis: "Gap Analysis",
    gapSubtitle: "Non-compliant controls sorted by severity",
    deadline: "Deadline",
    doraMetricsTitle: "DORA 4 Key Metrics",
    deploymentFrequency: "Deployment Frequency",
    leadTime: "Lead Time for Changes",
    changeFailureRate: "Change Failure Rate",
    mttr: "Mean Time to Recovery",
    benchmark: "Industry Benchmark",
    good: "Good",
    warning: "Warning",
    critical: "Critical",
    evidencePackage: "Evidence Package",
    generateEvidence: "Generate Package",
    evidenceItems: "items",
    evidenceNote: "Evidence packages are formatted for regulatory submission per DORA Article 19. Generated packages include test results, configuration evidence, and attestations.",
    ipoReadinessTitle: "IPO Readiness",
    ipoReadinessDesc: "Going public? FaultRay proves your infrastructure meets the audit requirements investors and regulators demand.",
    ipoCheckDora: "DORA compliance for financial services",
    ipoCheckSoc2: "SOC2 Type II evidence package",
    ipoCheckIso: "ISO27001 control mapping",
    ipoCheckSla: "Availability SLA mathematical proof",
    ipoCheckRunbooks: "Incident response runbooks",
    ipoCheckAudit: "Change management audit trail",
  },
  ja: {
    title: "DORA コンプライアンスダッシュボード",
    subtitle: "Digital Operational Resilience Act — EUの金融機関向け規制",
    loading: "DORAアセスメントを読み込み中...",
    overallScore: "DORA 準拠率",
    compliantControls: "準拠コントロール",
    partialControls: "一部準拠",
    nonCompliantControls: "非準拠",
    ofTotal: "{n} 件中",
    needsImprovement: "改善が必要",
    requiresRemediation: "是正措置が必要",
    compliant: "準拠",
    partial: "一部準拠",
    nonCompliant: "非準拠",
    pillarOverview: "5 Pillar 概要",
    controlAssessment: "コントロールアセスメント",
    controlId: "コントロールID",
    description: "説明",
    statusCol: "ステータス",
    lastAssessed: "最終評価日",
    evidence: "エビデンス",
    evidenceAvailable: "エビデンスあり",
    noEvidence: "エビデンス未整備",
    showAll: "全 {n} 件を表示",
    showLess: "折りたたむ",
    pass: "適合",
    fail: "不適合",
    gapAnalysis: "ギャップ分析",
    gapSubtitle: "重要度順に並べられた非準拠コントロール",
    deadline: "期限",
    doraMetricsTitle: "DORA 4つの主要メトリクス",
    deploymentFrequency: "デプロイ頻度",
    leadTime: "変更のリードタイム",
    changeFailureRate: "変更失敗率",
    mttr: "平均復旧時間",
    benchmark: "業界ベンチマーク",
    good: "良好",
    warning: "警告",
    critical: "重大",
    evidencePackage: "エビデンスパッケージ",
    generateEvidence: "パッケージ生成",
    evidenceItems: "件",
    evidenceNote: "エビデンスパッケージはDORA第19条に基づく規制当局への提出形式に準拠しています。",
    ipoReadinessTitle: "IPO準備",
    ipoReadinessDesc: "上場を検討中ですか？FaultRayは投資家と規制当局が求める監査要件をインフラが満たしていることを証明します。",
    ipoCheckDora: "金融サービス向けDORA準拠",
    ipoCheckSoc2: "SOC2 Type IIエビデンスパッケージ",
    ipoCheckIso: "ISO27001コントロールマッピング",
    ipoCheckSla: "可用性SLAの数学的証明",
    ipoCheckRunbooks: "インシデント対応ランブック",
    ipoCheckAudit: "変更管理監査証跡",
  },
  de: {
    title: "DORA Compliance-Dashboard",
    subtitle: "Digital Operational Resilience Act — EU-Verordnung für Finanzinstitute",
    loading: "DORA-Bewertung wird geladen...",
    overallScore: "DORA-Compliance",
    compliantControls: "Konforme Controls",
    partialControls: "Teilweise",
    nonCompliantControls: "Nicht konform",
    ofTotal: "von {n} Controls",
    needsImprovement: "Verbesserung nötig",
    requiresRemediation: "Abhilfe erforderlich",
    compliant: "Konform",
    partial: "Teilweise",
    nonCompliant: "Nicht konform",
    pillarOverview: "5-Säulen-Übersicht",
    controlAssessment: "Control-Bewertung",
    controlId: "Control-ID",
    description: "Beschreibung",
    statusCol: "Status",
    lastAssessed: "Zuletzt bewertet",
    evidence: "Nachweise",
    evidenceAvailable: "Nachweise",
    noEvidence: "Keine Nachweise",
    showAll: "Alle {n} Controls anzeigen",
    showLess: "Weniger anzeigen",
    pass: "Bestanden",
    fail: "Fehlgeschlagen",
    gapAnalysis: "Lückenanalyse",
    gapSubtitle: "Nicht konforme Controls, nach Schweregrad sortiert",
    deadline: "Frist",
    doraMetricsTitle: "DORA 4 Schlüsselmetriken",
    deploymentFrequency: "Deployment-Häufigkeit",
    leadTime: "Vorlaufzeit für Änderungen",
    changeFailureRate: "Änderungsfehlerrate",
    mttr: "Mittlere Wiederherstellungszeit",
    benchmark: "Branchenbenchmark",
    good: "Gut",
    warning: "Warnung",
    critical: "Kritisch",
    evidencePackage: "Nachweispaket",
    generateEvidence: "Paket erstellen",
    evidenceItems: "Nachweise",
    evidenceNote: "Nachweispakete sind für die behördliche Einreichung gemäß DORA-Artikel 19 formatiert.",
    ipoReadinessTitle: "IPO-Bereitschaft",
    ipoReadinessDesc: "Planen Sie einen Börsengang? FaultRay beweist, dass Ihre Infrastruktur die Anforderungen von Investoren und Regulatoren erfüllt.",
    ipoCheckDora: "DORA-Compliance für Finanzdienstleister",
    ipoCheckSoc2: "SOC2 Typ II Nachweispaket",
    ipoCheckIso: "ISO27001-Kontrollmapping",
    ipoCheckSla: "Mathematischer Verfügbarkeits-SLA-Nachweis",
    ipoCheckRunbooks: "Runbooks für die Incident-Response",
    ipoCheckAudit: "Änderungsmanagement-Prüfpfad",
  },
  fr: {
    title: "Tableau de bord DORA",
    subtitle: "Digital Operational Resilience Act — réglementation UE pour les institutions financières",
    loading: "Chargement de l'évaluation DORA...",
    overallScore: "Conformité DORA",
    compliantControls: "Contrôles conformes",
    partialControls: "Partiels",
    nonCompliantControls: "Non conformes",
    ofTotal: "sur {n} contrôles",
    needsImprovement: "amélioration nécessaire",
    requiresRemediation: "remédiation requise",
    compliant: "Conforme",
    partial: "Partiel",
    nonCompliant: "Non conforme",
    pillarOverview: "Vue d'ensemble des 5 piliers",
    controlAssessment: "Évaluation des contrôles",
    controlId: "ID de contrôle",
    description: "Description",
    statusCol: "Statut",
    lastAssessed: "Dernière évaluation",
    evidence: "Preuves",
    evidenceAvailable: "Preuves",
    noEvidence: "Pas de preuves",
    showAll: "Afficher les {n} contrôles",
    showLess: "Afficher moins",
    pass: "Réussi",
    fail: "Échoué",
    gapAnalysis: "Analyse des écarts",
    gapSubtitle: "Contrôles non conformes triés par gravité",
    deadline: "Échéance",
    doraMetricsTitle: "4 métriques clés DORA",
    deploymentFrequency: "Fréquence de déploiement",
    leadTime: "Délai de mise en œuvre",
    changeFailureRate: "Taux d'échec des changements",
    mttr: "Temps moyen de rétablissement",
    benchmark: "Référence du secteur",
    good: "Bon",
    warning: "Avertissement",
    critical: "Critique",
    evidencePackage: "Package de preuves",
    generateEvidence: "Générer le package",
    evidenceItems: "éléments",
    evidenceNote: "Les packages de preuves sont formatés pour la soumission réglementaire conformément à l'article 19 du DORA.",
    ipoReadinessTitle: "Préparation à l'introduction en bourse",
    ipoReadinessDesc: "Vous envisagez une introduction en bourse ? FaultRay prouve que votre infrastructure répond aux exigences d'audit des investisseurs et des régulateurs.",
    ipoCheckDora: "Conformité DORA pour les services financiers",
    ipoCheckSoc2: "Package de preuves SOC2 Type II",
    ipoCheckIso: "Cartographie des contrôles ISO27001",
    ipoCheckSla: "Preuve mathématique du SLA de disponibilité",
    ipoCheckRunbooks: "Runbooks de réponse aux incidents",
    ipoCheckAudit: "Piste d'audit de gestion des changements",
  },
  zh: {
    title: "DORA 合规仪表盘",
    subtitle: "数字运营弹性法案 — 欧盟金融机构法规",
    loading: "正在加载 DORA 评估...",
    overallScore: "DORA 合规率",
    compliantControls: "合规控制项",
    partialControls: "部分合规",
    nonCompliantControls: "不合规",
    ofTotal: "共 {n} 项",
    needsImprovement: "需要改进",
    requiresRemediation: "需要整改",
    compliant: "合规",
    partial: "部分合规",
    nonCompliant: "不合规",
    pillarOverview: "5 大支柱概览",
    controlAssessment: "控制项评估",
    controlId: "控制项 ID",
    description: "描述",
    statusCol: "状态",
    lastAssessed: "最近评估日期",
    evidence: "证据",
    evidenceAvailable: "有证据",
    noEvidence: "无证据",
    showAll: "显示全部 {n} 项",
    showLess: "收起",
    pass: "通过",
    fail: "未通过",
    gapAnalysis: "差距分析",
    gapSubtitle: "按严重程度排序的不合规控制项",
    deadline: "截止日期",
    doraMetricsTitle: "DORA 4 项关键指标",
    deploymentFrequency: "部署频率",
    leadTime: "变更交付周期",
    changeFailureRate: "变更失败率",
    mttr: "平均恢复时间",
    benchmark: "行业基准",
    good: "良好",
    warning: "警告",
    critical: "严重",
    evidencePackage: "证据包",
    generateEvidence: "生成证据包",
    evidenceItems: "项",
    evidenceNote: "证据包按 DORA 第 19 条的监管提交格式生成。",
    ipoReadinessTitle: "IPO准备",
    ipoReadinessDesc: "计划上市？FaultRay证明您的基础设施满足投资者和监管机构要求的审计标准。",
    ipoCheckDora: "金融服务DORA合规",
    ipoCheckSoc2: "SOC2 Type II证据包",
    ipoCheckIso: "ISO27001控制映射",
    ipoCheckSla: "可用性SLA数学证明",
    ipoCheckRunbooks: "事件响应运行手册",
    ipoCheckAudit: "变更管理审计跟踪",
  },
  ko: {
    title: "DORA 컴플라이언스 대시보드",
    subtitle: "디지털 운영 복원력 법 — EU 금융기관 규정",
    loading: "DORA 평가 로딩 중...",
    overallScore: "DORA 준수율",
    compliantControls: "준수 통제항목",
    partialControls: "부분 준수",
    nonCompliantControls: "미준수",
    ofTotal: "{n}개 중",
    needsImprovement: "개선 필요",
    requiresRemediation: "조치 필요",
    compliant: "준수",
    partial: "부분 준수",
    nonCompliant: "미준수",
    pillarOverview: "5대 기둥 개요",
    controlAssessment: "통제항목 평가",
    controlId: "통제 ID",
    description: "설명",
    statusCol: "상태",
    lastAssessed: "최근 평가일",
    evidence: "증거",
    evidenceAvailable: "증거 있음",
    noEvidence: "증거 없음",
    showAll: "전체 {n}개 보기",
    showLess: "접기",
    pass: "통과",
    fail: "실패",
    gapAnalysis: "갭 분석",
    gapSubtitle: "심각도 순으로 정렬된 미준수 통제항목",
    deadline: "기한",
    doraMetricsTitle: "DORA 4대 핵심 지표",
    deploymentFrequency: "배포 빈도",
    leadTime: "변경 리드타임",
    changeFailureRate: "변경 실패율",
    mttr: "평균 복구 시간",
    benchmark: "업계 기준",
    good: "양호",
    warning: "경고",
    critical: "심각",
    evidencePackage: "증거 패키지",
    generateEvidence: "패키지 생성",
    evidenceItems: "항목",
    evidenceNote: "증거 패키지는 DORA 제19조에 따른 규제 제출 형식으로 생성됩니다.",
    ipoReadinessTitle: "IPO 준비",
    ipoReadinessDesc: "상장을 계획 중이신가요? FaultRay는 귀하의 인프라가 투자자와 규제 기관이 요구하는 감사 요건을 충족함을 증명합니다.",
    ipoCheckDora: "금융 서비스를 위한 DORA 준수",
    ipoCheckSoc2: "SOC2 Type II 증거 패키지",
    ipoCheckIso: "ISO27001 통제 매핑",
    ipoCheckSla: "가용성 SLA 수학적 증명",
    ipoCheckRunbooks: "인시던트 대응 런북",
    ipoCheckAudit: "변경 관리 감사 추적",
  },
  es: {
    title: "Panel de Cumplimiento DORA",
    subtitle: "Ley de Resiliencia Operativa Digital — regulación UE para instituciones financieras",
    loading: "Cargando evaluación DORA...",
    overallScore: "Cumplimiento DORA",
    compliantControls: "Controles conformes",
    partialControls: "Parciales",
    nonCompliantControls: "No conformes",
    ofTotal: "de {n} controles",
    needsImprovement: "necesita mejora",
    requiresRemediation: "requiere remediación",
    compliant: "Conforme",
    partial: "Parcial",
    nonCompliant: "No conforme",
    pillarOverview: "Resumen de los 5 pilares",
    controlAssessment: "Evaluación de controles",
    controlId: "ID de control",
    description: "Descripción",
    statusCol: "Estado",
    lastAssessed: "Última evaluación",
    evidence: "Evidencia",
    evidenceAvailable: "Evidencia",
    noEvidence: "Sin evidencia",
    showAll: "Mostrar los {n} controles",
    showLess: "Mostrar menos",
    pass: "Aprobado",
    fail: "Fallido",
    gapAnalysis: "Análisis de brechas",
    gapSubtitle: "Controles no conformes ordenados por severidad",
    deadline: "Plazo",
    doraMetricsTitle: "4 métricas clave DORA",
    deploymentFrequency: "Frecuencia de despliegue",
    leadTime: "Tiempo de entrega",
    changeFailureRate: "Tasa de fallos en cambios",
    mttr: "Tiempo medio de recuperación",
    benchmark: "Referencia del sector",
    good: "Bueno",
    warning: "Advertencia",
    critical: "Crítico",
    evidencePackage: "Paquete de evidencias",
    generateEvidence: "Generar paquete",
    evidenceItems: "elementos",
    evidenceNote: "Los paquetes de evidencias están formateados para presentación regulatoria según el Artículo 19 de DORA.",
    ipoReadinessTitle: "Preparación para la OPV",
    ipoReadinessDesc: "¿Planea salir a bolsa? FaultRay demuestra que su infraestructura cumple con los requisitos de auditoría que exigen inversores y reguladores.",
    ipoCheckDora: "Cumplimiento DORA para servicios financieros",
    ipoCheckSoc2: "Paquete de evidencias SOC2 Tipo II",
    ipoCheckIso: "Mapeo de controles ISO27001",
    ipoCheckSla: "Prueba matemática del SLA de disponibilidad",
    ipoCheckRunbooks: "Runbooks de respuesta a incidentes",
    ipoCheckAudit: "Registro de auditoría de gestión de cambios",
  },
  pt: {
    title: "Painel de Conformidade DORA",
    subtitle: "Lei de Resiliência Operacional Digital — regulamento UE para instituições financeiras",
    loading: "Carregando avaliação DORA...",
    overallScore: "Conformidade DORA",
    compliantControls: "Controles conformes",
    partialControls: "Parciais",
    nonCompliantControls: "Não conformes",
    ofTotal: "de {n} controles",
    needsImprovement: "precisa de melhoria",
    requiresRemediation: "requer remediação",
    compliant: "Conforme",
    partial: "Parcial",
    nonCompliant: "Não conforme",
    pillarOverview: "Visão geral dos 5 pilares",
    controlAssessment: "Avaliação de controles",
    controlId: "ID do controle",
    description: "Descrição",
    statusCol: "Status",
    lastAssessed: "Última avaliação",
    evidence: "Evidências",
    evidenceAvailable: "Evidências",
    noEvidence: "Sem evidências",
    showAll: "Mostrar todos os {n} controles",
    showLess: "Mostrar menos",
    pass: "Aprovado",
    fail: "Reprovado",
    gapAnalysis: "Análise de lacunas",
    gapSubtitle: "Controles não conformes ordenados por severidade",
    deadline: "Prazo",
    doraMetricsTitle: "4 métricas-chave DORA",
    deploymentFrequency: "Frequência de implantação",
    leadTime: "Tempo de entrega",
    changeFailureRate: "Taxa de falhas em mudanças",
    mttr: "Tempo médio de recuperação",
    benchmark: "Referência do setor",
    good: "Bom",
    warning: "Aviso",
    critical: "Crítico",
    evidencePackage: "Pacote de evidências",
    generateEvidence: "Gerar pacote",
    evidenceItems: "itens",
    evidenceNote: "Os pacotes de evidências são formatados para submissão regulatória conforme o Artigo 19 do DORA.",
    ipoReadinessTitle: "Preparação para IPO",
    ipoReadinessDesc: "Planejando abrir capital? FaultRay comprova que sua infraestrutura atende aos requisitos de auditoria exigidos por investidores e reguladores.",
    ipoCheckDora: "Conformidade DORA para serviços financeiros",
    ipoCheckSoc2: "Pacote de evidências SOC2 Tipo II",
    ipoCheckIso: "Mapeamento de controles ISO27001",
    ipoCheckSla: "Prova matemática do SLA de disponibilidade",
    ipoCheckRunbooks: "Runbooks de resposta a incidentes",
    ipoCheckAudit: "Trilha de auditoria de gerenciamento de mudanças",
  },
} as const;
type DoraLocale = keyof typeof DORA_DICT;

/* ============================================================
 * Types
 * ============================================================ */

interface DoraPillar {
  id: string;
  name: string;
  articles: string;
  score: number;
  status: "compliant" | "partial" | "non_compliant";
  compliant: number;
  total: number;
}

interface DoraControl {
  id: string;
  pillar: string;
  description: string;
  status: "compliant" | "partial" | "non_compliant";
  last_assessed: string;
  evidence: string | null;
}

interface DoraGap {
  control_id: string;
  severity: "critical" | "high" | "medium";
  description: string;
  remediation: string;
  deadline: string;
}

interface DoraMetric {
  value: number;
  unit: string;
  trend: "up" | "down" | "stable";
  benchmark: number;
  status: "good" | "warning" | "critical";
}

interface DoraMetrics {
  deployment_frequency: DoraMetric;
  lead_time: DoraMetric;
  change_failure_rate: DoraMetric;
  mttr: DoraMetric;
}

interface EvidencePackage {
  pillar: string;
  items: number;
  total_required: number;
  coverage: number;
}

interface DoraData {
  assessed_at: string;
  organization: string;
  overall_score: number;
  pillars: DoraPillar[];
  controls: DoraControl[];
  gaps: DoraGap[];
  dora_metrics: DoraMetrics;
  evidence_packages: EvidencePackage[];
}

/* ============================================================
 * Static demo fallback
 * ============================================================ */

const DEMO: DoraData = {
  assessed_at: "2026-04-01T09:00:00Z",
  organization: "Demo Organization",
  overall_score: 72,
  pillars: [
    { id: "pillar1", name: "ICT Risk Management", articles: "Articles 5-16", score: 78, status: "partial", compliant: 6, total: 10 },
    { id: "pillar2", name: "Incident Management", articles: "Articles 17-23", score: 62, status: "partial", compliant: 4, total: 8 },
    { id: "pillar3", name: "Resilience Testing", articles: "Articles 24-27", score: 70, status: "partial", compliant: 5, total: 7 },
    { id: "pillar4", name: "Third-Party Risk", articles: "Articles 28-30", score: 55, status: "non_compliant", compliant: 3, total: 8 },
    { id: "pillar5", name: "Information Sharing", articles: "Article 45", score: 82, status: "compliant", compliant: 4, total: 5 },
  ],
  controls: [
    { id: "P1-01", pillar: "pillar1", description: "ICT Risk Management Policy", status: "compliant", last_assessed: "2026-03-15", evidence: "doc_001.pdf" },
    { id: "P1-02", pillar: "pillar1", description: "Asset Management & Classification", status: "compliant", last_assessed: "2026-03-15", evidence: "doc_002.pdf" },
    { id: "P1-03", pillar: "pillar1", description: "Risk Assessment Process", status: "partial", last_assessed: "2026-02-28", evidence: "doc_003.pdf" },
    { id: "P1-04", pillar: "pillar1", description: "Protection & Prevention Controls", status: "non_compliant", last_assessed: "2026-02-01", evidence: null },
    { id: "P2-01", pillar: "pillar2", description: "Incident Detection & Classification", status: "compliant", last_assessed: "2026-03-20", evidence: "doc_010.pdf" },
    { id: "P2-02", pillar: "pillar2", description: "Major Incident Reporting (4h SLA)", status: "non_compliant", last_assessed: "2026-03-01", evidence: null },
    { id: "P2-03", pillar: "pillar2", description: "Incident Response Procedures", status: "partial", last_assessed: "2026-03-10", evidence: "doc_012.pdf" },
    { id: "P2-04", pillar: "pillar2", description: "Root Cause Analysis Process", status: "compliant", last_assessed: "2026-03-20", evidence: "doc_013.pdf" },
    { id: "P3-01", pillar: "pillar3", description: "Periodic ICT Tool Testing", status: "compliant", last_assessed: "2026-03-25", evidence: "doc_020.pdf" },
    { id: "P3-02", pillar: "pillar3", description: "Threat-Led Penetration Testing (TLPT)", status: "non_compliant", last_assessed: "2026-01-15", evidence: null },
    { id: "P3-03", pillar: "pillar3", description: "Test Result Remediation Tracking", status: "compliant", last_assessed: "2026-03-25", evidence: "doc_022.pdf" },
    { id: "P4-01", pillar: "pillar4", description: "Third-Party Identification & Classification", status: "partial", last_assessed: "2026-02-20", evidence: "doc_030.pdf" },
    { id: "P4-02", pillar: "pillar4", description: "DORA Contract Clause Standardization", status: "non_compliant", last_assessed: "2026-01-31", evidence: null },
    { id: "P4-03", pillar: "pillar4", description: "Cloud Concentration Risk Assessment", status: "non_compliant", last_assessed: "2026-01-31", evidence: null },
    { id: "P4-04", pillar: "pillar4", description: "Critical Third-Party Oversight Framework", status: "partial", last_assessed: "2026-02-28", evidence: "doc_033.pdf" },
    { id: "P5-01", pillar: "pillar5", description: "Cyber Threat Intelligence Sharing", status: "compliant", last_assessed: "2026-03-28", evidence: "doc_040.pdf" },
    { id: "P5-02", pillar: "pillar5", description: "Incident Information Exchange", status: "compliant", last_assessed: "2026-03-28", evidence: "doc_041.pdf" },
    { id: "P5-03", pillar: "pillar5", description: "Cross-Industry Collaboration", status: "partial", last_assessed: "2026-03-10", evidence: "doc_042.pdf" },
  ],
  gaps: [
    { control_id: "P4-02", severity: "critical", description: "DORA-required contract clauses missing from 23 vendor agreements", remediation: "Update all vendor contracts with DORA-required provisions", deadline: "2026-06-30" },
    { control_id: "P2-02", severity: "critical", description: "Incident reporting pipeline not automated within 4-hour regulatory window", remediation: "Implement automated incident reporting with 4h SLA", deadline: "2026-05-31" },
    { control_id: "P4-03", severity: "high", description: "No concentration risk assessment for AWS/Azure cloud dependency", remediation: "Perform concentration risk assessment, document multi-cloud strategy", deadline: "2026-07-31" },
    { control_id: "P3-02", severity: "high", description: "No TLPT program established; required for systemic institutions", remediation: "Establish annual TLPT program with qualified external testers", deadline: "2026-09-30" },
    { control_id: "P1-04", severity: "high", description: "Insufficient network segmentation between critical systems", remediation: "Implement zero-trust network segmentation", deadline: "2026-06-30" },
  ],
  dora_metrics: {
    deployment_frequency: { value: 12.3, unit: "per week", trend: "up", benchmark: 15.0, status: "good" },
    lead_time: { value: 4.2, unit: "days", trend: "down", benchmark: 3.0, status: "warning" },
    change_failure_rate: { value: 8.5, unit: "%", trend: "down", benchmark: 5.0, status: "warning" },
    mttr: { value: 47, unit: "minutes", trend: "down", benchmark: 30, status: "good" },
  },
  evidence_packages: [
    { pillar: "pillar1", items: 6, total_required: 10, coverage: 60 },
    { pillar: "pillar2", items: 4, total_required: 8, coverage: 50 },
    { pillar: "pillar3", items: 4, total_required: 7, coverage: 57 },
    { pillar: "pillar4", items: 2, total_required: 8, coverage: 25 },
    { pillar: "pillar5", items: 4, total_required: 5, coverage: 80 },
  ],
};

/* ============================================================
 * Helpers
 * ============================================================ */

function scoreColor(score: number): string {
  if (score >= 80) return "#10b981";
  if (score >= 60) return "#f59e0b";
  return "#ef4444";
}

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "compliant" || status === "good") return "green";
  if (status === "partial" || status === "warning") return "yellow";
  if (status === "non_compliant" || status === "critical") return "red";
  return "default";
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === "up") return <TrendingUp size={14} className="text-emerald-400" />;
  if (trend === "down") return <TrendingDown size={14} className="text-red-400" />;
  return <Minus size={14} className="text-[#64748b]" />;
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function DoraPage() {
  const locale = useLocale();
  const t = DORA_DICT[(locale as DoraLocale)] ?? DORA_DICT.en;
  const [data, setData] = useState<DoraData>(DEMO);
  const [loading, setLoading] = useState(true);
  const [expandedPillar, setExpandedPillar] = useState<string | null>("pillar1");
  const [showAllControls, setShowAllControls] = useState(false);

  useEffect(() => {
    fetch("/api/governance?action=dora")
      .then((r) => r.json())
      .then((d) => { if (d && d.pillars) setData(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const totalControls = data.controls.length;
  const compliantCount = data.controls.filter((c) => c.status === "compliant").length;
  const partialCount = data.controls.filter((c) => c.status === "partial").length;
  const nonCompliantCount = data.controls.filter((c) => c.status === "non_compliant").length;

  const pillarControls = (pillarId: string) => data.controls.filter((c) => c.pillar === pillarId);
  const displayedControls = showAllControls ? data.controls : data.controls.slice(0, 8);

  const METRIC_LABELS: Record<string, string> = {
    deployment_frequency: t.deploymentFrequency,
    lead_time: t.leadTime,
    change_failure_rate: t.changeFailureRate,
    mttr: t.mttr,
  };

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <ShieldAlert size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
        {loading && <p className="text-xs text-[#64748b] mt-1">{t.loading}</p>}
      </div>

      {/* ── 1. Score Overview ── */}
      <div className="grid md:grid-cols-4 gap-6 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.overallScore}</p>
          <p className="text-5xl font-extrabold font-mono" style={{ color: scoreColor(data.overall_score) }}>
            {data.overall_score}%
          </p>
          <Badge variant={statusVariant(data.overall_score >= 80 ? "compliant" : data.overall_score >= 60 ? "partial" : "non_compliant")} className="mt-2">
            {data.overall_score >= 80 ? t.compliant : data.overall_score >= 60 ? t.partial : t.nonCompliant}
          </Badge>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.compliantControls}</p>
          <p className="text-5xl font-extrabold font-mono text-emerald-400">{compliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.ofTotal.replace("{n}", String(totalControls))}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.partialControls}</p>
          <p className="text-5xl font-extrabold font-mono text-yellow-400">{partialCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.needsImprovement}</p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.nonCompliantControls}</p>
          <p className="text-5xl font-extrabold font-mono text-red-400">{nonCompliantCount}</p>
          <p className="text-xs text-[#64748b] mt-2">{t.requiresRemediation}</p>
        </Card>
      </div>

      {/* ── 2. Pillar Breakdown ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
          <ShieldAlert size={18} className="text-[#FFD700]" />
          {t.pillarOverview}
        </h3>
        <div className="space-y-3">
          {data.pillars.map((pillar) => (
            <div key={pillar.id}>
              <button
                className="w-full text-left"
                onClick={() => setExpandedPillar(expandedPillar === pillar.id ? null : pillar.id)}
              >
                <div className="flex items-center gap-3 py-2">
                  {expandedPillar === pillar.id
                    ? <ChevronDown size={14} className="text-[#64748b] shrink-0" />
                    : <ChevronRight size={14} className="text-[#64748b] shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium truncate">{pillar.name}</span>
                      <div className="flex items-center gap-3 shrink-0 ml-4">
                        <span className="text-xs text-[#64748b]">{pillar.articles}</span>
                        <Badge variant={statusVariant(pillar.status)}>
                          {pillar.status === "compliant" ? t.compliant : pillar.status === "partial" ? t.partial : t.nonCompliant}
                        </Badge>
                        <span className="text-sm font-bold font-mono min-w-[44px] text-right" style={{ color: scoreColor(pillar.score) }}>
                          {pillar.score}%
                        </span>
                      </div>
                    </div>
                    <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: `${pillar.score}%`, backgroundColor: scoreColor(pillar.score) }}
                      />
                    </div>
                  </div>
                </div>
              </button>

              {expandedPillar === pillar.id && (
                <div className="ml-6 mt-2 mb-3 space-y-2">
                  {pillarControls(pillar.id).map((ctrl) => (
                    <div
                      key={ctrl.id}
                      className={`flex items-center gap-3 p-3 rounded-lg border text-sm ${
                        ctrl.status === "compliant"
                          ? "bg-emerald-500/5 border-emerald-500/10"
                          : ctrl.status === "partial"
                            ? "bg-yellow-500/5 border-yellow-500/10"
                            : "bg-red-500/5 border-red-500/10"
                      }`}
                    >
                      {ctrl.status === "compliant"
                        ? <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                        : ctrl.status === "partial"
                          ? <AlertTriangle size={14} className="text-yellow-400 shrink-0" />
                          : <XCircle size={14} className="text-red-400 shrink-0" />}
                      <span className="font-mono text-xs text-[#64748b] shrink-0">{ctrl.id}</span>
                      <span className="flex-1 text-[#e2e8f0]">{ctrl.description}</span>
                      <span className="text-xs text-[#64748b] shrink-0">{ctrl.last_assessed}</span>
                      {ctrl.evidence
                        ? <Badge variant="default"><FileText size={10} className="mr-1" />{t.evidenceAvailable}</Badge>
                        : <Badge variant="red"><FileText size={10} className="mr-1" />{t.noEvidence}</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* ── 3. Control Assessment Table ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <CheckCircle2 size={18} className="text-[#FFD700]" />
          {t.controlAssessment}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1e293b]">
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.controlId}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.description}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.statusCol}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.lastAssessed}</th>
                <th className="text-left py-3 px-2 text-[#64748b] font-medium">{t.evidence}</th>
              </tr>
            </thead>
            <tbody>
              {displayedControls.map((ctrl) => (
                <tr key={ctrl.id} className="border-b border-[#1e293b]/50 hover:bg-white/[0.02]">
                  <td className="py-3 px-2 font-mono text-xs text-[#64748b]">{ctrl.id}</td>
                  <td className="py-3 px-2 text-[#e2e8f0]">{ctrl.description}</td>
                  <td className="py-3 px-2">
                    <Badge variant={statusVariant(ctrl.status)}>
                      {ctrl.status === "compliant" ? t.pass : ctrl.status === "partial" ? t.partial : t.fail}
                    </Badge>
                  </td>
                  <td className="py-3 px-2 text-xs text-[#64748b]">{ctrl.last_assessed}</td>
                  <td className="py-3 px-2">
                    {ctrl.evidence
                      ? <span className="text-xs text-emerald-400 flex items-center gap-1"><FileText size={10} />{ctrl.evidence}</span>
                      : <span className="text-xs text-red-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {data.controls.length > 8 && (
          <div className="mt-4 text-center">
            <Button variant="secondary" size="sm" onClick={() => setShowAllControls(!showAllControls)}>
              {showAllControls ? t.showLess : t.showAll.replace("{n}", String(data.controls.length))}
            </Button>
          </div>
        )}
      </Card>

      {/* ── 4. Gap Analysis ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={18} className="text-[#FFD700]" />
          {t.gapAnalysis}
        </h3>
        <p className="text-xs text-[#64748b] mb-4">{t.gapSubtitle}</p>
        <div className="space-y-3">
          {data.gaps.map((gap, i) => (
            <div
              key={gap.control_id}
              className={`p-4 rounded-xl border ${
                gap.severity === "critical"
                  ? "bg-red-500/5 border-red-500/20"
                  : gap.severity === "high"
                    ? "bg-yellow-500/5 border-yellow-500/20"
                    : "bg-blue-500/5 border-blue-500/20"
              }`}
            >
              <div className="flex items-start gap-3">
                <span className="text-sm font-bold text-[#FFD700] shrink-0 w-5">{i + 1}.</span>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-mono text-xs text-[#64748b]">{gap.control_id}</span>
                    <Badge variant={gap.severity === "critical" ? "red" : gap.severity === "high" ? "yellow" : "default"}>
                      {gap.severity.toUpperCase()}
                    </Badge>
                    <span className="text-xs text-[#64748b]">{t.deadline}: {gap.deadline}</span>
                  </div>
                  <p className="text-sm text-[#e2e8f0] mb-1">{gap.description}</p>
                  <p className="text-xs text-[#FFD700] flex items-center gap-1">
                    <ArrowRight size={10} />
                    {gap.remediation}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 5. DORA 4 Key Metrics ── */}
      <Card className="mb-8">
        <h3 className="text-lg font-bold mb-6 flex items-center gap-2">
          <TrendingUp size={18} className="text-[#FFD700]" />
          {t.doraMetricsTitle}
        </h3>
        <div className="grid md:grid-cols-2 gap-6">
          {(Object.entries(data.dora_metrics) as [string, DoraMetric][]).map(([key, metric]) => (
            <div key={key} className="p-4 rounded-xl border border-[#1e293b] bg-white/[0.02]">
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-medium text-[#94a3b8]">{METRIC_LABELS[key] ?? key}</p>
                <div className="flex items-center gap-2">
                  <TrendIcon trend={metric.trend} />
                  <Badge variant={statusVariant(metric.status)}>
                    {metric.status === "good" ? t.good : metric.status === "warning" ? t.warning : t.critical}
                  </Badge>
                </div>
              </div>
              <p className="text-3xl font-extrabold font-mono text-[#e2e8f0]">
                {metric.value}
                <span className="text-sm font-normal text-[#64748b] ml-1">{metric.unit}</span>
              </p>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-xs text-[#64748b]">{t.benchmark}:</span>
                <span className="text-xs font-mono text-[#FFD700]">{metric.benchmark} {metric.unit}</span>
              </div>
              <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full"
                  style={{
                    width: `${Math.min(100, (metric.value / (metric.benchmark * 1.5)) * 100)}%`,
                    backgroundColor: scoreColor(metric.status === "good" ? 85 : metric.status === "warning" ? 65 : 30),
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 6. IPO Readiness ── */}
      <Card className="mb-8 border-[#FFD700]/20 bg-gradient-to-br from-[#0a0e1a] to-[#FFD700]/[0.03]">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#FFD700]/10 border border-[#FFD700]/20 flex items-center justify-center shrink-0">
            <Rocket size={22} className="text-[#FFD700]" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-bold text-[#FFD700] mb-2">{t.ipoReadinessTitle ?? "IPO Readiness"}</h3>
            <p className="text-sm text-[#94a3b8] leading-relaxed mb-4">
              {t.ipoReadinessDesc ?? "Going public? FaultRay proves your infrastructure meets the audit requirements investors and regulators demand."}
            </p>
            <div className="grid sm:grid-cols-2 gap-2">
              {[
                t.ipoCheckDora ?? "DORA compliance for financial services",
                t.ipoCheckSoc2 ?? "SOC2 Type II evidence package",
                t.ipoCheckIso ?? "ISO27001 control mapping",
                t.ipoCheckSla ?? "Availability SLA mathematical proof",
                t.ipoCheckRunbooks ?? "Incident response runbooks",
                t.ipoCheckAudit ?? "Change management audit trail",
              ].map((item) => (
                <div key={item} className="flex items-center gap-2 text-sm text-[#e2e8f0]">
                  <CheckCircle2 size={14} className="text-emerald-400 shrink-0" />
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </Card>

      {/* ── 7. Evidence Package ── */}
      <Card>
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-bold flex items-center gap-2">
            <FileText size={18} className="text-[#FFD700]" />
            {t.evidencePackage}
          </h3>
          <Button size="sm" onClick={() => alert("Generating evidence package...")}>
            <Download size={14} />
            {t.generateEvidence}
          </Button>
        </div>
        <div className="space-y-4">
          {data.evidence_packages.map((pkg) => {
            const pillar = data.pillars.find((p) => p.id === pkg.pillar);
            return (
              <div key={pkg.pillar}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm text-[#94a3b8]">{pillar?.name ?? pkg.pillar}</span>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-[#64748b]">{pkg.items}/{pkg.total_required} {t.evidenceItems}</span>
                    <span className="text-sm font-mono font-bold" style={{ color: scoreColor(pkg.coverage) }}>
                      {pkg.coverage}%
                    </span>
                  </div>
                </div>
                <div className="h-2 bg-white/5 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${pkg.coverage}%`, backgroundColor: scoreColor(pkg.coverage) }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        <p className="text-xs text-[#64748b] mt-4 border-t border-[#1e293b] pt-3">
          {t.evidenceNote}
        </p>
      </Card>
    </div>
  );
}
