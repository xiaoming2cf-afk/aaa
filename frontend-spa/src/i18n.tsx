import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

export type Language = "en" | "zh";

const LANGUAGE_KEY = "spa-language";

const en = {
  "app.brand": "ARBITER",
  "app.subtitle": "Research Ops Console",
  "app.legacyTools": "Legacy tools",
  "app.refreshAll": "Refresh All",
  "app.search": "Search workbench",
  "app.workspace": "Workspace",
  "app.team": "Team",
  "app.noTeam": "No team",
  "app.workspacePending": "Workspace pending",
  "app.noTeamSelected": "No team selected",
  "app.sessionExpired": "Session expired",
  "app.sessionExpiredDescription": "Open the login page and sign in again.",
  "app.returnToLogin": "Return to login",
  "nav.overview": "Overview",
  "nav.research": "Research",
  "nav.dataLab": "Data Lab",
  "nav.dataLabAgent": "Data Lab Agent",
  "nav.teamLibrary": "Team Library",
  "nav.knowledge": "Knowledge",
  "nav.providers": "Providers",
  "nav.quality": "Quality",
  "route.overview.eyebrow": "Workspace Command Center",
  "route.research.eyebrow": "Command Queue",
  "route.dataLab.eyebrow": "Workspace Data Lab",
  "route.dataLabAgent.eyebrow": "Analysis Runtime",
  "route.teamLibrary.eyebrow": "Published Artifacts",
  "route.knowledge.eyebrow": "Workspace Memory",
  "route.providers.eyebrow": "Operations Scope",
  "route.quality.eyebrow": "Delivery Control",
  "dataLab.title": "Data Lab",
  "dataLab.description": "Prepare datasets, run preflight checks, execute models, review results, optimize suites, and continue with the agent runtime.",
  "dataLab.dataset": "Dataset",
  "dataLab.preparation": "Preparation",
  "dataLab.model": "Model",
  "dataLab.results": "Results",
  "dataLab.history": "History",
  "dataLab.optimization": "Optimization",
  "dataLab.agent": "Agent",
  "dataLab.upload": "Upload dataset",
  "dataLab.selectDataset": "Select dataset",
  "dataLab.previewPreparation": "Preview preparation",
  "dataLab.savePrepared": "Save prepared dataset",
  "dataLab.variableGuide": "Variable guide",
  "dataLab.runGuide": "Run guide",
  "dataLab.preflight": "Run preflight",
  "dataLab.runModel": "Run model",
  "dataLab.runPlot": "Create plot",
  "dataLab.openResult": "Open result",
  "dataLab.preflightRequired": "Preflight required",
  "dataLab.manifest": "Reproducibility manifest",
  "dataLab.trustedDisabled": "Trusted execution disabled",
  "dataLab.notSandbox": "Data Lab Agent trusted Python execution is not a sandbox.",
  "dataLab.noWorkspace": "No workspace selected",
  "dataLab.noWorkspaceDescription": "Select a workspace before using Data Lab.",
  "dataLab.recentActivity": "Recent activity",
  "dataLab.catalog": "Catalog",
  "dataLab.profile": "Profile",
  "dataLab.previewRows": "Preview rows",
  "dataLab.resultDetail": "Result detail",
  "dataLab.optimizationSuite": "Optimization suite",
  "dataLab.agentContinuity": "Agent continuity",
  "dataLab.fileTypes": "CSV / XLSX / JSON",
  "dataLab.selectDatasetOption": "Select dataset",
  "dataLab.fileGuidance": "CSV, XLSX, XLS, or JSON. SVG remains forbidden.",
  "dataLab.uploadFailed": "Upload failed",
  "dataLab.prompt": "Prompt",
  "dataLab.guideEmpty": "Guide suggestions will appear here.",
  "dataLab.loadingProfile": "Loading profile",
  "dataLab.loadingProfileDescription": "Reading dataset schema and preview rows.",
  "dataLab.profileUnavailable": "Profile unavailable",
  "dataLab.noDatasetPreview": "No dataset preview",
  "dataLab.noDatasetPreviewDescription": "Upload or select a structured dataset.",
  "dataLab.rows": "Rows",
  "dataLab.columns": "Columns",
  "dataLab.candidateTargets": "Candidate targets",
  "dataLab.workflow": "Workflow",
  "dataLab.includeColumns": "Include columns",
  "dataLab.requiredColumns": "Required columns",
  "dataLab.numericColumns": "Numeric columns",
  "dataLab.dateColumns": "Date columns",
  "dataLab.imputeMethod": "Impute method",
  "dataLab.preparationOutput": "Preparation output",
  "dataLab.preparationEmpty": "Preview or saved preparation details will appear here.",
  "dataLab.processingWorkflow": "Processing workflow",
  "dataLab.family": "Family",
  "dataLab.method": "Method",
  "dataLab.dependent": "Dependent",
  "dataLab.independents": "Independents",
  "dataLab.controls": "Controls",
  "dataLab.seriesColumns": "Series columns",
  "dataLab.entityTime": "Entity / Time",
  "dataLab.timeColumn": "Time column",
  "dataLab.treatmentPost": "Treatment / Post",
  "dataLab.postColumn": "Post column",
  "dataLab.modelOutput": "Preflight / model output",
  "dataLab.modelOutputEmpty": "Run preflight before treating model output as reliable.",
  "dataLab.chart": "Chart",
  "dataLab.chartType": "Chart type",
  "dataLab.xColumn": "X column",
  "dataLab.yColumns": "Y columns",
  "dataLab.groupColumn": "Group column",
  "dataLab.titleLabel": "Title",
  "dataLab.plotEmpty": "Chart asset metadata will appear after creation.",
  "dataLab.noProfileWarnings": "No profile warnings loaded.",
  "dataLab.trustedExecution": "trusted_execution",
  "dataLab.sandboxClaim": "sandbox_claim",
  "dataLab.enabled": "enabled",
  "dataLab.disabled": "disabled",
  "dataLab.none": "none",
  "dataLab.unknown": "unknown",
  "dataLab.noActivity": "No activity yet",
  "dataLab.noActivityDescription": "Run a Data Lab workflow to populate this inspector.",
  "dataLab.noResults": "No results yet",
  "dataLab.noResultsDescription": "Run processing, model, or optimization workflows.",
  "dataLab.loadingResult": "Loading result",
  "dataLab.loadingResultDescription": "Fetching result detail and manifest.",
  "dataLab.resultEmpty": "Select a result to inspect coefficients, figures, tables, audit notes, and manifest.",
  "dataLab.manifestText": "Model and processing result details keep reproducibility metadata, input specification, audit notes, and export routes attached to the selected workspace item.",
  "dataLab.loadingHistory": "Loading history",
  "dataLab.loadingHistoryDescription": "Fetching processing, model, optimization, and agent activity.",
  "dataLab.historyUnavailable": "History unavailable",
  "dataLab.processing": "Processing",
  "dataLab.models": "Models",
  "dataLab.optimizationHistory": "Optimization history",
  "dataLab.agentSessions": "Agent Sessions",
  "dataLab.empty": "Empty",
  "dataLab.emptyBucketDescription": "No items in this bucket yet.",
  "dataLab.noSummary": "No summary recorded.",
  "dataLab.loadingCatalog": "Loading catalog",
  "dataLab.loadingCatalogDescription": "Fetching optimizer and benchmark inventory.",
  "dataLab.optimizers": "optimizers",
  "dataLab.functions": "functions",
  "dataLab.minimum": "minimum",
  "dataLab.suiteLabel": "Suite label",
  "dataLab.dimension": "Dimension",
  "dataLab.epoch": "Epoch",
  "dataLab.population": "Population",
  "dataLab.runs": "Runs",
  "dataLab.workers": "Workers",
  "dataLab.optimizationEmpty": "Optimization run summary appears here after execution.",
  "dataLab.noOptimizationResults": "No optimization results",
  "dataLab.noOptimizationResultsDescription": "Run a suite to populate history.",
  "dataLab.requestFailed": "Request failed",
  "dataLab.awaitingData": "Awaiting data",
} as const;

