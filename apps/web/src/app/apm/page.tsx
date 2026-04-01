"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect, useCallback, useMemo, memo } from "react";
import {
  Activity,
  Cpu,
  HardDrive,
  Wifi,
  AlertTriangle,
  Server,
  RefreshCw,
  Download,
  Radio,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Network,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Inline i18n (extracted from app-dict.ts to reduce chunk size)
 * ============================================================ */

const APM_DICT = {
  en: {
    title: "APM Dashboard",
    subtitle: "Real-time monitoring of connected agents, metrics, and alerts",
    connectedAgents: "Connected Agents",
    activeAlerts: "Active Alerts",
    avgCpu: "Avg CPU Usage",
    avgMemory: "Avg Memory Usage",
    agentId: "Agent ID",
    hostname: "Hostname",
    ip: "IP Address",
    status: "Status",
    cpu: "CPU%",
    memory: "Mem%",
    disk: "Disk%",
    lastSeen: "Last Seen",
    running: "Running",
    offline: "Offline",
    degraded: "Degraded",
    noAgents: "No agents connected. Install the FaultRay agent to start monitoring.",
    noAlerts: "No active alerts.",
    metricsTitle: "Metrics",
    cpuUsage: "CPU Usage",
    memoryUsage: "Memory Usage",
    networkIo: "Network I/O",
    alertsTitle: "Active Alerts",
    severity: "Severity",
    rule: "Rule",
    agent: "Agent",
    metric: "Metric",
    value: "Value",
    threshold: "Threshold",
    firedAt: "Fired At",
    critical: "CRITICAL",
    warning: "WARNING",
    info: "INFO",
    setupTitle: "Setup APM Agent",
    setupDescription: "Install the FaultRay agent on your servers to start collecting metrics.",
    setupStep1: "Download the agent: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "Configure your API key in /etc/faultray/agent.conf",
    setupStep3: "Start the service: systemctl start faultray-agent",
    setupStep4: "Verify connection — the agent will appear in the table above within 60s",
    refresh: "Refresh",
    export: "Export",
    setupAgent: "Setup Agent",
    byteSent: "Bytes Sent",
    byteRecv: "Bytes Recv",
    last1h: "1H",
    last6h: "6H",
    last24h: "24H",
    last7d: "7D",
    autoRefresh: "Auto Refresh",
    refreshing: "Refreshing...",
    timeRange: "Time Range",
    allAgents: "All Agents",
    selectAgent: "Select Agent",
    diskUsage: "Disk Usage",
    loadAverage: "Load Average",
    connections: "Connections",
    trend: "Trend",
    up: "Up",
    down: "Down",
    stable: "Stable",
    infrastructureMap: "Infrastructure Map",
    processExplorer: "Process Explorer",
    alertTimeline: "Alert Timeline",
    pid: "PID",
    name: "Name",
    threads: "Threads",
    sortBy: "Sort By",
    search: "Search processes...",
    acknowledge: "Acknowledge",
    noActiveAlerts: "No active alerts — all systems nominal",
    allClear: "All Clear",
    quickSetup: "Quick Setup",
    expand: "Expand",
    collapse: "Collapse",
    bytesPerSec: "B/s",
    percent: "%",
    count: "Count",
    last5m: "5M",
    last15m: "15M",
    last30d: "30D",
  },
  ja: {
    title: "APM ダッシュボード",
    subtitle: "接続されたエージェント、メトリクス、アラートのリアルタイム監視",
    connectedAgents: "接続中エージェント",
    activeAlerts: "アクティブアラート",
    avgCpu: "平均 CPU 使用率",
    avgMemory: "平均メモリ使用率",
    agentId: "エージェント ID",
    hostname: "ホスト名",
    ip: "IP アドレス",
    status: "ステータス",
    cpu: "CPU%",
    memory: "メモリ%",
    disk: "ディスク%",
    lastSeen: "最終確認",
    running: "稼働中",
    offline: "オフライン",
    degraded: "低下中",
    noAgents: "エージェントが接続されていません。FaultRay エージェントをインストールして監視を開始してください。",
    noAlerts: "アクティブなアラートはありません。",
    metricsTitle: "メトリクス",
    cpuUsage: "CPU 使用率",
    memoryUsage: "メモリ使用率",
    networkIo: "ネットワーク I/O",
    alertsTitle: "アクティブアラート",
    severity: "重要度",
    rule: "ルール",
    agent: "エージェント",
    metric: "メトリクス",
    value: "値",
    threshold: "しきい値",
    firedAt: "発生日時",
    critical: "CRITICAL",
    warning: "WARNING",
    info: "INFO",
    setupTitle: "APM エージェントのセットアップ",
    setupDescription: "サーバーに FaultRay エージェントをインストールしてメトリクス収集を開始します。",
    setupStep1: "エージェントをダウンロード: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "/etc/faultray/agent.conf に API キーを設定します",
    setupStep3: "サービスを開始: systemctl start faultray-agent",
    setupStep4: "接続を確認 — 60秒以内に上のテーブルにエージェントが表示されます",
    refresh: "更新",
    export: "エクスポート",
    setupAgent: "エージェント設定",
    byteSent: "送信バイト",
    byteRecv: "受信バイト",
    last1h: "1時間",
    last6h: "6時間",
    last24h: "24時間",
    last7d: "7日間",
    autoRefresh: "自動更新",
    refreshing: "更新中...",
    timeRange: "時間範囲",
    allAgents: "全エージェント",
    selectAgent: "エージェントを選択",
    diskUsage: "ディスク使用率",
    loadAverage: "ロードアベレージ",
    connections: "接続数",
    trend: "トレンド",
    up: "上昇",
    down: "下降",
    stable: "安定",
    infrastructureMap: "インフラマップ",
    processExplorer: "プロセスエクスプローラー",
    alertTimeline: "アラートタイムライン",
    pid: "PID",
    name: "名前",
    threads: "スレッド",
    sortBy: "並び替え",
    search: "プロセスを検索...",
    acknowledge: "確認",
    noActiveAlerts: "アクティブなアラートなし — 全システム正常",
    allClear: "問題なし",
    quickSetup: "クイックセットアップ",
    expand: "展開",
    collapse: "折りたたむ",
    bytesPerSec: "B/s",
    percent: "%",
    count: "件",
    last5m: "5分",
    last15m: "15分",
    last30d: "30日",
  },
  de: {
    title: "APM-Dashboard",
    subtitle: "Echtzeit-Überwachung verbundener Agenten, Metriken und Warnungen",
    connectedAgents: "Verbundene Agenten",
    activeAlerts: "Aktive Warnungen",
    avgCpu: "Durchschn. CPU-Auslastung",
    avgMemory: "Durchschn. Speicherauslastung",
    agentId: "Agenten-ID",
    hostname: "Hostname",
    ip: "IP-Adresse",
    status: "Status",
    cpu: "CPU%",
    memory: "Speicher%",
    disk: "Festplatte%",
    lastSeen: "Zuletzt gesehen",
    running: "Aktiv",
    offline: "Offline",
    degraded: "Beeinträchtigt",
    noAgents: "Keine Agenten verbunden. Installieren Sie den FaultRay-Agenten, um die Überwachung zu starten.",
    noAlerts: "Keine aktiven Warnungen.",
    metricsTitle: "Metriken",
    cpuUsage: "CPU-Auslastung",
    memoryUsage: "Speicherauslastung",
    networkIo: "Netzwerk-E/A",
    alertsTitle: "Aktive Warnungen",
    severity: "Schweregrad",
    rule: "Regel",
    agent: "Agent",
    metric: "Metrik",
    value: "Wert",
    threshold: "Schwellenwert",
    firedAt: "Ausgelöst am",
    critical: "KRITISCH",
    warning: "WARNUNG",
    info: "INFO",
    setupTitle: "APM-Agenten einrichten",
    setupDescription: "Installieren Sie den FaultRay-Agenten auf Ihren Servern, um Metriken zu erfassen.",
    setupStep1: "Agenten herunterladen: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "API-Schlüssel in /etc/faultray/agent.conf konfigurieren",
    setupStep3: "Dienst starten: systemctl start faultray-agent",
    setupStep4: "Verbindung prüfen — Agent erscheint innerhalb von 60s in der Tabelle",
    refresh: "Aktualisieren",
    export: "Exportieren",
    setupAgent: "Agent einrichten",
    byteSent: "Gesendet",
    byteRecv: "Empfangen",
    last1h: "1Std",
    last6h: "6Std",
    last24h: "24Std",
    last7d: "7T",
    autoRefresh: "Automatisch aktualisieren",
    refreshing: "Aktualisierung...",
    timeRange: "Zeitraum",
    allAgents: "Alle Agenten",
    selectAgent: "Agent auswählen",
    diskUsage: "Festplattenauslastung",
    loadAverage: "Lastdurchschnitt",
    connections: "Verbindungen",
    trend: "Trend",
    up: "Aufsteigend",
    down: "Absteigend",
    stable: "Stabil",
    infrastructureMap: "Infrastrukturkarte",
    processExplorer: "Prozessexplorer",
    alertTimeline: "Warnungs-Zeitachse",
    pid: "PID",
    name: "Name",
    threads: "Threads",
    sortBy: "Sortieren nach",
    search: "Prozesse suchen...",
    acknowledge: "Bestätigen",
    noActiveAlerts: "Keine aktiven Warnungen — alle Systeme in Ordnung",
    allClear: "Alles in Ordnung",
    quickSetup: "Schnelleinrichtung",
    expand: "Erweitern",
    collapse: "Einklappen",
    bytesPerSec: "B/s",
    percent: "%",
    count: "Anzahl",
    last5m: "5Min",
    last15m: "15Min",
    last30d: "30T",
  },
  fr: {
    title: "Tableau de bord APM",
    subtitle: "Surveillance en temps réel des agents connectés, métriques et alertes",
    connectedAgents: "Agents connectés",
    activeAlerts: "Alertes actives",
    avgCpu: "CPU moyen",
    avgMemory: "Mémoire moyenne",
    agentId: "ID agent",
    hostname: "Nom d'hôte",
    ip: "Adresse IP",
    status: "Statut",
    cpu: "CPU%",
    memory: "Mém%",
    disk: "Disque%",
    lastSeen: "Dernière vue",
    running: "Actif",
    offline: "Hors ligne",
    degraded: "Dégradé",
    noAgents: "Aucun agent connecté. Installez l'agent FaultRay pour commencer la surveillance.",
    noAlerts: "Aucune alerte active.",
    metricsTitle: "Métriques",
    cpuUsage: "Utilisation CPU",
    memoryUsage: "Utilisation mémoire",
    networkIo: "E/S réseau",
    alertsTitle: "Alertes actives",
    severity: "Sévérité",
    rule: "Règle",
    agent: "Agent",
    metric: "Métrique",
    value: "Valeur",
    threshold: "Seuil",
    firedAt: "Déclenché le",
    critical: "CRITIQUE",
    warning: "AVERTISSEMENT",
    info: "INFO",
    setupTitle: "Configurer l'agent APM",
    setupDescription: "Installez l'agent FaultRay sur vos serveurs pour collecter des métriques.",
    setupStep1: "Télécharger l'agent: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "Configurer votre clé API dans /etc/faultray/agent.conf",
    setupStep3: "Démarrer le service: systemctl start faultray-agent",
    setupStep4: "Vérifier la connexion — l'agent apparaîtra dans le tableau en moins de 60s",
    refresh: "Actualiser",
    export: "Exporter",
    setupAgent: "Configurer l'agent",
    byteSent: "Octets envoyés",
    byteRecv: "Octets reçus",
    last1h: "1H",
    last6h: "6H",
    last24h: "24H",
    last7d: "7J",
    autoRefresh: "Actualisation auto",
    refreshing: "Actualisation...",
    timeRange: "Plage temporelle",
    allAgents: "Tous les agents",
    selectAgent: "Sélectionner un agent",
    diskUsage: "Utilisation disque",
    loadAverage: "Charge moyenne",
    connections: "Connexions",
    trend: "Tendance",
    up: "En hausse",
    down: "En baisse",
    stable: "Stable",
    infrastructureMap: "Carte d'infrastructure",
    processExplorer: "Explorateur de processus",
    alertTimeline: "Chronologie des alertes",
    pid: "PID",
    name: "Nom",
    threads: "Threads",
    sortBy: "Trier par",
    search: "Rechercher des processus...",
    acknowledge: "Accuser réception",
    noActiveAlerts: "Aucune alerte active — tous les systèmes nominaux",
    allClear: "Tout est nominal",
    quickSetup: "Configuration rapide",
    expand: "Développer",
    collapse: "Réduire",
    bytesPerSec: "o/s",
    percent: "%",
    count: "Nombre",
    last5m: "5Min",
    last15m: "15Min",
    last30d: "30J",
  },
  zh: {
    title: "APM 仪表盘",
    subtitle: "实时监控已连接代理、指标和告警",
    connectedAgents: "已连接代理",
    activeAlerts: "活跃告警",
    avgCpu: "平均 CPU 使用率",
    avgMemory: "平均内存使用率",
    agentId: "代理 ID",
    hostname: "主机名",
    ip: "IP 地址",
    status: "状态",
    cpu: "CPU%",
    memory: "内存%",
    disk: "磁盘%",
    lastSeen: "最后在线",
    running: "运行中",
    offline: "离线",
    degraded: "降级",
    noAgents: "未连接代理。请安装 FaultRay 代理以开始监控。",
    noAlerts: "暂无活跃告警。",
    metricsTitle: "指标",
    cpuUsage: "CPU 使用率",
    memoryUsage: "内存使用率",
    networkIo: "网络 I/O",
    alertsTitle: "活跃告警",
    severity: "严重程度",
    rule: "规则",
    agent: "代理",
    metric: "指标",
    value: "值",
    threshold: "阈值",
    firedAt: "触发时间",
    critical: "严重",
    warning: "警告",
    info: "信息",
    setupTitle: "配置 APM 代理",
    setupDescription: "在服务器上安装 FaultRay 代理以开始收集指标。",
    setupStep1: "下载代理: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "在 /etc/faultray/agent.conf 中配置 API 密钥",
    setupStep3: "启动服务: systemctl start faultray-agent",
    setupStep4: "验证连接 — 代理将在 60 秒内出现在上方表格中",
    refresh: "刷新",
    export: "导出",
    setupAgent: "配置代理",
    byteSent: "发送字节",
    byteRecv: "接收字节",
    last1h: "1小时",
    last6h: "6小时",
    last24h: "24小时",
    last7d: "7天",
    autoRefresh: "自动刷新",
    refreshing: "刷新中...",
    timeRange: "时间范围",
    allAgents: "所有代理",
    selectAgent: "选择代理",
    diskUsage: "磁盘使用率",
    loadAverage: "平均负载",
    connections: "连接数",
    trend: "趋势",
    up: "上升",
    down: "下降",
    stable: "稳定",
    infrastructureMap: "基础设施图",
    processExplorer: "进程浏览器",
    alertTimeline: "告警时间线",
    pid: "PID",
    name: "名称",
    threads: "线程",
    sortBy: "排序方式",
    search: "搜索进程...",
    acknowledge: "确认",
    noActiveAlerts: "无活跃告警 — 所有系统正常",
    allClear: "一切正常",
    quickSetup: "快速设置",
    expand: "展开",
    collapse: "收起",
    bytesPerSec: "B/s",
    percent: "%",
    count: "数量",
    last5m: "5分钟",
    last15m: "15分钟",
    last30d: "30天",
  },
  ko: {
    title: "APM 대시보드",
    subtitle: "연결된 에이전트, 메트릭 및 알림의 실시간 모니터링",
    connectedAgents: "연결된 에이전트",
    activeAlerts: "활성 알림",
    avgCpu: "평균 CPU 사용률",
    avgMemory: "평균 메모리 사용률",
    agentId: "에이전트 ID",
    hostname: "호스트명",
    ip: "IP 주소",
    status: "상태",
    cpu: "CPU%",
    memory: "메모리%",
    disk: "디스크%",
    lastSeen: "마지막 확인",
    running: "실행 중",
    offline: "오프라인",
    degraded: "성능 저하",
    noAgents: "연결된 에이전트가 없습니다. FaultRay 에이전트를 설치하여 모니터링을 시작하세요.",
    noAlerts: "활성 알림이 없습니다.",
    metricsTitle: "메트릭",
    cpuUsage: "CPU 사용률",
    memoryUsage: "메모리 사용률",
    networkIo: "네트워크 I/O",
    alertsTitle: "활성 알림",
    severity: "심각도",
    rule: "규칙",
    agent: "에이전트",
    metric: "메트릭",
    value: "값",
    threshold: "임계값",
    firedAt: "발생 시각",
    critical: "심각",
    warning: "경고",
    info: "정보",
    setupTitle: "APM 에이전트 설정",
    setupDescription: "서버에 FaultRay 에이전트를 설치하여 메트릭 수집을 시작합니다.",
    setupStep1: "에이전트 다운로드: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "/etc/faultray/agent.conf에 API 키 설정",
    setupStep3: "서비스 시작: systemctl start faultray-agent",
    setupStep4: "연결 확인 — 에이전트가 60초 이내에 위 표에 나타납니다",
    refresh: "새로 고침",
    export: "내보내기",
    setupAgent: "에이전트 설정",
    byteSent: "전송 바이트",
    byteRecv: "수신 바이트",
    last1h: "1시간",
    last6h: "6시간",
    last24h: "24시간",
    last7d: "7일",
    autoRefresh: "자동 새로고침",
    refreshing: "새로고침 중...",
    timeRange: "시간 범위",
    allAgents: "모든 에이전트",
    selectAgent: "에이전트 선택",
    diskUsage: "디스크 사용률",
    loadAverage: "로드 평균",
    connections: "연결 수",
    trend: "추세",
    up: "상승",
    down: "하강",
    stable: "안정",
    infrastructureMap: "인프라 맵",
    processExplorer: "프로세스 탐색기",
    alertTimeline: "알림 타임라인",
    pid: "PID",
    name: "이름",
    threads: "스레드",
    sortBy: "정렬 기준",
    search: "프로세스 검색...",
    acknowledge: "확인",
    noActiveAlerts: "활성 알림 없음 — 모든 시스템 정상",
    allClear: "이상 없음",
    quickSetup: "빠른 설정",
    expand: "펼치기",
    collapse: "접기",
    bytesPerSec: "B/s",
    percent: "%",
    count: "개",
    last5m: "5분",
    last15m: "15분",
    last30d: "30일",
  },
  es: {
    title: "Panel APM",
    subtitle: "Monitoreo en tiempo real de agentes conectados, métricas y alertas",
    connectedAgents: "Agentes conectados",
    activeAlerts: "Alertas activas",
    avgCpu: "CPU promedio",
    avgMemory: "Memoria promedio",
    agentId: "ID de agente",
    hostname: "Nombre de host",
    ip: "Dirección IP",
    status: "Estado",
    cpu: "CPU%",
    memory: "Mem%",
    disk: "Disco%",
    lastSeen: "Último visto",
    running: "Activo",
    offline: "Sin conexión",
    degraded: "Degradado",
    noAgents: "No hay agentes conectados. Instale el agente FaultRay para comenzar a monitorear.",
    noAlerts: "No hay alertas activas.",
    metricsTitle: "Métricas",
    cpuUsage: "Uso de CPU",
    memoryUsage: "Uso de memoria",
    networkIo: "E/S de red",
    alertsTitle: "Alertas activas",
    severity: "Severidad",
    rule: "Regla",
    agent: "Agente",
    metric: "Métrica",
    value: "Valor",
    threshold: "Umbral",
    firedAt: "Disparado el",
    critical: "CRÍTICO",
    warning: "ADVERTENCIA",
    info: "INFO",
    setupTitle: "Configurar agente APM",
    setupDescription: "Instale el agente FaultRay en sus servidores para comenzar a recopilar métricas.",
    setupStep1: "Descargar el agente: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "Configurar su clave API en /etc/faultray/agent.conf",
    setupStep3: "Iniciar el servicio: systemctl start faultray-agent",
    setupStep4: "Verificar la conexión — el agente aparecerá en la tabla en menos de 60s",
    refresh: "Actualizar",
    export: "Exportar",
    setupAgent: "Configurar agente",
    byteSent: "Bytes enviados",
    byteRecv: "Bytes recibidos",
    last1h: "1H",
    last6h: "6H",
    last24h: "24H",
    last7d: "7D",
    autoRefresh: "Actualización automática",
    refreshing: "Actualizando...",
    timeRange: "Rango de tiempo",
    allAgents: "Todos los agentes",
    selectAgent: "Seleccionar agente",
    diskUsage: "Uso de disco",
    loadAverage: "Carga promedio",
    connections: "Conexiones",
    trend: "Tendencia",
    up: "Subiendo",
    down: "Bajando",
    stable: "Estable",
    infrastructureMap: "Mapa de infraestructura",
    processExplorer: "Explorador de procesos",
    alertTimeline: "Línea de tiempo de alertas",
    pid: "PID",
    name: "Nombre",
    threads: "Hilos",
    sortBy: "Ordenar por",
    search: "Buscar procesos...",
    acknowledge: "Confirmar",
    noActiveAlerts: "Sin alertas activas — todos los sistemas nominales",
    allClear: "Todo en orden",
    quickSetup: "Configuración rápida",
    expand: "Expandir",
    collapse: "Contraer",
    bytesPerSec: "B/s",
    percent: "%",
    count: "Cantidad",
    last5m: "5Min",
    last15m: "15Min",
    last30d: "30D",
  },
  pt: {
    title: "Painel APM",
    subtitle: "Monitoramento em tempo real de agentes conectados, métricas e alertas",
    connectedAgents: "Agentes conectados",
    activeAlerts: "Alertas ativos",
    avgCpu: "CPU médio",
    avgMemory: "Memória média",
    agentId: "ID do agente",
    hostname: "Nome do host",
    ip: "Endereço IP",
    status: "Status",
    cpu: "CPU%",
    memory: "Mem%",
    disk: "Disco%",
    lastSeen: "Última vez visto",
    running: "Ativo",
    offline: "Offline",
    degraded: "Degradado",
    noAgents: "Nenhum agente conectado. Instale o agente FaultRay para iniciar o monitoramento.",
    noAlerts: "Nenhum alerta ativo.",
    metricsTitle: "Métricas",
    cpuUsage: "Uso de CPU",
    memoryUsage: "Uso de memória",
    networkIo: "E/S de rede",
    alertsTitle: "Alertas ativos",
    severity: "Severidade",
    rule: "Regra",
    agent: "Agente",
    metric: "Métrica",
    value: "Valor",
    threshold: "Limite",
    firedAt: "Disparado em",
    critical: "CRÍTICO",
    warning: "AVISO",
    info: "INFO",
    setupTitle: "Configurar agente APM",
    setupDescription: "Instale o agente FaultRay em seus servidores para começar a coletar métricas.",
    setupStep1: "Baixar o agente: curl -L https://faultray.io/install.sh | bash",
    setupStep2: "Configurar sua chave de API em /etc/faultray/agent.conf",
    setupStep3: "Iniciar o serviço: systemctl start faultray-agent",
    setupStep4: "Verificar conexão — o agente aparecerá na tabela em até 60s",
    refresh: "Atualizar",
    export: "Exportar",
    setupAgent: "Configurar agente",
    byteSent: "Bytes enviados",
    byteRecv: "Bytes recebidos",
    last1h: "1H",
    last6h: "6H",
    last24h: "24H",
    last7d: "7D",
    autoRefresh: "Atualização automática",
    refreshing: "Atualizando...",
    timeRange: "Intervalo de tempo",
    allAgents: "Todos os agentes",
    selectAgent: "Selecionar agente",
    diskUsage: "Uso de disco",
    loadAverage: "Carga média",
    connections: "Conexões",
    trend: "Tendência",
    up: "Subindo",
    down: "Descendo",
    stable: "Estável",
    infrastructureMap: "Mapa de infraestrutura",
    processExplorer: "Explorador de processos",
    alertTimeline: "Linha do tempo de alertas",
    pid: "PID",
    name: "Nome",
    threads: "Threads",
    sortBy: "Ordenar por",
    search: "Pesquisar processos...",
    acknowledge: "Reconhecer",
    noActiveAlerts: "Sem alertas ativos — todos os sistemas nominais",
    allClear: "Tudo em ordem",
    quickSetup: "Configuração rápida",
    expand: "Expandir",
    collapse: "Recolher",
    bytesPerSec: "B/s",
    percent: "%",
    count: "Contagem",
    last5m: "5Min",
    last15m: "15Min",
    last30d: "30D",
  },
} as const;
type ApmLocale = keyof typeof APM_DICT;
import { api, type ApmAgent, type ApmMetricPoint, type ApmAlert } from "@/lib/api";

/* ============================================================
 * Constants
 * ============================================================ */

const AGENT_COLORS = [
  "#10b981", // emerald
  "#3b82f6", // blue
  "#f59e0b", // amber
  "#ef4444", // red
  "#8b5cf6", // violet
  "#ec4899", // pink
  "#14b8a6", // teal
  "#f97316", // orange
];

type TimeRange = "5m" | "15m" | "1h" | "6h" | "24h" | "7d" | "30d";

const TIME_RANGES: TimeRange[] = ["5m", "15m", "1h", "6h", "24h", "7d", "30d"];

/* ============================================================
 * Mock Data — Realistic with per-agent time series
 * ============================================================ */

// Generate a sinusoidal + noise time series
function makeTimeSeries(
  baseVal: number,
  amplitude: number,
  periodFactor: number,
  count: number,
  startEpoch: number,
  intervalSec: number,
  drift = 0,
): ApmMetricPoint[] {
  return Array.from({ length: count }, (_, i) => {
    const phase = (i / count) * Math.PI * 2 * periodFactor;
    const noise = (Math.random() - 0.5) * amplitude * 0.4;
    const driftVal = drift * (i / count);
    const raw = baseVal + Math.sin(phase) * amplitude * 0.6 + noise + driftVal;
    return {
      metric_name: "cpu_percent",
      value: Math.max(0, Math.min(100, raw)),
      sample_count: Math.floor(Math.random() * 10) + 1,
      bucket_epoch: startEpoch + i * intervalSec,
    };
  });
}

function getPointsForRange(range: TimeRange): { count: number; intervalSec: number } {
  switch (range) {
    case "5m":  return { count: 60,  intervalSec: 5 };
    case "15m": return { count: 60,  intervalSec: 15 };
    case "1h":  return { count: 60,  intervalSec: 60 };
    case "6h":  return { count: 72,  intervalSec: 300 };
    case "24h": return { count: 288, intervalSec: 300 };
    case "7d":  return { count: 168, intervalSec: 3600 };
    case "30d": return { count: 180, intervalSec: 14400 };
  }
}

interface AgentTimeSeries {
  cpu: ApmMetricPoint[];
  mem: ApmMetricPoint[];
  netSent: ApmMetricPoint[];
  netRecv: ApmMetricPoint[];
  load1: ApmMetricPoint[];
  load5: ApmMetricPoint[];
  load15: ApmMetricPoint[];
}

function generateAllMockSeries(range: TimeRange): Record<string, AgentTimeSeries> {
  const { count, intervalSec } = getPointsForRange(range);
  const startEpoch = Math.floor(Date.now() / 1000) - count * intervalSec;

  const agents = {
    "agent-001": {
      cpu:     makeTimeSeries(35,  25, 2,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(62,  15, 1.5, count, startEpoch, intervalSec),
      netSent: makeTimeSeries(450, 300, 3,  count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(820, 400, 2.5, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(1.2, 0.8, 2,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(1.1, 0.5, 1.5, count, startEpoch, intervalSec),
      load15:  makeTimeSeries(1.0, 0.3, 1,  count, startEpoch, intervalSec),
    },
    "agent-002": {
      cpu:     makeTimeSeries(72,  20, 3,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(78,  10, 1,   count, startEpoch, intervalSec, 7), // memory leak pattern
      netSent: makeTimeSeries(1200, 600, 4, count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(3400, 1200, 3, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(3.5, 1.5, 3,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(3.2, 0.8, 2,  count, startEpoch, intervalSec),
      load15:  makeTimeSeries(3.0, 0.4, 1,  count, startEpoch, intervalSec),
    },
    "agent-003": {
      cpu:     makeTimeSeries(88,  10, 2,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(78,  8,  1.5, count, startEpoch, intervalSec),
      netSent: makeTimeSeries(200, 100, 2,  count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(310, 120, 1.5, count, startEpoch, intervalSec),
      load1:   makeTimeSeries(4.8, 1.2, 2,  count, startEpoch, intervalSec),
      load5:   makeTimeSeries(4.5, 0.6, 1.5, count, startEpoch, intervalSec),
      load15:  makeTimeSeries(4.2, 0.3, 1,  count, startEpoch, intervalSec),
    },
    "agent-004": {
      cpu:     makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      mem:     makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      netSent: makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      netRecv: makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load1:   makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load5:   makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
      load15:  makeTimeSeries(0,   0,   1,   count, startEpoch, intervalSec),
    },
  };

  return agents;
}

const MOCK_AGENTS: ApmAgent[] = [
  {
    agent_id: "agent-001",
    hostname: "web-server-01",
    ip_address: "10.0.1.10",
    status: "running",
    os_info: "Ubuntu 22.04",
    last_seen: new Date(Date.now() - 15000).toISOString(),
    cpu_percent: 34.2,
    memory_percent: 61.8,
    disk_percent: 45.0,
  },
  {
    agent_id: "agent-002",
    hostname: "api-server-02",
    ip_address: "10.0.1.11",
    status: "running",
    os_info: "Ubuntu 22.04",
    last_seen: new Date(Date.now() - 30000).toISOString(),
    cpu_percent: 72.5,
    memory_percent: 85.3,
    disk_percent: 62.1,
  },
  {
    agent_id: "agent-003",
    hostname: "db-server-01",
    ip_address: "10.0.1.20",
    status: "degraded",
    os_info: "Debian 12",
    last_seen: new Date(Date.now() - 120000).toISOString(),
    cpu_percent: 91.3,
    memory_percent: 78.2,
    disk_percent: 88.7,
  },
  {
    agent_id: "agent-004",
    hostname: "cache-server-01",
    ip_address: "10.0.1.30",
    status: "offline",
    os_info: "CentOS 8",
    last_seen: new Date(Date.now() - 900000).toISOString(),
    cpu_percent: undefined,
    memory_percent: undefined,
    disk_percent: undefined,
  },
];

interface MockProcess {
  pid: number;
  name: string;
  cpu: number;
  mem: number;
  threads: number;
  status: string;
}

const MOCK_PROCESSES: MockProcess[] = [
  { pid: 1842, name: "postgres",       cpu: 42.1, mem: 28.3, threads: 18, status: "running" },
  { pid: 3201, name: "node",           cpu: 31.7, mem: 14.2, threads: 12, status: "running" },
  { pid: 4510, name: "nginx",          cpu: 18.3, mem: 3.1,  threads: 8,  status: "running" },
  { pid: 2340, name: "redis-server",   cpu: 12.8, mem: 6.7,  threads: 4,  status: "running" },
  { pid: 5901, name: "python3",        cpu: 9.4,  mem: 11.2, threads: 6,  status: "running" },
  { pid: 1120, name: "java",           cpu: 8.1,  mem: 35.8, threads: 24, status: "running" },
  { pid: 6230, name: "mysqld",         cpu: 5.6,  mem: 18.4, threads: 16, status: "running" },
  { pid: 2890, name: "ruby",           cpu: 4.2,  mem: 8.9,  threads: 3,  status: "running" },
  { pid: 7120, name: "mongod",         cpu: 3.8,  mem: 22.1, threads: 14, status: "running" },
  { pid: 3450, name: "go-server",      cpu: 2.9,  mem: 4.3,  threads: 8,  status: "running" },
  { pid: 8901, name: "elasticsearch",  cpu: 2.1,  mem: 41.2, threads: 20, status: "running" },
  { pid: 1560, name: "sshd",           cpu: 0.4,  mem: 0.8,  threads: 2,  status: "running" },
  { pid: 2001, name: "systemd",        cpu: 0.2,  mem: 1.1,  threads: 1,  status: "running" },
  { pid: 4780, name: "cron",           cpu: 0.1,  mem: 0.3,  threads: 1,  status: "sleeping" },
  { pid: 9012, name: "logrotate",      cpu: 0.0,  mem: 0.2,  threads: 1,  status: "sleeping" },
];

const MOCK_ALERTS: ApmAlert[] = [
  {
    id: "alert-001",
    severity: "CRITICAL",
    rule_name: "High CPU Usage",
    agent_id: "agent-003",
    metric_name: "cpu_percent",
    metric_value: 91.3,
    threshold: 90.0,
    fired_at: new Date(Date.now() - 300000).toISOString(),
  },
  {
    id: "alert-002",
    severity: "WARNING",
    rule_name: "High Memory Usage",
    agent_id: "agent-002",
    metric_name: "memory_usage_percent",
    metric_value: 85.3,
    threshold: 80.0,
    fired_at: new Date(Date.now() - 600000).toISOString(),
  },
  {
    id: "alert-003",
    severity: "WARNING",
    rule_name: "High Disk Usage",
    agent_id: "agent-003",
    metric_name: "disk_percent",
    threshold: 85.0,
    metric_value: 88.7,
    fired_at: new Date(Date.now() - 1200000).toISOString(),
  },
  {
    id: "alert-004",
    severity: "INFO",
    rule_name: "Agent Offline",
    agent_id: "agent-004",
    metric_name: "heartbeat",
    metric_value: 0,
    threshold: 1,
    fired_at: new Date(Date.now() - 900000).toISOString(),
  },
];

/* ============================================================
 * Helper functions
 * ============================================================ */

function metricColor(v: number | undefined, warn = 70, crit = 85): string {
  if (v === undefined) return "#64748b";
  if (v >= crit) return "#ef4444";
  if (v >= warn) return "#f59e0b";
  return "#10b981";
}

function statusDotColor(status: string): string {
  switch (status) {
    case "running":  return "#10b981";
    case "degraded": return "#f59e0b";
    case "offline":  return "#ef4444";
    default:         return "#64748b";
  }
}

function statusBadgeVariant(status: string): "green" | "yellow" | "red" | "default" {
  switch (status) {
    case "running":  return "green";
    case "degraded": return "yellow";
    case "offline":  return "red";
    default:         return "default";
  }
}

function severityBadgeVariant(severity: string): "red" | "yellow" | "default" {
  switch (severity) {
    case "CRITICAL": return "red";
    case "WARNING":  return "yellow";
    default:         return "default";
  }
}

function severityDotColor(severity: string): string {
  switch (severity) {
    case "CRITICAL": return "#ef4444";
    case "WARNING":  return "#f59e0b";
    default:         return "#3b82f6";
  }
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60)  return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60)  return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function formatBytes(val: number): string {
  if (val >= 1_000_000) return `${(val / 1_000_000).toFixed(1)} MB/s`;
  if (val >= 1_000)     return `${(val / 1_000).toFixed(1)} KB/s`;
  return `${val.toFixed(0)} B/s`;
}

function trendArrow(points: ApmMetricPoint[]): "up" | "down" | "stable" {
  if (points.length < 4) return "stable";
  const recent = points.slice(-4).reduce((s, p) => s + p.value, 0) / 4;
  const older  = points.slice(-8, -4).reduce((s, p) => s + p.value, 0) / 4;
  if (recent > older + 2) return "up";
  if (recent < older - 2) return "down";
  return "stable";
}

function trendPct(points: ApmMetricPoint[]): number {
  if (points.length < 8) return 0;
  const recent = points.slice(-4).reduce((s, p) => s + p.value, 0) / 4;
  const older  = points.slice(-8, -4).reduce((s, p) => s + p.value, 0) / 4;
  if (older === 0) return 0;
  return ((recent - older) / older) * 100;
}

/* ============================================================
 * Sparkline (30px tall inline SVG)
 * ============================================================ */

const Sparkline = memo(function Sparkline({
  points,
  color,
  width = 80,
  height = 30,
}: {
  points: number[];
  color: string;
  width?: number;
  height?: number;
}) {
  if (points.length < 2) return null;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const toX = (i: number) => (i / (points.length - 1)) * width;
  const toY = (v: number) => height - ((v - min) / range) * (height - 2) - 1;
  const d = points.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
  const areaD = `${d} L${toX(points.length - 1).toFixed(1)},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="shrink-0">
      <path d={areaD} fill={color} opacity={0.15} />
      <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
});

/* ============================================================
 * Progress bar
 * ============================================================ */

function ProgressBar({ value, warn = 70, crit = 85, width = "100%" }: {
  value: number | undefined;
  warn?: number;
  crit?: number;
  width?: string;
}) {
  const pct = Math.min(100, Math.max(0, value ?? 0));
  const color = metricColor(value, warn, crit);
  return (
    <div className="h-1.5 rounded-full bg-[#1e293b] overflow-hidden" style={{ width }}>
      <div
        className="h-full rounded-full transition-all"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  );
}

/* ============================================================
 * Multi-agent line chart (full panel)
 * ============================================================ */

interface ChartSeries {
  label: string;
  color: string;
  points: ApmMetricPoint[];
}

const MetricsPanel = memo(function MetricsPanel({
  title,
  series,
  unit = "%",
  yMax = 100,
}: {
  title: string;
  series: ChartSeries[];
  unit?: string;
  yMax?: number;
}) {
  const W = 560;
  const H = 140;
  const PAD = { top: 12, right: 12, bottom: 28, left: 42 };
  const cW = W - PAD.left - PAD.right;
  const cH = H - PAD.top - PAD.bottom;

  const allPoints = series.flatMap((s) => s.points.map((p) => p.value));
  const dynMax = allPoints.length > 0 ? Math.max(...allPoints, 1) : yMax;
  const effectiveMax = unit === "%" ? Math.max(dynMax, 10) : Math.max(dynMax, 1);

  const toX = (i: number, total: number) =>
    PAD.left + (total <= 1 ? cW / 2 : (i / (total - 1)) * cW);
  const toY = (v: number) =>
    PAD.top + cH - (v / effectiveMax) * cH;

  const gridVals = unit === "%"
    ? [0, 25, 50, 75, 100].filter((v) => v <= effectiveMax)
    : [0, effectiveMax * 0.25, effectiveMax * 0.5, effectiveMax * 0.75, effectiveMax];

  return (
    <div>
      <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2 font-medium">{title}</p>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
          {/* Grid */}
          {gridVals.map((val) => {
            const y = toY(val);
            if (y < PAD.top - 1) return null;
            return (
              <g key={val}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y} y2={y} stroke="#1e293b" strokeWidth={1} />
                <text x={PAD.left - 4} y={y + 3.5} textAnchor="end" fill="#475569" fontSize={8} fontFamily="monospace">
                  {unit === "%" ? `${Math.round(val)}%` : formatBytes(val)}
                </text>
              </g>
            );
          })}

          {/* Series */}
          {series.map((s) => {
            if (s.points.length < 2) return null;
            const d = s.points
              .map((p, i) => `${i === 0 ? "M" : "L"}${toX(i, s.points.length).toFixed(1)},${toY(p.value).toFixed(1)}`)
              .join(" ");
            const last = s.points[s.points.length - 1];
            const areaD = `${d} L${toX(s.points.length - 1, s.points.length).toFixed(1)},${(PAD.top + cH).toFixed(1)} L${PAD.left.toFixed(1)},${(PAD.top + cH).toFixed(1)} Z`;
            return (
              <g key={s.label}>
                <path d={areaD} fill={s.color} opacity={0.06} />
                <path d={d} fill="none" stroke={s.color} strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" />
                <circle
                  cx={toX(s.points.length - 1, s.points.length)}
                  cy={toY(last.value)}
                  r={2.5}
                  fill={s.color}
                  stroke="#111827"
                  strokeWidth={1.5}
                />
              </g>
            );
          })}

          {/* X-axis time labels */}
          {series[0]?.points && (() => {
            const pts = series[0].points;
            const idxs = [0, Math.floor(pts.length / 4), Math.floor(pts.length / 2), Math.floor((pts.length * 3) / 4), pts.length - 1];
            return idxs.map((idx) => {
              if (idx >= pts.length) return null;
              const d = new Date(pts[idx].bucket_epoch * 1000);
              const lbl = `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
              return (
                <text key={idx} x={toX(idx, pts.length)} y={H - 4} textAnchor="middle" fill="#475569" fontSize={8}>
                  {lbl}
                </text>
              );
            });
          })()}
        </svg>
      </div>
      {/* Legend */}
      {series.length > 1 && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
          {series.map((s) => (
            <div key={s.label} className="flex items-center gap-1.5 text-xs text-[#64748b]">
              <span className="w-2.5 h-0.5 rounded" style={{ backgroundColor: s.color, display: "inline-block" }} />
              {s.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});

/* ============================================================
 * Stat Card with sparkline
 * ============================================================ */

function StatCard({
  label,
  value,
  unit,
  sparkPoints,
  color,
  trend,
  trendPctVal,
  icon,
}: {
  label: string;
  value: string;
  unit: string;
  sparkPoints: number[];
  color: string;
  trend: "up" | "down" | "stable";
  trendPctVal: number;
  icon: React.ReactNode;
}) {
  const TrendIcon = trend === "up" ? ArrowUpRight : trend === "down" ? ArrowDownRight : Minus;
  const trendColorCls = trend === "up" ? "text-red-400" : trend === "down" ? "text-emerald-400" : "text-[#64748b]";
  return (
    <Card>
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs text-[#64748b] uppercase tracking-wider font-medium">{label}</p>
        <span className="text-[#64748b]">{icon}</span>
      </div>
      <div className="flex items-end justify-between gap-2">
        <div>
          <p className="text-2xl font-extrabold font-mono leading-none" style={{ color }}>
            {value}
            <span className="text-base font-normal text-[#64748b] ml-0.5">{unit}</span>
          </p>
          <div className={`flex items-center gap-0.5 mt-1 text-xs ${trendColorCls}`}>
            <TrendIcon size={11} />
            <span>{Math.abs(trendPctVal).toFixed(1)}%</span>
          </div>
        </div>
        <Sparkline points={sparkPoints} color={color} />
      </div>
    </Card>
  );
}

/* ============================================================
 * Infrastructure host card
 * ============================================================ */

function HostCard({
  agent,
  color,
  selected,
  onClick,
  seriesData,
}: {
  agent: ApmAgent;
  color: string;
  selected: boolean;
  onClick: () => void;
  seriesData?: AgentTimeSeries;
}) {
  const cpuPts = seriesData?.cpu.slice(-20).map((p) => p.value) ?? [];
  return (
    <div
      onClick={onClick}
      className={`rounded-lg border p-3 cursor-pointer transition-all ${
        selected
          ? "border-[#FFD700]/40 bg-[#FFD700]/5"
          : "border-[#1e293b] bg-[#111827] hover:border-[#334155]"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ backgroundColor: statusDotColor(agent.status) }}
          />
          <span className="font-semibold text-sm text-[#e2e8f0]">{agent.hostname}</span>
          <span className="text-xs text-[#64748b] font-mono">{agent.ip_address}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[#475569]">{agent.os_info}</span>
          {selected && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/20 font-medium">
              selected
            </span>
          )}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-3 mb-2">
        {[
          { label: "CPU", val: agent.cpu_percent, warn: 70, crit: 85 },
          { label: "MEM", val: agent.memory_percent, warn: 75, crit: 90 },
          { label: "DISK", val: agent.disk_percent, warn: 80, crit: 90 },
        ].map(({ label, val, warn, crit }) => (
          <div key={label}>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-[#64748b]">{label}</span>
              <span className="font-mono" style={{ color: metricColor(val, warn, crit) }}>
                {val !== undefined ? `${val.toFixed(0)}%` : "—"}
              </span>
            </div>
            <ProgressBar value={val} warn={warn} crit={crit} />
          </div>
        ))}
      </div>
      {cpuPts.length > 2 && (
        <div className="flex items-center gap-2">
          <Sparkline points={cpuPts} color={color} width={100} height={20} />
          <span className="text-xs text-[#475569]">CPU trend</span>
        </div>
      )}
    </div>
  );
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function ApmPage() {
  const locale = useLocale();
  const t = APM_DICT[(locale as ApmLocale)] ?? APM_DICT.en;

  const [agents, setAgents] = useState<ApmAgent[]>([]);
  const [alerts, setAlerts] = useState<ApmAlert[]>([]);
  const [allSeries, setAllSeries] = useState<Record<string, AgentTimeSeries>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>("1h");
  const [showSetup, setShowSetup] = useState(false);
  const [processSearch, setProcessSearch] = useState("");
  const [processSortKey, setProcessSortKey] = useState<"cpu" | "mem" | "pid" | "name" | "threads">("cpu");
  const [processSortAsc, setProcessSortAsc] = useState(false);
  const [acknowledgedAlerts, setAcknowledgedAlerts] = useState<Set<string>>(new Set());

  const loadData = useCallback(async (silent = false) => {
    if (silent) setRefreshing(true);
    else setLoading(true);
    try {
      let token: string | undefined;
      try {
        const session = localStorage.getItem("faultray_session");
        if (session) {
          const parsed = JSON.parse(session) as { access_token?: string };
          token = parsed.access_token;
        }
      } catch { /* ignore */ }

      const [agentsData, alertsData] = await Promise.all([
        api.getApmAgents(token),
        api.getApmAlerts(undefined, token),
      ]);
      if (agentsData.length > 0) {
        setAgents(agentsData);
        setAlerts(alertsData);
      } else {
        throw new Error("empty");
      }
    } catch {
      setAgents(MOCK_AGENTS);
      setAlerts(MOCK_ALERTS);
    } finally {
      const series = generateAllMockSeries(timeRange);
      setAllSeries(series);
      if (silent) setRefreshing(false);
      else setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Auto-refresh every 15s
  useEffect(() => {
    if (!autoRefresh) return;
    const id = setInterval(() => {
      void loadData(true);
    }, 15000);
    return () => clearInterval(id);
  }, [autoRefresh, loadData]);

  // Export
  const handleExport = useCallback(() => {
    const data = { agents, alerts, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "faultray-apm-export.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }, [agents, alerts]);

  // ── Computed stats ──
  const stats = useMemo(() => {
    const connected = agents.filter((a) => a.status !== "offline").length;
    const critical  = alerts.filter((a) => a.severity === "CRITICAL").length;
    const warning   = alerts.filter((a) => a.severity === "WARNING").length;
    const info      = alerts.filter((a) => a.severity === "INFO").length;
    const cpuVals   = agents.filter((a) => a.cpu_percent !== undefined).map((a) => a.cpu_percent!);
    const memVals   = agents.filter((a) => a.memory_percent !== undefined).map((a) => a.memory_percent!);
    const diskVals  = agents.filter((a) => a.disk_percent !== undefined).map((a) => a.disk_percent!);
    const avgCpu    = cpuVals.length  > 0 ? cpuVals.reduce((s, v)  => s + v, 0)  / cpuVals.length  : 0;
    const avgMem    = memVals.length  > 0 ? memVals.reduce((s, v)  => s + v, 0)  / memVals.length  : 0;
    const avgDisk   = diskVals.length > 0 ? diskVals.reduce((s, v) => s + v, 0)  / diskVals.length : 0;
    return { connected, total: agents.length, critical, warning, info, avgCpu, avgMem, avgDisk };
  }, [agents, alerts]);

  // ── Series for selected agent(s) ──
  const visibleAgentIds = useMemo(
    () => (selectedAgent ? [selectedAgent] : agents.map((a) => a.agent_id)),
    [selectedAgent, agents]
  );

  const cpuSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: agents.find((a) => a.agent_id === id)?.hostname ?? id,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.cpu ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const memSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: agents.find((a) => a.agent_id === id)?.hostname ?? id,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.mem ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const netSentSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: `${agents.find((a) => a.agent_id === id)?.hostname ?? id} ↑`,
      color: AGENT_COLORS[i % AGENT_COLORS.length],
      points: allSeries[id]?.netSent ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const netRecvSeries = useMemo<ChartSeries[]>(() =>
    visibleAgentIds.map((id, i) => ({
      label: `${agents.find((a) => a.agent_id === id)?.hostname ?? id} ↓`,
      color: AGENT_COLORS[(i + 1) % AGENT_COLORS.length],
      points: allSeries[id]?.netRecv ?? [],
    })),
    [visibleAgentIds, agents, allSeries]
  );

  const loadSeries = useMemo<ChartSeries[]>(() => {
    const firstId = visibleAgentIds[0] ?? "";
    const s = allSeries[firstId];
    if (!s) return [];
    return [
      { label: "load 1m",  color: "#10b981", points: s.load1  },
      { label: "load 5m",  color: "#3b82f6", points: s.load5  },
      { label: "load 15m", color: "#8b5cf6", points: s.load15 },
    ];
  }, [visibleAgentIds, allSeries]);

  // ── Sparkline data for stat cards ──
  const cpuSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.cpu.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  const memSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.mem.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  const netSparkAll = useMemo(() => {
    const merged: number[] = [];
    for (const id of visibleAgentIds) {
      const pts = allSeries[id]?.netSent.slice(-20) ?? [];
      pts.forEach((p, i) => { merged[i] = (merged[i] ?? 0) + p.value / visibleAgentIds.length; });
    }
    return merged;
  }, [visibleAgentIds, allSeries]);

  // ── Process table ──
  const sortedProcesses = useMemo(() => {
    const filtered = MOCK_PROCESSES.filter(
      (p) =>
        p.name.toLowerCase().includes(processSearch.toLowerCase()) ||
        String(p.pid).includes(processSearch)
    );
    return [...filtered].sort((a, b) => {
      const av = a[processSortKey] as number | string;
      const bv = b[processSortKey] as number | string;
      const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return processSortAsc ? cmp : -cmp;
    });
  }, [processSearch, processSortKey, processSortAsc]);

  const timeRangeLabel: Record<TimeRange, string> = {
    "5m":  t.last5m,
    "15m": t.last15m,
    "1h":  t.last1h,
    "6h":  t.last6h,
    "24h": t.last24h,
    "7d":  t.last7d,
    "30d": t.last30d,
  };

  /* ============================================================
   * Render
   * ============================================================ */

  if (loading) {
    return (
      <div className="max-w-[1400px] mx-auto px-6 py-10 flex items-center justify-center min-h-[60vh]">
        <div className="text-center">
          <RefreshCw size={32} className="animate-spin text-[#FFD700] mx-auto mb-4" />
          <p className="text-[#64748b]">Loading APM data...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 md:px-6 py-6 space-y-6">

      {/* ══ Top Bar ══════════════════════════════════════════════ */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Radio size={22} className="text-[#FFD700] shrink-0" />
          <div>
            <h1 className="text-xl font-bold leading-none">{t.title}</h1>
            <p className="text-xs text-[#64748b] mt-0.5">{t.subtitle}</p>
          </div>
          {/* auto-refresh indicator */}
          {autoRefresh && (
            <div className="flex items-center gap-1.5 ml-2 px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-xs text-emerald-400">
                {refreshing ? t.refreshing : t.autoRefresh}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Time range */}
          <div className="flex gap-0.5 bg-[#111827] border border-[#1e293b] rounded-lg p-0.5">
            {TIME_RANGES.map((r) => (
              <button
                key={r}
                onClick={() => setTimeRange(r)}
                className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                  timeRange === r
                    ? "bg-[#FFD700]/15 text-[#FFD700] border border-[#FFD700]/30"
                    : "text-[#64748b] hover:text-[#94a3b8]"
                }`}
              >
                {timeRangeLabel[r]}
              </button>
            ))}
          </div>

          {/* Agent selector */}
          <select
            value={selectedAgent ?? ""}
            onChange={(e) => setSelectedAgent(e.target.value || null)}
            className="bg-[#111827] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-[#e2e8f0] focus:outline-none focus:border-[#FFD700]/40"
          >
            <option value="">{t.allAgents}</option>
            {agents.map((a) => (
              <option key={a.agent_id} value={a.agent_id}>{a.hostname}</option>
            ))}
          </select>

          {/* Auto-refresh toggle */}
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
              autoRefresh
                ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                : "bg-[#111827] border-[#1e293b] text-[#64748b] hover:text-[#94a3b8]"
            }`}
          >
            {t.autoRefresh}
          </button>

          <Button variant="secondary" size="sm" onClick={() => void loadData(true)} disabled={refreshing}>
            <RefreshCw size={13} className={refreshing ? "animate-spin" : ""} />
            {t.refresh}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleExport}>
            <Download size={13} />
            {t.export}
          </Button>
        </div>
      </div>

      {/* ══ Section 1: Key Metric Stat Cards ═════════════════════ */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label={t.cpuUsage}
          value={stats.avgCpu.toFixed(1)}
          unit="%"
          sparkPoints={cpuSparkAll}
          color={metricColor(stats.avgCpu)}
          trend={trendArrow(cpuSeries[0]?.points ?? [])}
          trendPctVal={trendPct(cpuSeries[0]?.points ?? [])}
          icon={<Cpu size={15} />}
        />
        <StatCard
          label={t.memoryUsage}
          value={stats.avgMem.toFixed(1)}
          unit="%"
          sparkPoints={memSparkAll}
          color={metricColor(stats.avgMem, 75, 90)}
          trend={trendArrow(memSeries[0]?.points ?? [])}
          trendPctVal={trendPct(memSeries[0]?.points ?? [])}
          icon={<HardDrive size={15} />}
        />
        <StatCard
          label={t.diskUsage}
          value={stats.avgDisk.toFixed(1)}
          unit="%"
          sparkPoints={[]}
          color={metricColor(stats.avgDisk, 80, 90)}
          trend="stable"
          trendPctVal={0}
          icon={<Server size={15} />}
        />
        <StatCard
          label={t.networkIo}
          value={
            netSparkAll.length > 0
              ? ((netSparkAll[netSparkAll.length - 1] ?? 0) / 1000).toFixed(1)
              : "0.0"
          }
          unit=" KB/s"
          sparkPoints={netSparkAll}
          color="#3b82f6"
          trend={trendArrow(netSentSeries[0]?.points ?? [])}
          trendPctVal={trendPct(netSentSeries[0]?.points ?? [])}
          icon={<Network size={15} />}
        />
      </div>

      {/* ══ Section 2: Time Series Grid (2×2) ════════════════════ */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card>
          <MetricsPanel title={t.cpuUsage} series={cpuSeries} unit="%" yMax={100} />
        </Card>
        <Card>
          <MetricsPanel title={t.memoryUsage} series={memSeries} unit="%" yMax={100} />
        </Card>
        <Card>
          <MetricsPanel
            title={t.networkIo}
            series={[...netSentSeries, ...netRecvSeries]}
            unit="bytes"
            yMax={5000}
          />
        </Card>
        <Card>
          <MetricsPanel title={t.loadAverage} series={loadSeries} unit="load" yMax={10} />
        </Card>
      </div>

      {/* ══ Section 3: Infrastructure Map ════════════════════════ */}
      <Card>
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <Server size={15} className="text-[#FFD700]" />
          {t.infrastructureMap}
          <span className="text-xs text-[#64748b] font-normal">
            — {stats.connected}/{stats.total} {t.running.toLowerCase()}
          </span>
        </h3>
        <div className="grid md:grid-cols-2 gap-3">
          {agents.map((agent, i) => (
            <HostCard
              key={agent.agent_id}
              agent={agent}
              color={AGENT_COLORS[i % AGENT_COLORS.length]}
              selected={selectedAgent === agent.agent_id}
              onClick={() => setSelectedAgent(
                selectedAgent === agent.agent_id ? null : agent.agent_id
              )}
              seriesData={allSeries[agent.agent_id]}
            />
          ))}
        </div>
      </Card>

      {/* ══ Section 4: Process Table ══════════════════════════════ */}
      <Card>
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Activity size={15} className="text-[#FFD700]" />
            {t.processExplorer}
          </h3>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={processSearch}
              onChange={(e) => setProcessSearch(e.target.value)}
              placeholder={t.search}
              className="bg-[#0a0e1a] border border-[#1e293b] rounded-lg px-3 py-1.5 text-xs text-[#e2e8f0] placeholder:text-[#475569] focus:outline-none focus:border-[#FFD700]/30 w-40"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-[#1e293b]">
                {(
                  [
                    { key: "pid",     label: t.pid     },
                    { key: "name",    label: t.name    },
                    { key: "cpu",     label: "CPU%"    },
                    { key: "mem",     label: "MEM%"    },
                    { key: "threads", label: t.threads },
                    { key: null,      label: t.status  },
                  ] as Array<{ key: "pid" | "name" | "cpu" | "mem" | "threads" | null; label: string }>
                ).map(({ key, label }) => (
                  <th
                    key={label}
                    className={`py-2.5 px-2 text-left text-[#64748b] font-medium ${key ? "cursor-pointer hover:text-[#94a3b8] select-none" : ""}`}
                    onClick={() => {
                      if (!key) return;
                      if (processSortKey === key) setProcessSortAsc(!processSortAsc);
                      else { setProcessSortKey(key); setProcessSortAsc(false); }
                    }}
                  >
                    {label}
                    {processSortKey === key && (
                      <span className="ml-1 text-[#FFD700]">{processSortAsc ? "↑" : "↓"}</span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedProcesses.map((proc) => (
                <tr key={proc.pid} className="border-b border-[#1e293b]/40 hover:bg-white/[0.02] transition-colors">
                  <td className="py-2.5 px-2 font-mono text-[#64748b]">{proc.pid}</td>
                  <td className="py-2.5 px-2 font-medium text-[#e2e8f0]">{proc.name}</td>
                  <td className="py-2.5 px-2 font-mono" style={{ color: metricColor(proc.cpu, 50, 80) }}>
                    {proc.cpu.toFixed(1)}%
                  </td>
                  <td className="py-2.5 px-2 font-mono" style={{ color: metricColor(proc.mem, 20, 40) }}>
                    {proc.mem.toFixed(1)}%
                  </td>
                  <td className="py-2.5 px-2 font-mono text-[#94a3b8]">{proc.threads}</td>
                  <td className="py-2.5 px-2">
                    <span className={`text-xs ${proc.status === "running" ? "text-emerald-400" : "text-[#64748b]"}`}>
                      {proc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* ══ Section 5: Alert Timeline ════════════════════════════ */}
      <Card>
        <h3 className="text-sm font-bold mb-4 flex items-center gap-2">
          <AlertTriangle size={15} className="text-amber-400" />
          {t.alertTimeline}
          {alerts.length > 0 && (
            <Badge variant="red">{alerts.length}</Badge>
          )}
        </h3>

        {alerts.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-center gap-3">
            <CheckCircle size={36} className="text-emerald-400" />
            <p className="text-emerald-400 font-medium">{t.allClear}</p>
            <p className="text-xs text-[#64748b]">{t.noActiveAlerts}</p>
          </div>
        ) : (
          <div className="space-y-1">
            {alerts.map((alert) => {
              const acked = acknowledgedAlerts.has(alert.id);
              return (
                <div
                  key={alert.id}
                  className={`flex items-start gap-3 py-3 border-b border-[#1e293b]/50 last:border-0 transition-opacity ${acked ? "opacity-40" : ""}`}
                >
                  {/* Timeline dot */}
                  <div className="flex flex-col items-center mt-1 shrink-0">
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: severityDotColor(alert.severity) }}
                    />
                    <span className="w-px flex-1 bg-[#1e293b] mt-1" style={{ minHeight: 12 }} />
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={severityBadgeVariant(alert.severity)}>
                        {t[alert.severity.toLowerCase() as "critical" | "warning" | "info"] ?? alert.severity}
                      </Badge>
                      <span className="text-sm font-medium text-[#e2e8f0]">{alert.rule_name}</span>
                      <span className="text-xs text-[#64748b] font-mono">{alert.agent_id}</span>
                    </div>
                    <div className="flex items-center gap-3 mt-1 flex-wrap">
                      <span className="text-xs text-[#64748b]">
                        {alert.metric_name}:{" "}
                        <span style={{ color: severityDotColor(alert.severity) }}>
                          {alert.metric_value.toFixed(1)}
                        </span>
                        {" "}/ threshold {alert.threshold.toFixed(1)}
                      </span>
                      <span className="text-xs text-[#475569]">{formatRelative(alert.fired_at)}</span>
                    </div>
                  </div>

                  <button
                    onClick={() =>
                      setAcknowledgedAlerts((prev) => {
                        const next = new Set(prev);
                        if (next.has(alert.id)) next.delete(alert.id);
                        else next.add(alert.id);
                        return next;
                      })
                    }
                    className={`text-xs px-2.5 py-1 rounded border transition-colors shrink-0 ${
                      acked
                        ? "border-emerald-500/30 text-emerald-400 bg-emerald-500/10"
                        : "border-[#1e293b] text-[#64748b] hover:border-[#334155] hover:text-[#94a3b8]"
                    }`}
                  >
                    {acked ? "✓ Acked" : t.acknowledge}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ══ Section 6: Quick Setup (collapsible) ═════════════════ */}
      <Card className="border-[#FFD700]/10">
        <button
          onClick={() => setShowSetup(!showSetup)}
          className="w-full flex items-center justify-between"
        >
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Server size={14} className="text-[#FFD700]" />
            {t.quickSetup}
          </h3>
          {showSetup ? (
            <ChevronUp size={16} className="text-[#64748b]" />
          ) : (
            <ChevronDown size={16} className="text-[#64748b]" />
          )}
        </button>

        {showSetup && (
          <div className="mt-4 pt-4 border-t border-[#1e293b]">
            <p className="text-xs text-[#94a3b8] mb-4">{t.setupDescription}</p>
            <ol className="space-y-3">
              {[t.setupStep1, t.setupStep2, t.setupStep3, t.setupStep4].map((step, i) => (
                <li key={i} className="flex gap-3">
                  <span className="shrink-0 w-6 h-6 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 text-[#FFD700] text-xs flex items-center justify-center font-bold">
                    {i + 1}
                  </span>
                  <span className="text-xs text-[#94a3b8] pt-1">{step}</span>
                </li>
              ))}
            </ol>
          </div>
        )}
      </Card>
    </div>
  );
}