const zh: Record<keyof typeof en, string> = {
  "app.brand": "ARBITER",
  "app.subtitle": "研究工作台",
  "app.legacyTools": "旧版工具",
  "app.refreshAll": "刷新全部",
  "app.search": "搜索工作台",
  "app.workspace": "工作区",
  "app.team": "团队",
  "app.noTeam": "无团队",
  "app.workspacePending": "工作区待选择",
  "app.noTeamSelected": "未选择团队",
  "app.sessionExpired": "登录已过期",
  "app.sessionExpiredDescription": "请返回登录页重新登录。",
  "app.returnToLogin": "返回登录",
  "nav.overview": "总览",
  "nav.research": "研究",
  "nav.dataLab": "Data Lab",
  "nav.dataLabAgent": "Data Lab Agent",
  "nav.teamLibrary": "团队库",
  "nav.knowledge": "知识库",
  "nav.providers": "供应商",
  "nav.quality": "质量门禁",
  "route.overview.eyebrow": "工作区指挥中心",
  "route.research.eyebrow": "研究队列",
  "route.dataLab.eyebrow": "工作区 Data Lab",
  "route.dataLabAgent.eyebrow": "分析运行时",
  "route.teamLibrary.eyebrow": "已发布产物",
  "route.knowledge.eyebrow": "工作区记忆",
  "route.providers.eyebrow": "运行范围",
  "route.quality.eyebrow": "交付控制",
  "dataLab.title": "Data Lab",
  "dataLab.description": "准备数据集、执行预检、运行模型、审阅结果、优化套件，并继续进入 Agent 分析运行时。",
  "dataLab.dataset": "数据集",
  "dataLab.preparation": "数据准备",
  "dataLab.model": "模型",
  "dataLab.results": "结果",
  "dataLab.history": "历史",
  "dataLab.optimization": "优化",
  "dataLab.agent": "Agent",
  "dataLab.upload": "上传数据集",
  "dataLab.selectDataset": "选择数据集",
  "dataLab.previewPreparation": "预览准备",
  "dataLab.savePrepared": "保存准备后数据",
  "dataLab.variableGuide": "变量向导",
  "dataLab.runGuide": "运行向导",
  "dataLab.preflight": "运行预检",
  "dataLab.runModel": "运行模型",
  "dataLab.runPlot": "生成图表",
  "dataLab.openResult": "打开结果",
  "dataLab.preflightRequired": "必须先预检",
  "dataLab.manifest": "可复现清单",
  "dataLab.trustedDisabled": "可信执行已关闭",
  "dataLab.notSandbox": "Data Lab Agent 可信 Python 执行不是沙箱。",
  "dataLab.noWorkspace": "未选择工作区",
  "dataLab.noWorkspaceDescription": "使用 Data Lab 前请先选择工作区。",
  "dataLab.recentActivity": "近期活动",
  "dataLab.catalog": "目录",
  "dataLab.profile": "画像",
  "dataLab.previewRows": "预览行",
  "dataLab.resultDetail": "结果详情",
  "dataLab.optimizationSuite": "优化套件",
  "dataLab.agentContinuity": "Agent 连续性",
  "dataLab.fileTypes": "CSV / XLSX / JSON",
  "dataLab.selectDatasetOption": "选择数据集",
  "dataLab.fileGuidance": "支持 CSV、XLSX、XLS 或 JSON。SVG 仍然禁止上传。",
  "dataLab.uploadFailed": "上传失败",
  "dataLab.prompt": "提示词",
  "dataLab.guideEmpty": "向导建议会显示在这里。",
  "dataLab.loadingProfile": "正在加载画像",
  "dataLab.loadingProfileDescription": "正在读取数据集结构和预览行。",
  "dataLab.profileUnavailable": "画像不可用",
  "dataLab.noDatasetPreview": "暂无数据预览",
  "dataLab.noDatasetPreviewDescription": "请上传或选择结构化数据集。",
  "dataLab.rows": "行数",
  "dataLab.columns": "列数",
  "dataLab.candidateTargets": "候选目标",
  "dataLab.workflow": "工作流",
  "dataLab.includeColumns": "包含列",
  "dataLab.requiredColumns": "必需列",
  "dataLab.numericColumns": "数值列",
  "dataLab.dateColumns": "日期列",
  "dataLab.imputeMethod": "填补方法",
  "dataLab.preparationOutput": "准备输出",
  "dataLab.preparationEmpty": "预览或保存后的准备详情会显示在这里。",
  "dataLab.processingWorkflow": "处理工作流",
  "dataLab.family": "模型族",
  "dataLab.method": "方法",
  "dataLab.dependent": "因变量",
  "dataLab.independents": "自变量",
  "dataLab.controls": "控制变量",
  "dataLab.seriesColumns": "序列列",
  "dataLab.entityTime": "个体 / 时间",
  "dataLab.timeColumn": "时间列",
  "dataLab.treatmentPost": "处理 / 事后",
  "dataLab.postColumn": "事后列",
  "dataLab.modelOutput": "预检 / 模型输出",
  "dataLab.modelOutputEmpty": "请先运行预检，再把模型输出视为可靠。",
  "dataLab.chart": "图表",
  "dataLab.chartType": "图表类型",
  "dataLab.xColumn": "X 列",
  "dataLab.yColumns": "Y 列",
  "dataLab.groupColumn": "分组列",
  "dataLab.titleLabel": "标题",
  "dataLab.plotEmpty": "图表资产元数据会在创建后显示。",
  "dataLab.noProfileWarnings": "暂无画像警告。",
  "dataLab.trustedExecution": "可信执行",
  "dataLab.sandboxClaim": "沙箱声明",
  "dataLab.enabled": "已启用",
  "dataLab.disabled": "已关闭",
  "dataLab.none": "无",
  "dataLab.unknown": "未知",
  "dataLab.noActivity": "暂无活动",
  "dataLab.noActivityDescription": "运行 Data Lab 工作流后会填充这里。",
  "dataLab.noResults": "暂无结果",
  "dataLab.noResultsDescription": "请运行数据处理、模型或优化工作流。",
  "dataLab.loadingResult": "正在加载结果",
  "dataLab.loadingResultDescription": "正在获取结果详情和清单。",
  "dataLab.resultEmpty": "选择一个结果以查看系数、图形、表格、审计备注和清单。",
  "dataLab.manifestText": "模型和处理结果详情会保留可复现元数据、输入规格、审计备注以及与所选工作区项目关联的导出路径。",
  "dataLab.loadingHistory": "正在加载历史",
  "dataLab.loadingHistoryDescription": "正在获取处理、模型、优化和 Agent 活动。",
  "dataLab.historyUnavailable": "历史不可用",
  "dataLab.processing": "处理",
  "dataLab.models": "模型",
  "dataLab.optimizationHistory": "优化历史",
  "dataLab.agentSessions": "Agent 会话",
  "dataLab.empty": "空",
  "dataLab.emptyBucketDescription": "这个分组还没有项目。",
  "dataLab.noSummary": "未记录摘要。",
  "dataLab.loadingCatalog": "正在加载目录",
  "dataLab.loadingCatalogDescription": "正在获取优化器和基准函数目录。",
  "dataLab.optimizers": "优化器",
  "dataLab.functions": "函数",
  "dataLab.minimum": "最低要求",
  "dataLab.suiteLabel": "套件名称",
  "dataLab.dimension": "维度",
  "dataLab.epoch": "轮次",
  "dataLab.population": "种群",
  "dataLab.runs": "运行次数",
  "dataLab.workers": "并行数",
  "dataLab.optimizationEmpty": "优化运行摘要会在执行后显示。",
  "dataLab.noOptimizationResults": "暂无优化结果",
  "dataLab.noOptimizationResultsDescription": "运行一个套件后会填充历史。",
  "dataLab.requestFailed": "请求失败",
  "dataLab.awaitingData": "等待数据",
};

const inlineZh: Record<string, string> = {
  "Loading session": "正在加载会话",
  "Checking your research operations context.": "正在检查研究工作台上下文。",
  "Overview": "总览",
  "Workspace overview": "工作区总览",
  "No workspace selected": "未选择工作区",
  "Open a workspace or sign in before starting private research work.": "开始私有研究前，请先打开工作区或登录。",
  "Open workspace": "打开工作区",
  "Sign in": "登录",
  "Choose the next research action.": "选择下一步研究动作。",
  "New research run": "新建研究任务",
  "Start agent session": "启动 Agent 会话",
  "Workspace count": "工作区数量",
  "Team count": "团队数量",
  "Current workspace": "当前工作区",
  "Team context": "团队上下文",
  "Research": "研究",
  "Start, review, and continue focused research runs.": "启动、审查并继续聚焦的研究任务。",
  "Open research": "打开研究",
  "Prepare structured datasets, run checks, and inspect outputs.": "准备结构化数据集、运行检查并查看输出。",
  "Keep notes, literature records, and reusable context close to the work.": "把笔记、文献记录和可复用上下文保存在工作流附近。",
  "Open knowledge": "打开知识库",
  "Quality": "质量",
  "Check delivery readiness and review status before publishing.": "发布前检查交付准备度和审查状态。",
  "Open quality": "打开质量页",
  "Agent execution remains separate.": "Agent 执行保持独立。",
  "Data Lab Agent trusted execution is separate from the normal workspace and should remain disabled unless authorized.": "Data Lab Agent 的可信执行独立于普通工作区，除非获得授权，否则应保持关闭。",
  "Use the standard Data Lab flow for structured dataset preparation, model checks, and result review.": "请使用标准 Data Lab 流程完成结构化数据准备、模型检查和结果审查。",
  "Need the legacy cockpit?": "需要旧版工作台？",
  "The legacy workspace remains available for older workflows while the SPA workbench evolves.": "SPA 工作台持续演进时，旧版工作区仍可用于旧流程。",
  "Open legacy workspace": "打开旧版工作区",
  "Run Composer": "任务编排器",
  "Research Run": "研究任务",
  "Delivery gate passed.": "交付门禁已通过。",
  "Delivery gate blocks publication until review reaches 100%.": "审查达到 100% 前，交付门禁会阻止发布。",
  "Workspace Deliverable": "工作区可交付",
  "Score": "分数",
  "Drafts": "草稿",
  "Topic": "主题",
  "Question": "问题",
  "Instructions": "说明",
  "Mode": "模式",
  "Draft Variants": "草稿变体",
  "Inflation persistence": "通胀持续性",
  "What explains inflation persistence?": "什么解释了通胀持续性？",
  "Start Run": "启动任务",
  "Research runtime unavailable": "研究运行时不可用",
  "Checking research runtime availability.": "正在检查研究运行时可用性。",
  "Research runtime status could not be verified; run creation is blocked.": "无法验证研究运行时状态，已阻止创建任务。",
  "Research runtime is available.": "研究运行时可用。",
  "Research generation is disabled in this deployment.": "此部署已禁用研究生成。",
  "Checking": "检查中",
  "Ready": "就绪",
  "Unavailable": "不可用",
  "Monitoring": "监控",
  "Live Run Queue": "实时任务队列",
  "Queued and active jobs stay in polling until saved, blocked, or failed.": "排队和运行中的任务会持续轮询，直到保存、阻止或失败。",
  "Runs": "任务数",
  "Recent runs could not load": "无法加载最近任务",
  "No research runs yet": "暂无研究任务",
  "Start a run to populate monitoring, quality review, and publish controls.": "启动任务后会填充监控、质量审查和发布控制。",
  "queue unknown": "队列未知",
  "stage unknown": "阶段未知",
  "unknown": "未知",
  "Untitled run": "未命名任务",
  "Waiting for reviewer summary.": "等待审查摘要。",
  "Trace": "追踪",
  "Run Detail": "任务详情",
  "Citation": "引用",
  "Unsupported": "无支持声明",
  "Review Precision": "审查精度",
  "Run detail could not load": "无法加载任务详情",
  "Run Status": "任务状态",
  "Queue": "队列",
  "Publish Gate": "发布门禁",
  "OPEN": "开启",
  "Evidence": "证据",
  "Review": "审查",
  "Final Report": "最终报告",
  "Run": "任务",
  "Stage": "阶段",
  "Attachments": "附件",
  "Publish gate open": "发布门禁已开启",
  "Publish gate is unknown": "发布门禁未知",
  "Publication blocked": "发布被阻止",
  "This run can be published to the selected team library.": "此任务可发布到选定团队库。",
  "Publish gate state is unknown until delivery review returns a current result.": "发布门禁需等待交付审查返回当前结果。",
  "The delivery review has not yet reached 100%.": "交付审查尚未达到 100%。",
  "Delivery Review": "交付审查",
  "No reviewer summary has been persisted yet.": "尚未保存审查摘要。",
  "ARBITER Candidates": "ARBITER 候选",
  "No selection-level ARBITER trace was persisted for this run.": "此任务未保存选择级 ARBITER 追踪。",
  "Selection v2": "选择 v2",
  "No reviewer summary.": "暂无审查摘要。",
  "No candidate-level ARBITER traces were persisted for this run.": "此任务未保存候选级 ARBITER 追踪。",
  "No final report persisted yet.": "尚未保存最终报告。",
  "Retry Instructions": "重试说明",
  "Retry Writer/Reviewer": "重试写作/审查",
  "Team": "团队",
  "Select team": "选择团队",
  "Publish to Team Library": "发布到团队库",
  "Publish is blocked": "发布被阻止",
  "Retry failed": "重试失败",
  "Publish failed": "发布失败",
  "No run selected": "未选择任务",
  "Select a run to inspect evidence, review, trace, and final report.": "选择任务以查看证据、审查、追踪和最终报告。",
  "Data Lab Agent Session": "Data Lab Agent 会话",
  "Show a concise overview of this dataset.": "简要概览这个数据集。",
  "Notebook download is ready.": "Notebook 下载已就绪。",
  "Preparing notebook export.": "正在准备 Notebook 导出。",
  "Notebook download is not prepared.": "Notebook 下载尚未准备。",
  "Select a session before preparing a notebook export.": "准备 Notebook 导出前请先选择会话。",
  "fresh export": "新导出",
  "session artifact": "会话产物",
  "awaiting export": "等待导出",
  "none": "无",
  "Trusted Python execution is separate from the normal workspace and is not a sandbox.": "可信 Python 执行独立于普通工作区，且不是沙箱。",
  "loading": "加载中",
  "no session": "无会话",
  "configured": "已配置",
  "disabled": "已关闭",
  "unset": "未设置",
  "ready": "就绪",
  "not ready": "未就绪",
  "fallback": "回退",
  "not run": "未运行",
  "Runtime boundary": "运行边界",
  "Trusted execution enabled": "可信执行已启用",
  "Trusted execution disabled": "可信执行已关闭",
  "production guidance": "生产建议",
  "keep disabled": "保持关闭",
  "Session and dataset browser": "会话与数据集浏览器",
  "Message workspace": "消息工作区",
  "Trace, notebook, and dataset inspector": "追踪、Notebook 与数据集检查器",
  "Composer": "编写器",
  "Manual Intervention Draft": "人工介入草稿",
  "Agent Instruction": "Agent 指令",
  "Human intervention is required before the agent can continue cleanly.": "Agent 要继续干净执行前需要人工介入。",
  "Send a prompt or provide a reviewed Python override.": "发送提示词，或提供已审查的 Python 覆盖代码。",
  "Human intervention required": "需要人工介入",
  "Review code": "审查代码",
  "Automated repair could not complete this cell.": "自动修复无法完成此单元。",
  "Edit Failed Code": "编辑失败代码",
  "Retry Last Prompt": "重试上次提示",
  "Instruction": "指令",
  "Execution Mode": "执行模式",
  "Session default": "会话默认",
  "Trusted subprocess replay": "可信子进程重放",
  "Auto dual mode": "自动双模式",
  "IPython kernel": "IPython 内核",
  "Trusted state": "可信状态",
  "Explicit mode selected; review server policy before running.": "已选择显式模式；运行前请审查服务器策略。",
  "Session default; approval state is unknown until run.": "会话默认；运行前审批状态未知。",
  "Manual code override": "人工代码覆盖",
  "Optional Python code for human intervention.": "用于人工介入的可选 Python 代码。",
  "Human note": "人工备注",
  "Why this manual code is being used.": "说明为何使用这段人工代码。",
  "Run Manual Code": "运行人工代码",
  "Run Message": "运行消息",
  "Clear Draft": "清空草稿",
  "Generate Report": "生成报告",
  "Dataset Context": "数据集上下文",
  "No dataset selected": "未选择数据集",
  "Session profile details appear after a dataset is attached.": "附加数据集后会显示会话画像详情。",
  "Rows": "行数",
  "Columns": "列数",
  "Warnings": "警告",
  "Profile guidance": "画像建议",
  "PROFILED": "已画像",
  "UNKNOWN": "未知",
  "Suggested targets": "建议目标",
  "Candidate features": "候选特征",
  "Fingerprint": "指纹",
  "Quality warnings": "质量警告",
  "NONE": "无",
  "No major quality warnings detected in the initial profile.": "初始画像未发现主要质量警告。",
  "No profile has been returned for this session yet.": "此会话尚未返回画像。",
  "Profile Preview": "画像预览",
  "Raw profile": "原始画像",
  "Notebook": "Notebook",
  "Data Lab inspector": "Data Lab 检查器",
  "Trace, notebook, and dataset tabs": "追踪、Notebook 与数据集标签",
  "LLM Config": "LLM 配置",
  "Scoped Model Settings": "作用域模型设置",
  "Load Stored": "加载已保存",
  "Test": "测试",
  "Save LLM Config": "保存 LLM 配置",
  "Workspace": "工作区",
  "Environment": "环境",
  "Resolved": "已解析",
  "Trusted execution boundary": "可信执行边界",
  "Enable scoped LLM": "启用作用域 LLM",
  "Base URL": "Base URL",
  "API Key": "API 密钥",
  "Stored Key": "已存密钥",
  "Keep stored key": "保留已存密钥",
  "Clear stored key": "清除已存密钥",
  "Label": "标签",
  "Coder Model": "编码模型",
  "Reviewer Model": "审查模型",
  "Report Model": "报告模型",
  "Optional for local gateways": "本地网关可选",
  "Stored; leave blank to keep": "已保存；留空表示保留",
  "Workspace-scoped agent config": "工作区作用域 Agent 配置",
  "Message Timeline": "消息时间线",
  "No session selected": "未选择会话",
  "Conversation, execution outputs, artifacts, repair traces, and knowledge context.": "会话、执行输出、产物、修复追踪和知识上下文。",
  "Agent session could not load": "无法加载 Agent 会话",
  "No messages yet": "暂无消息",
  "Use the composer to send the first instruction for this session.": "使用编写器发送此会话的第一条指令。",
  "Create or select a session to start the Data Lab Agent loop.": "创建或选择会话以启动 Data Lab Agent 循环。",
  "Request failed": "请求失败",
  "Notebook Export": "Notebook 导出",
  "Evidence Package": "证据包",
  "Preparing Notebook": "正在准备 Notebook",
  "Prepare Notebook": "准备 Notebook",
  "Download Notebook": "下载 Notebook",
  "Permalink": "永久链接",
  "Export": "导出",
  "Prepared": "已准备",
  "In progress": "进行中",
  "Pending": "待处理",
  "No session": "无会话",
  "Source": "来源",
  "Notebook artifact": "Notebook 产物",
  "No notebook artifact is available yet.": "暂无 Notebook 产物。",
  "Prepare Notebook creates the current export; Download Notebook appears only when the export path is available.": "准备 Notebook 会创建当前导出；只有导出路径可用时才显示下载入口。",
  "Session History": "会话历史",
  "Agent Sessions": "Agent 会话",
  "Reopen a previous run or follow a deep-linked session.": "重新打开历史任务或进入深链会话。",
  "Agent sessions could not load": "无法加载 Agent 会话",
  "No agent sessions yet": "暂无 Agent 会话",
  "Create a session to begin the analysis loop.": "创建会话以开始分析循环。",
  "Open the session to inspect messages and cells.": "打开会话以检查消息和单元。",
  "Session Launch": "会话启动",
  "Start Analysis Session": "启动分析会话",
  "Launch an agent session against a registered dataset while keeping trusted execution explicit.": "针对已登记数据集启动 Agent 会话，同时显式保持可信执行边界。",
  "Open Session Link": "打开会话链接",
  "Trusted mode notice": "可信模式提示",
  "Requires approval": "需要审批",
  "Python execution can read files and use network access available to the server process. Keep trusted execution disabled unless the deployment, datasets, and users are approved for local code execution.": "Python 执行可以读取文件并使用服务器进程可用的网络访问。除非部署、数据集和用户均已获准执行本地代码，否则请保持可信执行关闭。",
  "Unknown, blocked, or unverified execution states are treated as not approved; they are never shown as passed.": "未知、阻止或未验证的执行状态均视为未批准，绝不会显示为通过。",
  "Session Title": "会话标题",
  "Select dataset": "选择数据集",
  "Dataset browser": "数据集浏览器",
  "SELECTED": "已选",
  "DATASET": "数据集",
  "Create Session": "创建会话",
  "Feature flag required: DATA_LAB_AGENT_ENABLED=true.": "需要功能开关：DATA_LAB_AGENT_ENABLED=true。",
  "Datasets could not load": "无法加载数据集",
  "No datasets available": "暂无可用数据集",
  "Upload or register a dataset asset before creating a Data Lab Agent session.": "创建 Data Lab Agent 会话前，请先上传或登记数据集资产。",
  "Trace Panel": "追踪面板",
  "Runtime Evidence": "运行证据",
  "Session state, executor mode, LLM routing, safety events, notebook/report artifacts, and ARBITER state.": "会话状态、执行器模式、LLM 路由、安全事件、Notebook/报告产物和 ARBITER 状态。",
  "Executor": "执行器",
  "LLM": "LLM",
  "Cells": "单元",
  "Safety": "安全",
  "Session routing": "会话路由",
  "Latest assistant": "最近助手",
  "RECORDED": "已记录",
  "ARBITER v2 state": "ARBITER v2 状态",
  "Recent failures": "最近失败",
  "Raw ARBITER state": "原始 ARBITER 状态",
  "Safety events": "安全事件",
  "No safety events recorded for this session.": "此会话未记录安全事件。",
  "Select a session to inspect safety events.": "选择会话以检查安全事件。",
  "Report": "报告",
  "AVAILABLE": "可用",
  "NOT GENERATED": "未生成",
  "Generate Report creates a markdown report for the selected session.": "生成报告会为所选会话创建 Markdown 报告。",
  "Generated Report": "生成的报告",
  "Workspace Notes": "工作区笔记",
  "Create Knowledge Record": "创建知识记录",
  "Capture a reviewed workspace note before it moves through the publish gate.": "在通过发布门禁前，先记录一条已审查的工作区笔记。",
  "Title": "标题",
  "Content": "内容",
  "Save Knowledge": "保存知识",
  "Knowledge records can be published into the team library after review.": "知识记录通过审查后可发布到团队库。",
  "Knowledge record was not saved": "知识记录未保存",
  "Publishing Control": "发布控制",
  "Review Gate": "审查门禁",
  "Workspace active": "工作区已激活",
  "No workspace": "无工作区",
  "Records stay in workspace scope until the delivery review allows publication.": "交付审查允许发布前，记录会保留在工作区范围内。",
  "Team target": "团队目标",
  "Select the active team in the shared app scope before publishing to the Team Library.": "发布到团队库前，请在共享应用范围内选择当前团队。",
  "Knowledge Base": "知识库",
  "Records": "记录",
  "Publication status is read from the delivery review gate; blocked rows keep their first recorded reason visible.": "发布状态来自交付审查门禁；被阻止的行会保留首个记录原因。",
  "Blocked": "已阻止",
  "Loading knowledge records": "正在加载知识记录",
  "Fetching workspace notes and publication gate metadata.": "正在获取工作区笔记和发布门禁元数据。",
  "Knowledge records could not load": "无法加载知识记录",
  "The knowledge API did not return records for this workspace.": "知识 API 未返回此工作区记录。",
  "Retry records": "重试记录",
  "No knowledge records yet": "暂无知识记录",
  "Create a workspace note or publish reviewed research to build the knowledge base.": "创建工作区笔记或发布已审查研究，以构建知识库。",
  "Document": "文档",
  "Publication": "发布",
  "Metadata": "元数据",
  "Gate": "门禁",
  "Action": "操作",
  "Knowledge record was not published": "知识记录未发布",
  "Publish is allowed.": "允许发布。",
  "Publish is blocked until delivery review reaches 100%.": "交付审查达到 100% 前阻止发布。",
  "score pending": "分数待定",
  "ID": "ID",
  "Updated": "更新",
  "Publish": "发布",
  "Team selected": "已选择团队",
  "Library Rules": "团队库规则",
  "Publication Boundary": "发布边界",
  "Read-only library": "只读团队库",
  "Published artifacts are not edited in place from this page.": "已发布产物不会在此页面原地编辑。",
  "Workspace clone target": "工作区克隆目标",
  "Clone to Workspace keeps source metadata so the copied knowledge record can be reviewed again.": "克隆到工作区会保留来源元数据，便于再次审查复制的知识记录。",
  "Artifacts": "产物",
  "selected": "已选择",
  "Published Artifacts": "已发布产物",
  "Team Library": "团队库",
  "Select a team before loading published artifacts.": "加载已发布产物前请选择团队。",
  "No team selected": "未选择团队",
  "Choose or create a team to browse published records.": "选择或创建团队以浏览已发布记录。",
  "Loading team library": "正在加载团队库",
  "Fetching published records for the selected team.": "正在获取所选团队的已发布记录。",
  "Team library could not load": "无法加载团队库",
  "The selected team library API did not return published artifacts.": "所选团队库 API 未返回已发布产物。",
  "Retry library": "重试团队库",
  "No published records yet": "暂无已发布记录",
  "Publish a reviewed knowledge record before the team library can serve reusable artifacts.": "先发布已审查的知识记录，团队库才会提供可复用产物。",
  "Artifact": "产物",
  "Status": "状态",
  "Published": "已发布",
  "No summary recorded.": "未记录摘要。",
  "Run not recorded": "未记录任务",
  "Source record not recorded": "未记录来源记录",
  "Workspace metadata not recorded": "未记录工作区元数据",
  "Clone to Workspace": "克隆到工作区",
  "Team Model": "团队模型",
  "Create or Select Team": "创建或选择团队",
  "Choose the team whose published artifacts should be browsed, or create a new read-only publication target.": "选择要浏览其已发布产物的团队，或创建新的只读发布目标。",
  "Current Team": "当前团队",
  "New Team Name": "新团队名称",
  "Description": "描述",
  "Create Team": "创建团队",
  "Publishing remains manual. Team library stays read-only until cloned back to a workspace.": "发布仍为手动操作。团队库保持只读，直到克隆回工作区。",
  "Team was not created": "团队未创建",
  "Current scope only": "仅当前范围",
  "Unavailable Surface": "不可用页面",
  "Runtime Provider Management Is Disabled": "运行时供应商管理已禁用",
  "This page documents the boundary of the current product build; it is not a provider operations dashboard.": "此页面说明当前产品版本的边界；它不是供应商运维仪表盘。",
  "Management": "管理",
  "Runtime health": "运行时健康",
  "not exposed": "未暴露",
  "Selected": "已选择",
  "Missing": "缺失",
  "No workspace selected.": "未选择工作区。",
  "Current scope": "当前范围",
  "Restricted": "受限",
  "This product build keeps research runs, review gates, publishing, knowledge capture, and team library workflows. Runtime provider management is not available in the current product scope, and the product does not expose model-provider setup, runtime health, or bundle operations.": "此产品版本保留研究任务、审查门禁、发布、知识捕获和团队库流程。当前产品范围不包含运行时供应商管理，也不暴露模型供应商设置、运行时健康或打包操作。",
  "Restricted capabilities": "受限能力",
  "Model-provider setup is not available here.": "此处不提供模型供应商设置。",
  "Runtime health checks are not exposed here.": "此处不暴露运行时健康检查。",
  "Bundle operations are not available here.": "此处不提供打包操作。",
  "Operating boundary": "运行边界",
  "Provider status cannot be inferred from this page. Treat all runtime-provider management as out of scope for this build.": "不能从此页面推断供应商状态。请将所有运行时供应商管理视为超出当前版本范围。",
  "Where to work instead": "替代工作入口",
  "Use Research for queued runs, Quality for business-quality review, and Team Library for publication.": "使用研究页处理排队任务，使用质量页做业务质量审查，使用团队库发布。",
  "Next check": "下一项检查",
  "Surface": "页面",
  "Expected state": "预期状态",
  "Research generation": "研究生成",
  "Confirm queued runs and runtime availability there.": "在那里确认排队任务和运行时可用性。",
  "Publication gate": "发布门禁",
  "Confirm business score and engineering gate before publishing.": "发布前确认业务分数和工程门禁。",
  "Published artifacts": "已发布产物",
  "Browse records after explicit publication.": "显式发布后浏览记录。",
  "Quality Radar": "质量雷达",
  "Publication is allowed only when the business score reaches 500/500 and the engineering gate is fully green.": "只有业务分数达到 500/500 且工程门禁完全通过时才允许发布。",
  "Quality score": "质量分数",
  "Business gate": "业务门禁",
  "Engineering gate": "工程门禁",
  "No blocking reasons recorded.": "未记录阻止原因。",
  "Gate state is unknown until the quality API returns a current scorecard.": "质量 API 返回当前记分卡前，门禁状态未知。",
  "Business": "业务",
  "Engineering": "工程",
  "Not known": "未知",
  "Checking delivery status": "正在检查交付状态",
  "Loading business and engineering gate results for this workspace.": "正在加载此工作区的业务和工程门禁结果。",
  "Delivery status unavailable": "交付状态不可用",
  "Retry scorecard": "重试记分卡",
  "Select a workspace before reading quality delivery gates.": "读取质量交付门禁前，请先选择工作区。",
  "Gate Matrix": "门禁矩阵",
  "Each gate stays blocked or unknown until its own source reports a pass.": "各门禁在自身来源报告通过前保持阻止或未知。",
  "No scorecard dimensions yet": "暂无记分卡维度",
  "Run quality scoring to populate delivery dimensions and checks.": "运行质量评分以填充交付维度和检查。",
  "Checks": "检查",
  "Engineering Gate": "工程门禁",
  "No engineering checks returned.": "未返回工程检查。",
  "Gate matrix unavailable": "门禁矩阵不可用",
  "Quality unavailable states are reported as UNKNOWN, never PASS.": "质量不可用状态显示为 UNKNOWN，绝不显示 PASS。",
  "Delivery Mini Trend": "交付迷你趋势",
  "Recent delivery posteriors and choices from the ARBITER delivery layer.": "ARBITER 交付层最近的后验概率和选择。",
  "Latest posterior": "最新后验概率",
  "V2 samples": "V2 样本",
  "Choices": "选择",
  "No ARBITER trend yet": "暂无 ARBITER 趋势",
  "Recent delivery posteriors will appear after reviewed runs persist ARBITER metadata.": "已审查任务保存 ARBITER 元数据后，会显示最近交付后验概率。",
  "Recent Snapshots": "最近快照",
  "Recent Snapshots Table": "最近快照表",
  "Persisted run-level quality outcomes for recent research jobs.": "最近研究任务保存的任务级质量结果。",
  "Snapshots": "快照",
  "Loading quality snapshots": "正在加载质量快照",
  "Fetching recent persisted run outcomes.": "正在获取最近保存的任务结果。",
  "Quality snapshots could not load": "无法加载质量快照",
  "Retry snapshots": "重试快照",
  "No quality snapshots yet": "暂无质量快照",
  "Run research jobs first. Quality scoring is based on persisted run outcomes.": "请先运行研究任务。质量评分基于已保存的任务结果。",
  "Blocker": "阻止原因",
  "No blocking reason recorded.": "未记录阻止原因。",
};

const translations: Record<Language, Record<string, string>> = {
  en,
  zh: {
    ...zh,
    ...inlineZh,
  },
};

type TranslationKey = keyof typeof en | keyof typeof inlineZh;

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  toggleLanguage: () => void;
  t: (key: TranslationKey | string) => string;
  tx: (value: string) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);
const ORIGINAL_TEXT = new WeakMap<Text, string>();
const ORIGINAL_ATTRS = new WeakMap<Element, Map<string, string>>();
const SKIP_SELECTOR = "script, style, code, pre, textarea, [data-i18n-skip]";
const TRANSLATABLE_ATTRIBUTES = ["aria-label", "placeholder", "title"] as const;
let isApplyingDomTranslation = false;

function initialLanguage(): Language {
  const stored = localStorage.getItem(LANGUAGE_KEY);
  return stored === "zh" || stored === "en" ? stored : "zh";
}

function translateInlineText(value: string, language: Language): string {
  const match = value.match(/^(\s*)(.*?)(\s*)$/s);
  const leading = match?.[1] || "";
  const core = match?.[2] || "";
  const trailing = match?.[3] || "";
  if (!core) {
    return value;
  }
  if (language === "en") {
    return value;
  }
  const exact = translations.zh[core];
  if (exact) {
    return `${leading}${exact}${trailing}`;
  }
  const dynamic = translateDynamicText(core);
  return dynamic ? `${leading}${dynamic}${trailing}` : value;
}

function translateDynamicText(value: string): string {
  const currentWorkspace = value.match(/^Current workspace: (.+)\. Choose the next research action\. Your workspace keeps runs, datasets, notes, and quality checks together\.$/);
  if (currentWorkspace) {
    return `当前工作区：${currentWorkspace[1]}。请选择下一步研究动作。工作区会统一保存任务、数据集、笔记和质量检查。`;
  }
  const workspace = value.match(/^Workspace: (.+)$/);
  if (workspace) {
    return `工作区：${workspace[1]}`;
  }
  const teamContext = value.match(/^Team context: (.+)$/);
  if (teamContext) {
    return `团队上下文：${teamContext[1]}`;
  }
  const runtimeCode = value.match(/^Runtime code: (.+)$/);
  if (runtimeCode) {
    return `运行时代码：${runtimeCode[1]}`;
  }
  const rowsColumns = value.match(/^(.+) rows, (.+) columns\.$/);
  if (rowsColumns) {
    return `${rowsColumns[1]} 行，${rowsColumns[2]} 列。`;
  }
  const source = value.match(/^Source: (.+)$/);
  if (source) {
    return `来源：${source[1]}`;
  }
  const artifact = value.match(/^Artifact: (.+)$/);
  if (artifact) {
    return `产物：${artifact[1]}`;
  }
  const run = value.match(/^Run (.+)$/);
  if (run) {
    return `任务 ${run[1]}`;
  }
  const record = value.match(/^Record (.+)$/);
  if (record) {
    return `记录 ${record[1]}`;
  }
  const workspaceMeta = value.match(/^Workspace (.+)$/);
  if (workspaceMeta) {
    return `工作区 ${workspaceMeta[1]}`;
  }
  const published = value.match(/^Browsing published artifacts for (.+)\.$/);
  if (published) {
    return `正在浏览 ${published[1]} 的已发布产物。`;
  }
  return "";
}

function isSkipped(node: Node): boolean {
  const element = node.nodeType === Node.ELEMENT_NODE ? node as Element : node.parentElement;
  return Boolean(element?.closest(SKIP_SELECTOR));
}

function originalAttributeMap(element: Element): Map<string, string> {
  const existing = ORIGINAL_ATTRS.get(element);
  if (existing) {
    return existing;
  }
  const next = new Map<string, string>();
  ORIGINAL_ATTRS.set(element, next);
  return next;
}

function translateTextNode(node: Text, language: Language): void {
  if (!node.nodeValue?.trim() || isSkipped(node)) {
    return;
  }
  const current = node.nodeValue;
  const stored = ORIGINAL_TEXT.get(node);
  const translatedStored = stored ? translateInlineText(stored, language) : "";
  if (!stored || (current !== stored && current !== translatedStored)) {
    ORIGINAL_TEXT.set(node, current);
  }
  const original = ORIGINAL_TEXT.get(node) || current;
  const translated = translateInlineText(original, language);
  if (node.nodeValue !== translated) {
    node.nodeValue = translated;
  }
}

function translateElementAttributes(element: Element, language: Language): void {
  if (isSkipped(element)) {
    return;
  }
  const originals = originalAttributeMap(element);
  TRANSLATABLE_ATTRIBUTES.forEach((attr) => {
    const current = element.getAttribute(attr);
    if (!current) {
      return;
    }
    const stored = originals.get(attr);
    const translatedStored = stored ? translateInlineText(stored, language) : "";
    if (!stored || (current !== stored && current !== translatedStored)) {
      originals.set(attr, current);
    }
    const original = originals.get(attr) || current;
    const translated = translateInlineText(original, language);
    if (element.getAttribute(attr) !== translated) {
      element.setAttribute(attr, translated);
    }
  });
}

function applyDomTranslation(language: Language): void {
  if (typeof document === "undefined" || isApplyingDomTranslation) {
    return;
  }
  const root = document.getElementById("root");
  if (!root) {
    return;
  }
  isApplyingDomTranslation = true;
  try {
    root.querySelectorAll("*").forEach((element) => translateElementAttributes(element, language));
    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode(node) {
          return node.nodeValue?.trim() && !isSkipped(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
        },
      },
    );
    while (walker.nextNode()) {
      translateTextNode(walker.currentNode as Text, language);
    }
  } finally {
    isApplyingDomTranslation = false;
  }
}

export function I18nProvider({ children }: { children: ReactNode }): JSX.Element {
  const [language, setLanguage] = useState<Language>(initialLanguage);

  useEffect(() => {
    localStorage.setItem(LANGUAGE_KEY, language);
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  useEffect(() => {
    applyDomTranslation(language);
    const root = document.getElementById("root");
    if (!root) {
      return undefined;
    }
    const observer = new MutationObserver(() => {
      if (!isApplyingDomTranslation) {
        applyDomTranslation(language);
      }
    });
    observer.observe(root, {
      attributes: true,
      attributeFilter: [...TRANSLATABLE_ATTRIBUTES],
      characterData: true,
      childList: true,
      subtree: true,
    });
    return () => observer.disconnect();
  }, [language]);

  const value = useMemo<I18nContextValue>(() => ({
    language,
    setLanguage,
    toggleLanguage: () => setLanguage((current) => current === "zh" ? "en" : "zh"),
    t: (key) => translations[language][key as TranslationKey] || translations.en[key as TranslationKey] || key,
    tx: (text) => translateInlineText(text, language),
  }), [language]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("i18n context is unavailable.");
  }
  return value;
}
