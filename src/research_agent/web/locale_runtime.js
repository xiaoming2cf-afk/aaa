(() => {
  const LOCALE_KEY = "erp.ui.locale";
  const SUPPORTED_LOCALES = new Set(["en", "zh-CN"]);
  const SWITCHER_HOSTS = [
    ".home-nav__links",
    ".workspace-header__nav",
    ".module-app-bar__actions",
    ".lab-app-bar__actions",
    ".suite-page-head__actions",
    ".suite-page-kpis",
  ];
  const SKIP_SELECTOR = [
    "script",
    "style",
    "textarea",
    "code",
    "pre",
    "[data-i18n-skip]",
    "#public-latest-view",
    "#public-summary-view",
  ].join(", ");

  const titleStrings = {
    "Economic Research Platform": "经济研究平台",
    "Workspace | Economic Research Platform": "工作区 | 经济研究平台",
    "Provider Center | Economic Research Platform": "供应商中心 | 经济研究平台",
    "Paper Library | Economic Research Platform": "论文库 | 经济研究平台",
    "Knowledge Base | Economic Research Platform": "知识库 | 经济研究平台",
    "Schedules | Economic Research Platform": "日程任务 | 经济研究平台",
    "Data Lab | Economic Research Platform": "数据实验室 | 经济研究平台",
    "Data Lab Optimization | Economic Research Platform": "优化实验室 | 经济研究平台",
    "Data Lab Method Detail | Economic Research Platform": "数据实验室方法族详情 | 经济研究平台",
    "Data Lab Model Method | Economic Research Platform": "数据实验室模型方法 | 经济研究平台",
    "Data Lab Result | Economic Research Platform": "数据实验室结果 | 经济研究平台",
    "Data Lab Teaching Page | Economic Research Platform": "数据实验室教学页 | 经济研究平台",
    "Optimization Result | Data Lab | Economic Research Platform": "优化结果 | 数据实验室 | 经济研究平台",
    "Public Daily Monitor | Economic Research Platform": "公共日报监测 | 经济研究平台",
    "Research Agent | Economic Research Platform": "研究 Agent | 经济研究平台",
    "Provider Center Unavailable": "供应商中心不可用",
    "United States | Public Daily Monitor": "美国 | 公共日报监测",
    "China | Public Daily Monitor": "中国 | 公共日报监测",
    "Developed Markets | Public Daily Monitor": "发达市场 | 公共日报监测",
  };

  const commonStrings = {
    "Research Terminal": "研究终端",
    "Public briefing first. Private workspace after sign-in.": "先读公共简报，再进入私有工作区。",
    "Read the daily macro edition in public, then continue in a workspace that keeps providers, papers, Data Lab outputs, notes, and schedules aligned.": "先在公共区域阅读每日宏观简报，再进入工作区，让供应商、论文、数据实验室结果、笔记和日程保持一致。",
    "Edition": "版本",
    "Platform": "平台",
    "Digest": "摘要",
    "Access": "访问",
    "Public + Private": "公共 + 私有",
    "Macro pulse": "宏观脉冲",
    "Rates regime": "利率状态",
    "Risk tone": "风险情绪",
    "Tracking": "跟踪中",
    "Scanning": "扫描中",
    "Neutral": "中性",
    "Read current briefing": "阅读当前简报",
    "Open private workspace": "打开私有工作区",
    "Public briefing": "公共简报",
    "Providers": "供应商",
    "Knowledge": "知识",
    "Home": "首页",
    "Workspace": "工作区",
    "Data Lab": "数据实验室",
    "Optimization": "优化",
    "Knowledge Base": "知识库",
    "Provider Center": "供应商中心",
    "Paper Library": "论文库",
    "Schedules": "日程任务",
    "Daily Monitor": "日报监测",
    "Navigation": "导航",
    "Navigate": "导航",
    "Status": "状态",
    "Results": "结果",
    "History": "历史",
    "Model": "模型",
    "Preparation": "准备",
    "Workflow": "流程",
    "Run": "运行",
    "Methods": "方法",
    "Inputs": "输入",
    "Outputs": "输出",
    "Preview": "预览",
    "Metrics": "指标",
    "Interpretation": "解释",
    "Specification": "设定",
    "Source": "来源",
    "Figures": "图形",
    "Tables": "表格",
    "Routes": "路径",
    "Source": "来源",
    "Profile": "画像",
    "Setup": "设置",
    "Catalog": "目录",
    "Explorer": "浏览器",
    "Builder": "构建器",
    "Validation": "校验",
    "Access Control": "访问控制",
    "Current view": "当前视图",
    "Current Workspace": "当前工作区",
    "Current state": "当前状态",
    "Recent activity": "近期活动",
    "Next action": "下一步动作",
    "Open workbench": "打开工作台",
    "Open in workbench": "在工作台中打开",
    "Open detail": "打开详情",
    "Open detail page": "打开详情页",
    "Open source page": "打开来源页面",
    "Open source PDF": "打开来源 PDF",
    "Method page": "方法页面",
    "Back to Data Lab": "返回数据实验室",
    "Back to Optimization Lab": "返回优化实验室",
    "Manage workspaces": "管理工作区",
    "Open Knowledge Base": "打开知识库",
    "Open Provider Center": "打开供应商中心",
    "Open Paper Library": "打开论文库",
    "Open Data Lab": "打开数据实验室",
    "Open summary": "打开摘要",
    "Read current briefing": "阅读当前简报",
    "Private": "私有",
    "Ready": "就绪",
    "Locked": "已锁定",
    "Loading latest edition": "正在加载最新版本",
    "Loading...": "加载中...",
    "Sign out": "退出登录",
    "Sign in": "登录",
    "Log in": "登录",
    "Register": "注册",
    "Email": "邮箱",
    "Password": "密码",
    "Full name": "姓名",
    "Primary": "主导航",
    "Homepage hero": "首页头图区",
    "Edition status": "版本状态",
    "Signal summary": "信号摘要",
    "Private workspace": "私有工作区",
    "Workspace navigation": "工作区导航",
    "Provider sections": "供应商分区",
    "Knowledge sections": "知识分区",
    "Paper Library sections": "论文库分区",
    "Schedule sections": "日程分区",
    "Data Lab sections": "数据实验室分区",
  };

  Object.assign(commonStrings, {
    "Review workspace state, recent activity, next actions, and module entry points from a single private cockpit.": "查看工作区状态、近期活动、下一步和模块入口。",
    "Configure provider connections, test credentials, and manage workspace defaults for model and data access.": "配置供应商连接、测试凭证并管理工作区默认项。",
    "Search literature, import papers and PDFs, and route findings into the active research workspace.": "搜索文献、导入论文与 PDF，并将结果接入当前工作区。",
    "Capture private notes, manage case workspaces, and connect research outputs inside the current workspace.": "记录私有笔记、管理案例工作区，并在当前工作区内连接研究结果。",
    "Read the public daily monitor, inspect source panels and review queues, and follow rolling macro summaries.": "阅读公共日报监测、查看来源面板与审核队列，并跟踪滚动宏观摘要。",
    "Manage recurring jobs, review upcoming runs, and keep automated research tasks aligned with the active workspace.": "管理定时任务、查看即将运行的作业，并让自动化研究任务与当前工作区保持一致。",
    "Select a dataset, inspect the profile, and prepare the input set for Data Lab workflows.": "选择数据集、查看画像，并为 Data Lab 流程准备输入集。",
    "Choose a preparation workflow, tune the current template, and run data processing on the active dataset.": "选择准备流程、调整当前模板，并在当前数据集上执行数据处理。",
    "Configure models and chart runs, then execute analysis against the currently selected dataset.": "配置模型和图表运行，然后对当前选中的数据集执行分析。",
    "Review the latest processing and model outputs, inspect charts, and export result packages.": "查看最新处理与模型输出、检查图表，并导出结果包。",
    "Browse recent preparation and model runs, then reopen the relevant result pages for review.": "浏览近期准备与模型运行，然后重新打开相关结果页进行复核。",
    "Run optimization suites, review validation settings, and inspect result history for the active workspace.": "运行优化套件、查看校验设置，并检查当前工作区的结果历史。",
    "Read a Data Lab result package, review metrics and narrative output, and export supporting artifacts.": "阅读 Data Lab 结果包、查看指标与叙述输出，并导出配套产物。",
    "Inspect method detail, assumptions, and controlled configuration for the selected Data Lab family.": "查看所选 Data Lab 家族的方法细节、假设和受控配置。",
    "Review model method references, supported variants, and implementation notes for the current Data Lab route.": "查看当前 Data Lab 路由的方法参考、支持变体和实现说明。",
    "Read the teaching notes for a Data Lab method without leaving the current private research flow.": "在不离开当前私有研究流程的情况下阅读 Data Lab 方法教学说明。",
    "Review optimization result summaries, exported figures, and validation details for the selected run.": "查看所选运行的优化结果摘要、导出图表和校验细节。",
  });

  const authStrings = {
    "Private Workspace": "私有工作区",
    "Sign in for the private workspace": "登录以进入私有工作区",
    "Public reading stays open. Private modules unlock after sign-in.": "公共阅读始终开放，登录后解锁私有模块。",
    "Signed out": "未登录",
    "Signed in": "已登录",
    "Register or sign in to unlock the private modules.": "注册或登录以解锁私有模块。",
    "Create account": "创建账户",
    "Password (8+ characters)": "密码（至少 8 位）",
    "Password (12+ characters)": "密码（至少 12 位）",
    "Forgot password": "忘记密码",
    "Password reset": "重置密码",
    "Send reset link": "发送重置链接",
    "Set new password": "设置新密码",
    "Reset password": "重置密码",
    "Workspace Ready": "工作区已就绪",
    "No workspace selected": "未选择工作区",
    "Open the workspace cockpit to switch workspaces and continue private research.": "打开工作区驾驶舱以切换工作区并继续私有研究。",
    "Open workspace cockpit": "打开工作区驾驶舱",
    "Restoring session": "正在恢复会话",
    "A saved session is being restored. Private modules will appear once the refresh completes.": "正在恢复已保存会话，刷新完成后私有模块将出现。",
    "Register or sign in to access the private workspace.": "注册或登录以访问私有工作区。",
    "Return to the homepage to sign in, then come back to continue.": "请先返回首页登录，再回来继续。",
    "Restoring private workspace": "正在恢复私有工作区",
    "A saved session was found. Restoring the private workspace now.": "检测到已保存会话，正在恢复私有工作区。",
    "Sign in to access private workspace": "登录以访问私有工作区",
    "Read the public briefing first, then sign in to enter the private research workspace.": "先阅读公共简报，再登录进入私有研究工作区。",
    "Return to the homepage to sign in, then come back here to continue in the private workspace.": "返回首页登录，然后回到这里继续使用私有工作区。",
    "Workspace ready": "工作区已就绪",
    "Your session is active. Continue into the private workspace for providers, papers, schedules, and notes.": "当前会话已激活，可继续进入私有工作区处理供应商、论文、日程和笔记。",
    "You are signed in. Select a workspace and continue across the private modules without changing context.": "你已登录。选择工作区后，可在各私有模块之间保持上下文连续工作。",
    "Sign in to open": "登录后打开",
    "Open module": "打开模块",
    "Open the private workspace to switch workspaces, connect providers, and manage research assets.": "打开私有工作区以切换工作区、连接供应商并管理研究资产。",
    "Private workspace ready for providers, papers, notes, and schedules.": "私有工作区已就绪，可用于供应商、论文、笔记和日程。",
  };

  const moduleStrings = {
    "Workspace Cockpit": "工作区驾驶舱",
    "Run the current workspace.": "运行当前工作区。",
    "Check state, recent movement, and the next useful action.": "查看当前状态、近期变化和下一步最有价值的动作。",
    "Workspace session": "工作区会话",
    "Select the active workspace, then jump into the next module.": "先确认当前工作区，再跳转到下一个模块。",
    "Sign in from the homepage to continue.": "请从首页登录后继续。",
    "Active Workspace": "当前工作区",
    "Select or create": "选择或创建",
    "New workspace name": "新工作区名称",
    "Description (optional)": "描述（可选）",
    "Create workspace": "创建工作区",
    "Cockpit": "驾驶舱",
    "Read this page fast": "快速浏览本页",
    "State, next action, and recent movement live here. Module work stays on dedicated pages.": "这里集中展示状态、下一步动作和近期动态，模块工作在各自页面完成。",
    "Sign in to begin": "登录后开始",
    "Private cockpit data appears after authentication.": "认证后将显示私有驾驶舱数据。",
    "Workspace state": "工作区状态",
    "Flow": "流程",
    "Immediate next steps": "立即可做的下一步",
    "Linkage Map": "联动地图",
    "Cross-module map": "跨模块地图",
    "See how providers, papers, Data Lab output, and notes connect inside the current workspace.": "查看供应商、论文、数据实验室结果和笔记如何在当前工作区中联动。",
    "Research Flow": "研究流程",
    "Private connections": "私有连接",
    "Connect model and data providers": "连接模型与数据供应商",
    "Save provider setup, connection tests, and defaults inside the current workspace.": "在当前工作区内保存供应商配置、连接测试和默认项。",
    "Provider workflow": "供应商流程",
    "Confirm the workspace, save a connection, test it, then reuse it elsewhere.": "先确认工作区，再保存连接、测试连接，并在其他模块复用。",
    "Saved connections": "已保存连接",
    "Add connection": "添加连接",
    "Review inventory": "查看清单",
    "Providers are saved per workspace. Confirm it here, then move into setup or testing.": "供应商配置按工作区保存。先在这里确认，再继续进行设置或测试。",
    "Use the active workspace to save, test, and reuse provider connections.": "使用当前工作区来保存、测试并复用供应商连接。",
    "Switch workspace here. Create new ones from the cockpit.": "在此切换工作区。可在驾驶舱中新建工作区。",
    "Connection setup": "连接设置",
    "Save credentials, choose a default when needed, and keep connection settings attached to the current workspace.": "保存凭证、按需设置默认项，并让连接配置附着在当前工作区。",
    "No private provider connections yet.": "暂无私有供应商连接。",
    "Create or update connection": "创建或更新连接",
    "Choose a provider preset, then override the model or base URL only when needed.": "先选择供应商预设，仅在必要时覆盖模型或基础 URL。",
    "Connection label": "连接标签",
    "Default model (optional)": "默认模型（可选）",
    "Base URL for compatible providers": "兼容供应商的基础 URL",
    "API key": "API 密钥",
    "Open official docs": "打开官方文档",
    "Set as default connection": "设为默认连接",
    "Save connection": "保存连接",
    "Data Source": "数据源",
    "Search, import, and connect literature": "搜索、导入并连接文献",
    "Run OpenAlex search, import private PDF copies, and route papers into notes or cases.": "执行 OpenAlex 搜索、导入私有 PDF 副本，并把论文流转到笔记或案例。",
    "Literature workflow": "文献流程",
    "Search first, then import records, PDFs, and follow-up notes into the selected workspace.": "先搜索，再将记录、PDF 和后续笔记导入所选工作区。",
    "Search results": "搜索结果",
    "Imported library": "已导入文库",
    "Run search": "执行搜索",
    "Open imported papers": "打开已导入论文",
    "Search economics literature, for example: monetary policy transmission": "搜索经济学文献，例如：monetary policy transmission",
    "Use the active workspace for paper imports, private PDFs, and follow-up notes.": "使用当前工作区处理论文导入、私有 PDF 和后续笔记。",
    "Notes + cases + summaries": "笔记 + 案例 + 摘要",
    "Store notes, cases, and research summaries": "存储笔记、案例和研究摘要",
    "Use this page as the private record layer for papers, briefings, datasets, model outputs, and case files.": "将此页作为论文、简报、数据集、模型结果和案例文件的私有记录层。",
    "Knowledge workflow": "知识流程",
    "Use cases as containers, then create or filter notes and route outputs back into them.": "以案例作为容器，然后创建或筛选笔记，并将结果回流其中。",
    "Case workspace": "案例工作区",
    "Private notes": "私有笔记",
    "Related outputs": "相关结果",
    "Open cases": "打开案例",
    "Open notes": "打开笔记",
    "Notes, cases, and linked output all stay inside the current workspace.": "笔记、案例和关联结果都保留在当前工作区内。",
    "Use the active workspace for notes, case files, summaries, and linked outputs.": "使用当前工作区处理笔记、案例文件、摘要和关联结果。",
    "Case title": "案例标题",
    "Tags, comma separated": "标签，逗号分隔",
    "Describe the case scope, research question, and intended linked materials": "描述案例范围、研究问题和计划关联的材料",
    "Search title, body, citation, or tags": "搜索标题、正文、引文或标签",
    "Record title": "记录标题",
    "Write your research note or internal summary": "撰写研究笔记或内部摘要",
    "Recurring jobs": "定期任务",
    "Run recurring research tasks": "运行定期研究任务",
    "Use schedules as a narrow execution surface for recurring briefings and repeatable research jobs.": "将日程作为定期简报和可重复研究任务的执行入口。",
    "Define a recurring focus, save a schedule, and monitor upcoming runs inside the active workspace.": "定义定期关注主题、保存日程，并在当前工作区内监控即将执行的任务。",
    "Create job": "创建任务",
    "Upcoming runs": "即将执行",
    "New schedule": "新建日程",
    "Review jobs": "查看任务",
    "Recurring jobs are attached to one workspace at a time. Confirm it here before creating or reviewing jobs.": "定期任务一次只附着于一个工作区。请在创建或查看任务前先在此确认。",
    "Use the active workspace for recurring briefings and repeatable research jobs.": "使用当前工作区处理定期简报和可重复研究任务。",
    "Job name": "任务名称",
    "Daily focus topic": "每日关注主题",
    "Latest public edition, source review, and rolling summary": "最新公共版本、来源复核与滚动摘要",
    "Use this surface to read the public edition first, then inspect sources, moderation queues, and multi-day summaries.": "先在此阅读公共版本，再检查来源、审核队列和多日摘要。",
    "Latest edition": "最新版本",
    "Source panel": "来源面板",
    "Review queue": "审核队列",
    "Rolling summary": "滚动摘要",
    "News clusters": "新闻聚类",
    "Reading": "阅读",
    "Recent editions": "最近版本",
    "Copy share link": "复制分享链接",
    "Open summary": "打开摘要",
    "The edition is public, but moderation access and linked follow-up work still depend on the workspace selected here.": "该版本对公众开放，但审核权限和关联后续工作仍依赖这里选择的工作区。",
    "Use the active workspace for moderation access and linked follow-up work.": "使用当前工作区处理审核权限和关联后续工作。",
    "Loading current edition...": "正在加载当前版本...",
    "Waiting for the latest public briefing...": "正在等待最新公共简报...",
    "Edition switcher": "版本切换器",
    "Edition body": "版本正文",
    "Loading the latest public briefing...": "正在加载最新公共简报...",
    "Sources": "来源",
    "Inspect source mix, geography, credibility, and filtering logic before you interpret the edition signal.": "在解读版本信号前，先检查来源结构、地域分布、可信度和筛选逻辑。",
    "Priority View": "优先视图",
    "All Sources": "全部来源",
    "Source Type": "来源类型",
    "All Types": "全部类型",
    "Dataset workspace": "数据集工作台",
    "Move from dataset intake to preparation, estimation, and result review inside one continuous research workbench.": "在一个连续研究工作台内，从数据集接入推进到准备、估计与结果复核。",
    "Workbench": "工作台",
    "Start with the active dataset, then move through preparation, modeling, results, and history without leaving the shell.": "从当前数据集开始，无需离开页面即可继续完成准备、建模、结果和历史查看。",
    "Open optimization suite": "打开优化套件",
    "Inspect dataset": "查看数据集",
    "Dataset intake": "数据集接入",
    "Dataset": "数据集",
    "Load a source, inspect the profile, and clarify variable roles before you prepare or estimate anything.": "在进行任何准备或估计前，先加载数据源、检查画像，并明确变量角色。",
    "Load source": "加载来源",
    "Upload a new file or reopen a workspace dataset.": "上传新文件或重新打开工作区中的数据集。",
    "Inspect profile": "检查画像",
    "Check rows, columns, missingness, and preview records.": "检查行列、缺失情况和预览记录。",
    "Route": "路线",
    "Set the route": "设定路线",
    "Ask for variable guidance, then move into preparation or model design.": "先获取变量建议，再进入准备或模型设计。",
    "Dataset Upload": "数据集上传",
    "Choose a file for this workspace": "为此工作区选择文件",
    "CSV, XLSX, XLS, JSON, PDF, TXT, MD. Drag here or click to browse.": "支持 CSV、XLSX、XLS、JSON、PDF、TXT、MD。可拖拽到此或点击浏览。",
    "Asset description (optional)": "资产描述（可选）",
    "Upload file": "上传文件",
    "Dataset Profile": "数据集画像",
    "Choose a structured dataset to inspect variables and sample quality.": "选择一个结构化数据集以检查变量和样本质量。",
    "Load profile": "加载画像",
    "Select a dataset asset": "选择一个数据集资产",
    "Select a dataset to inspect rows, missingness, variable roles, and preview records.": "选择一个数据集以检查行数、缺失、变量角色和预览记录。",
    "Dataset preview will appear here after you load a profile.": "加载画像后，这里将显示数据集预览。",
    "Need help with variables?": "需要变量帮助吗？",
    "Describe the research question and let the guide suggest workflow, variables, and manual checks.": "描述研究问题，让向导建议流程、变量和人工核查项。",
    "Example: I want to study whether a policy increased firm exports after 2020, controlling for firm size and leverage.": "例如：我想研究一项政策在控制企业规模和杠杆后，是否提升了 2020 年后的企业出口。",
    "Suggest variables and model": "建议变量与模型",
    "Apply to workbench": "应用到工作台",
    "Load a dataset profile first, then describe the research question.": "请先加载数据集画像，再描述研究问题。",
    "No beginner guidance has been generated yet.": "尚未生成入门引导。",
    "Run Summary": "运行摘要",
    "Method Summary": "方法摘要",
    "Family Detail": "族详情",
    "Method Family Detail": "方法族详情",
    "Review the family first, then reopen the workbench with the right workflow and family already selected.": "先查看方法族，再用已预选好流程和方法族的状态重新打开工作台。",
    "Family sections": "方法族分区",
    "Model Method": "模型方法",
    "Loading model method...": "正在加载模型方法...",
    "Model family": "模型家族",
    "Equation exposed": "公式已显示",
    "Method Document": "方法文档",
    "Model Method Detail": "模型方法详情",
    "Review the method, then reopen the private workbench with the correct family and model preselected.": "查看方法后，再以正确的家族和模型预选状态重新打开私有工作台。",
    "Open family page": "打开家族页面",
    "Open teaching page": "打开教学页面",
    "Method sections": "方法分区",
    "Equation": "公式",
    "Paper template": "论文模板",
    "Data Lab Result": "数据实验室结果",
    "Loading result...": "正在加载结果...",
    "Result detail stays traceable here with metrics, specification, audit notes, figures, and export routes.": "结果详情在此可追踪查看，包括指标、设定、审计说明、图形和导出路径。",
    "Result type": "结果类型",
    "Raw JSON included": "包含原始 JSON",
    "Result Document": "结果文档",
    "Result Detail": "结果详情",
    "Open the exact workbench context, review the result, and export only after the audit trail is clear.": "打开精确工作台上下文，先复核结果，再在审计链清晰后导出。",
    "Result sections": "结果分区",
    "Audit trail": "审计轨迹",
    "Teaching Page": "教学页",
    "Loading teaching page...": "正在加载教学页...",
    "Teaching mode": "教学模式",
    "Guided reading": "引导阅读",
    "Teaching Document": "教学文档",
    "Use this page to understand the method before opening the private workbench.": "在打开私有工作台前，先用此页理解该方法。",
    "Teaching sections": "教学分区",
    "Core lessons": "核心要点",
    "Optimization Suite": "优化套件",
    "Build, benchmark, and reopen optimization suites with a lighter private workbench and a clearer export path.": "用更轻的私有工作台和更清晰的导出路径来构建、基准测试和重新打开优化套件。",
    "Use defaults": "使用默认项",
    "Optimization outputs stay in the active workspace and reopen from there.": "优化结果保存在当前工作区，并可从该处重新打开。",
    "Switch the active workspace here. Create or manage workspaces from the workspace hub.": "在此切换当前工作区。可在工作区中心创建或管理工作区。",
    "Catalog and rules": "目录与规则",
    "Catalog summary": "目录摘要",
    "Optimizer and benchmark counts will appear here.": "优化器和基准函数数量将显示在这里。",
    "Catalog browser": "目录浏览",
    "Catalog explorer will appear here.": "目录浏览器将显示在这里。",
    "Suite design": "套件设计",
    "Choose algorithms, benchmark functions, and run settings without losing sight of the current workspace and export requirements.": "选择算法、基准函数和运行设置，同时保持对当前工作区和导出要求的关注。",
    "Suite label": "套件标签",
    "Dimension": "维度",
    "Epochs": "迭代轮数",
    "Population": "种群规模",
    "Runs": "运行次数",
    "Workers": "工作线程",
    "Algorithms": "算法",
    "Benchmark functions": "基准函数",
    "Validation and export surfaces": "验证与导出面板",
    "Optimization Result": "优化结果",
    "Loading optimization suite...": "正在加载优化套件...",
    "This page keeps the suite snapshot, exports, tables, figures, and raw payload together as one result document.": "此页将套件快照、导出物、表格、图形和原始载荷集中为一个结果文档。",
    "Optimization suite": "优化套件",
    "All exports preserved": "全部导出已保留",
    "Optimization Suite Detail": "优化套件详情",
    "Use the same browser session as the optimization workbench when reopening private suite results.": "重新打开私有套件结果时，请使用与优化工作台相同的浏览器会话。",
    "Back to Optimization Lab": "返回优化实验室",
    "Data Lab module": "数据实验室模块",
    "Snapshot": "快照",
    "Exports": "导出",
  };

  const runtimeStrings = {
    "No workspace yet": "暂无工作区",
    "Use a saved provider preset or enter a custom OpenAI-compatible endpoint.": "使用已保存的供应商预设，或输入自定义 OpenAI 兼容端点。",
    "Public link copied.": "已复制公共链接。",
    "Something went wrong.": "发生错误。",
    "Initialization failed.": "初始化失败。",
    "Session refresh failed.": "会话刷新失败。",
    "Workspace data refresh failed. The session remains active.": "工作区数据刷新失败，但会话仍然有效。",
    "Optimization history refresh failed. The session remains active.": "优化历史刷新失败，但会话仍然有效。",
    "Public feed refreshed.": "公共信息流已刷新。",
    "No public briefing selected.": "尚未选择公共简报。",
    "Dataset profile refreshed.": "数据集画像已刷新。",
    "Generate a chart first.": "请先生成图表。",
    "Chart download started.": "图表下载已开始。",
    "No public edition yet": "暂无公共版本",
    "Temporarily unavailable": "暂时不可用",
    "No public briefing has been published yet.": "尚未发布公共简报。",
    "The public daily monitor will appear here after the first scheduled collection.": "首次计划采集完成后，公共日报监测将显示在这里。",
    "Recent multi-day view": "近期多日视图",
    "The rolling public summary will appear after public daily briefings accumulate.": "公共日报简报累计后，这里将显示滚动摘要。",
    "Method detail not found.": "未找到方法详情。",
    "Model method not found.": "未找到模型方法。",
    "Teaching guide not found.": "未找到教学指引。",
    "Method Detail": "方法详情",
    "Method": "方法",
    "Model Family": "模型家族",
    "Data Processing Family": "数据处理家族",
    "Family": "家族",
    "Required field or design checks": "必填字段或设计检查",
    "Normal output surfaces": "标准输出界面",
    "Manual verification checks": "人工核查项",
    "Inspect inputs": "检查输入",
    "Check the required variables and confirm that the dataset profile supports the fields this method needs.": "检查必需变量，并确认数据集画像支持该方法所需字段。",
    "Read the output package": "查看输出包",
    "Expect a result detail page with tables, figures when applicable, specification metadata, and an audit trail.": "预期会生成包含表格、图形（如适用）、设定元数据和审计轨迹的结果详情页。",
    "Equation not provided.": "未提供公式。",
    "Section": "章节",
    "Teaching page": "教学页",
    "Review the sections below before estimation.": "估计前请先查看下方内容。",
    "Lessons": "课程块",
    "Core lesson blocks": "核心教学块",
    "Paper blocks": "论文模块",
    "Paper reporting modules": "论文报告模块",
    "Preview tables": "预览表",
    "Illustrative table layouts": "示例表格布局",
    "Read the core lessons": "阅读核心要点",
    "Start with the lesson blocks to understand when the model is appropriate and what assumptions matter.": "先从核心要点开始，理解模型适用场景及关键假设。",
    "Check paper reporting": "检查论文报告方式",
    "Use the paper template and table preview to understand how the output should look in a paper.": "结合论文模板和表格预览，理解结果在论文中的呈现方式。",
    "Only after the teaching page is clear should you open the workbench and run the model on a private dataset.": "在教学页内容明确后，再打开工作台并在私有数据集上运行模型。",
    "Result": "结果",
    "No narrative available.": "暂无说明。",
    "No interpretation metadata is available for this result yet.": "该结果暂未提供解释性元数据。",
    "Interpretation headline": "解释总览",
    "Use the result together with its tables, figures, and sample metadata.": "请结合表格、图形和样本元数据一起解读结果。",
    "Quick replication facts": "快速复核要点",
    "Expected paper outputs": "预期论文输出",
    "No specification metadata available.": "暂无设定元数据。",
    "Strict suite rules": "严格套件规则",
    "Standard comparative benchmark": "标准比较基准",
    "This module will not downgrade statistical validation. A valid comparative suite must meet every condition below before Friedman, Wilcoxon, sign, and rank outputs are produced.": "该模块不会降低统计验证标准。在生成 Friedman、Wilcoxon、sign 和 rank 输出前，有效比较套件必须满足以下全部条件。",
    "Library Browser": "库浏览器",
    "Browse the available libraries by family before you add items into the suite builder.": "在将项目加入套件构建器前，先按家族浏览可用库。",
    "Mealpy library": "Mealpy 库",
    "Opfunu library": "Opfunu 库",
    "Validation & Export": "验证与导出",
    "Average convergence curve, per-algorithm process curves, radar and ranking visuals are exported as PNG assets.": "平均收敛曲线、单算法过程曲线、雷达图和排名图将导出为 PNG 资产。",
    "Friedman, Wilcoxon, sign, ranking, score, and raw process tables are exported as downloadable CSV assets.": "Friedman、Wilcoxon、sign、ranking、score 和原始过程表将导出为可下载的 CSV 资产。",
    "Every successful suite is stored in the current workspace and can be routed into cases or the private knowledge base.": "每个成功运行的套件都会保存到当前工作区，并可流转到案例或私有知识库。",
    "Create or select a workspace": "创建或选择工作区",
    "Choose a workspace to unlock private providers, literature, notes, and recurring jobs.": "选择一个工作区以解锁私有供应商、文献、笔记和定期任务。",
    "Select a workspace": "选择工作区",
    "Once a workspace is active, the cockpit will map providers, materials, and outputs.": "工作区激活后，驾驶舱将映射供应商、材料和结果。",
    "No private connections loaded yet.": "尚未加载任何私有连接。",
    "Private literature appears here after import.": "导入后这里将显示私有文献。",
    "Build case files to group workspace evidence.": "构建案例文件以归纳工作区证据。",
    "Knowledge records will accumulate here.": "知识记录会在此累积。",
    "Recurring jobs appear after setup.": "设置后这里将显示定期任务。",
    "Authenticate and choose a workspace.": "完成认证并选择一个工作区。",
    "Connect": "连接",
    "Save one provider or data source.": "保存一个供应商或数据源。",
    "Collect": "收集",
    "Import papers or create notes.": "导入论文或创建笔记。",
    "Reuse": "复用",
    "Schedule work or review outputs.": "安排任务或复核输出。",
    "Browse Public Daily Monitor": "浏览公共日报监测",
    "No private workspace activity yet.": "暂无私有工作区活动。",
    "Sign in and select a workspace to unlock guided cross-module flows.": "登录并选择工作区后，即可解锁跨模块引导流程。",
    "Connect your first provider": "连接第一个供应商",
    "Save an LLM or data-source connection so research generation and diagnostics can run inside this workspace.": "保存一个大模型或数据源连接，以便研究生成和诊断能够在此工作区运行。",
    "Collect private research materials": "收集私有研究材料",
    "Search OpenAlex, import papers, or switch to Data Lab to work with datasets.": "搜索 OpenAlex、导入论文，或切换到数据实验室处理数据集。",
    "Create reusable notes": "创建可复用笔记",
    "Convert papers and private outputs into searchable knowledge records inside the workspace.": "将论文和私有输出转化为工作区内可搜索的知识记录。",
    "Automate a recurring task": "自动化定期任务",
    "Add a daily job so the workspace continues to collect briefings without manual intervention.": "新增一个每日任务，使工作区在无需手动干预的情况下持续收集简报。",
    "Review and extend the workspace": "复核并扩展工作区",
    "Use the cockpit to jump to the most recent outputs and continue from the last completed step.": "使用驾驶舱跳转到最新输出，并从上一次完成的步骤继续。",
    "Saved model and data-source connections.": "已保存的模型和数据源连接。",
    "Private macro briefings stored in this workspace.": "存储在此工作区的私有宏观简报。",
    "Imported OpenAlex entries and follow-up notes.": "已导入的 OpenAlex 条目和后续笔记。",
    "Datasets, PDFs, charts, and processed outputs.": "数据集、PDF、图表和处理后的结果。",
    "Case files that group evidence across modules.": "用于归纳跨模块证据的案例文件。",
    "Manual notes, paper notes, and model outputs.": "手工笔记、论文笔记和模型结果。",
    "Recurring private jobs waiting to run.": "等待执行的私有定期任务。",
    "Workspace access": "工作区访问",
    "Provider setup": "供应商设置",
    "No provider yet. Start from Provider Center.": "尚无供应商。请从供应商中心开始。",
    "Research materials": "研究材料",
    "Import literature or move to Data Lab for datasets.": "导入文献，或切换到数据实验室处理数据集。",
    "Reusable outputs": "可复用输出",
    "Runtime provider management is unavailable in the current product scope.": "当前产品范围不提供运行时供应商管理。",
    "Disabled Surface": "已禁用页面",
    "Provider Center is unavailable": "供应商中心不可用",
    "Runtime provider management is not part of the current product scope. Use Research, Knowledge, Team Library, and Quality instead.": "运行时供应商管理不属于当前产品范围。请改用研究、知识库、团队库和质量页面。",
    "Research Agent": "研究 Agent",
    "Run evidence-backed research.": "运行有证据支撑的研究。",
    "Launch multimodal research runs, inspect evidence, compare candidate drafts, and retry blocked reports.": "启动多模态研究任务、检查证据、比较候选草稿，并重试被阻止的报告。",
    "Launch multimodal runs, inspect reviewer decisions, and push approved reports into the knowledge base.": "启动多模态任务、检查审查决策，并将通过的报告推入知识库。",
    "Research navigation": "研究导航",
    "Research session": "研究会话",
    "Select the active workspace, then launch a research run.": "选择当前工作区，然后启动研究任务。",
    "Research loop": "研究循环",
    "Planner, researcher, writer, reviewer, and knowledge-base save now live in one focused surface.": "规划、研究、写作、审查和知识库保存现在集中在一个页面中。",
    "Multimodal": "多模态",
    "Best-of-N drafts": "Best-of-N 草稿",
    "Retry blocked runs": "重试被阻止任务",
    "Research Queue": "研究队列",
    "No run selected": "未选择任务",
    "Launch a run or inspect a previous one from the right rail.": "启动任务，或从右侧栏检查历史任务。",
    "Back to Workspace": "返回工作区",
    "Eval Snapshot": "评估快照",
    "Awaiting data": "等待数据",
    "Approved and blocked runs will surface prompt-optimization candidates here.": "通过和被阻止的任务会在此显示提示词优化候选。",
    "Launch": "启动",
    "New research run": "新建研究任务",
    "Research topic": "研究主题",
    "Research question (optional)": "研究问题（可选）",
    "Extra instructions for the planner, writer, or reviewer": "给规划器、写作者或审查者的额外说明",
    "Mode": "模式",
    "Standard": "标准",
    "Deep Research": "深度研究",
    "Draft Variants": "草稿变体",
    "Auto": "自动",
    "Knowledge Case": "知识案例",
    "No case": "无案例",
    "Attachments": "附件",
    "Choose workspace assets to feed the run.": "选择要提供给任务的工作区资产。",
    "Start research run": "启动研究任务",
    "Runs": "任务",
    "Recent research runs": "最近研究任务",
    "Selected Run": "已选任务",
    "Run detail": "任务详情",
    "Retry": "重试",
    "Rewrite blocked run": "重写被阻止任务",
    "What should the writer or reviewer fix on retry?": "重试时写作者或审查者应修复什么？",
    "Retry Draft Variants": "重试草稿变体",
    "Keep current": "保持当前",
    "Extra attachments": "额外附件",
    "Add more assets when the reviewer says evidence is weak.": "当审查者认为证据薄弱时，添加更多资产。",
    "Retry selected run": "重试所选任务",
    "Connection test succeeded.": "连接测试成功。",
    "Optimization suite completed.": "优化套件已完成。",
    "Failed to load the full knowledge note.": "加载完整知识笔记失败。",
    "Account created.": "账户已创建。",
    "Signed in.": "已登录。",
    "Signed out.": "已退出登录。",
    "Password reset email sent if the account exists.": "如果账户存在，重置邮件已发送。",
    "Password reset completed. Sign in with the new password.": "密码已重置，请使用新密码登录。",
    "Workspace created.": "工作区已创建。",
    "Private briefing generated.": "私有简报已生成。",
    "Literature imported into your private library.": "文献已导入到你的私有文库。",
    "File uploaded.": "文件已上传。",
    "Private note updated.": "私有笔记已更新。",
    "Private note saved.": "私有笔记已保存。",
    "Private case updated.": "私有案例已更新。",
    "Private case created.": "私有案例已创建。",
    "Private daily job created.": "私有日常任务已创建。",
    "Variable guide suggestions applied to the workbench.": "变量向导建议已应用到工作台。",
    "Variable guide updated.": "变量向导已更新。",
    "Prepared analysis sample created.": "已创建分析样本。",
    "Chart generated.": "图表已生成。",
    "Connection deleted.": "连接已删除。",
    "Dataset loaded into Data Lab.": "数据集已载入数据实验室。",
    "Cleaned dataset generated.": "已生成清洗后数据集。",
    "Download started.": "下载已开始。",
    "Private paper download started.": "私有论文下载已开始。",
    "Result JSON download started.": "结果 JSON 下载已开始。",
    "Active case updated.": "当前案例已更新。",
    "Case not found.": "未找到案例。",
    "Case loaded for editing.": "案例已载入编辑器。",
    "Case deleted.": "案例已删除。",
    "Case item removed.": "案例条目已移除。",
    "Knowledge note loaded into the editor.": "知识笔记已载入编辑器。",
    "Knowledge note archived.": "知识笔记已归档。",
    "Knowledge note restored.": "知识笔记已恢复。",
    "Knowledge note deleted.": "知识笔记已删除。",
    "Knowledge note copied.": "知识笔记已复制。",
    "Knowledge note download started.": "知识笔记下载已开始。",
    "Headline restored to the public edition.": "标题已恢复到公共版本。",
    "Headline removed from the public edition.": "标题已从公共版本移除。",
  };

  const metadataStrings = {
    "Sample Preparation": "样本准备",
    "Cleaning & Transforms": "清洗与变换",
    "Time-Series Features": "时间序列特征",
    "Visualization": "可视化",
    "Econometrics Baseline": "计量经济学基础",
    "Time Series & Econometric Finance": "时间序列与计量金融",
    "Corporate Finance": "公司金融",
    "Risk Management": "风险管理",
    "Derivatives Pricing": "衍生品定价",
    "Macro Finance & DSGE": "宏观金融与 DSGE",
    "Portfolio Allocation": "资产组合配置",
    "Asset Pricing": "资产定价",
    "Data Processing": "数据处理",
    "Build an analysis-ready sample before cleaning, plotting, or model estimation.": "在清洗、绘图或模型估计前先构建可用于分析的样本。",
    "Model setup and execution.": "模型设置与执行。",
    "Review the latest outputs and export the result package.": "查看最新输出并导出结果包。",
    "Browse recent processing and model runs.": "浏览最近的数据处理与模型运行记录。",
    "Normalize variables, cap extremes, and generate transformed regressors with explicit thresholds.": "对变量做标准化、截尾并在明确阈值下生成变换后的回归变量。",
    "Generate differences, returns, lags, leads, and rolling diagnostics before time-series or finance models.": "在时间序列或金融模型之前生成差分、收益率、滞后、超前和滚动诊断。",
    "Render line, scatter, bar, and histogram charts and export them as PNG assets.": "渲染折线图、散点图、柱状图和直方图，并将其导出为 PNG 资产。",
    "Classical empirical economics workflows for treatment effects, structural breaks, and panel-style identification.": "用于处理效应、结构性变化和面板识别的经典实证经济学流程。",
    "Forecasting, volatility, impulse-response, and connectedness models for ordered macro-finance data.": "面向有序宏观金融数据的预测、波动率、脉冲响应和联动性模型。",
    "Official OpenAI API connection for GPT models.": "面向 GPT 模型的官方 OpenAI API 连接。",
    "DeepSeek OpenAI-compatible chat completions endpoint.": "DeepSeek 的 OpenAI 兼容聊天补全端点。",
    "Google Gemini via the OpenAI-compatible Gemini API.": "通过 OpenAI 兼容 Gemini API 接入 Google Gemini。",
    "Anthropic Claude via the OpenAI SDK compatibility layer.": "通过 OpenAI SDK 兼容层接入 Anthropic Claude。",
    "Moonshot AI Kimi models through the Moonshot API.": "通过 Moonshot API 接入 Moonshot AI 的 Kimi 模型。",
    "Custom OpenAI-compatible endpoint such as OpenRouter or self-hosted gateways.": "自定义 OpenAI 兼容端点，例如 OpenRouter 或自托管网关。",
    "Federal Reserve Economic Data API for macroeconomic series.": "用于宏观经济序列的美联储经济数据 API。",
  };

  const translations = Object.freeze(Object.assign({}, titleStrings, commonStrings, authStrings, moduleStrings, runtimeStrings, metadataStrings));
  const patterns = [
    { pattern: /^(.+)\s\|\sEconomic Research Platform$/, replace: (_, title) => `${title} | 经济研究平台` },
    { pattern: /^Updated (.+)$/, replace: (_, value) => `已更新 ${value}` },
    { pattern: /^(.+) Teaching Page$/, replace: (_, name) => `${name} 教学页` },
    { pattern: /^Loaded (\d+)-day summary\.$/, replace: (_, days) => `已载入 ${days} 天摘要。` },
    { pattern: /^Found (\d+) literature items\.$/, replace: (_, count) => `已找到 ${count} 条文献。` },
    { pattern: /^Saved connection: (.+)$/, replace: (_, label) => `已保存连接：${label}` },
    { pattern: /^Paper Library PDF import finished: (\d+) imported, (\d+) skipped, (\d+) failed\.$/, replace: (_, imported, skipped, failed) => `论文库 PDF 导入完成：${imported} 个已导入，${skipped} 个已跳过，${failed} 个失败。` },
    { pattern: /^Knowledge note import finished: (\d+) processed, (\d+) failed\.$/, replace: (_, processed, failed) => `知识笔记导入完成：${processed} 个已处理，${failed} 个失败。` },
    { pattern: /^(Already linked in case|Added to case): (.+)$/, replace: (_, prefix, title) => `${prefix === "Already linked in case" ? "案例中已存在关联" : "已加入案例"}：${title}` },
    { pattern: /^(.+) completed\.$/, replace: (_, label) => `${label} 已完成。` },
    { pattern: /^Loaded profile for (.+)\.$/, replace: (_, label) => `已加载 ${label} 的画像。` },
    { pattern: /^(.*?)(Connection test succeeded\.)$/, replace: (_, prefix) => `${prefix}${translations["Connection test succeeded."]}` },
    { pattern: /^(Private copy already exists|Paper imported): (.+)$/, replace: (_, prefix, title) => `${prefix === "Private copy already exists" ? "私有副本已存在" : "论文已导入"}：${title}` },
    { pattern: /^(Follow-up note already exists|Follow-up note created): (.+)$/, replace: (_, prefix, title) => `${prefix === "Follow-up note already exists" ? "后续笔记已存在" : "后续笔记已创建"}：${title}` },
    { pattern: /^Template loaded: (.+)$/, replace: (_, label) => `模板已载入：${label}` },
    { pattern: /^Workspace digest created: (.+)$/, replace: (_, label) => `工作区摘要已创建：${label}` },
    { pattern: /^(Briefing note already exists|Briefing captured in the knowledge base): (.+)$/, replace: (_, prefix, title) => `${prefix === "Briefing note already exists" ? "简报笔记已存在" : "简报已收录到知识库"}：${title}` },
    { pattern: /^(Knowledge note already exists|Saved to knowledge base): (.+)$/, replace: (_, prefix, title) => `${prefix === "Knowledge note already exists" ? "知识笔记已存在" : "已保存到知识库"}：${title}` },
    { pattern: /^Algorithms >= (.+)$/, replace: (_, value) => `算法 >= ${value}` },
    { pattern: /^Functions >= (.+)$/, replace: (_, value) => `函数 >= ${value}` },
    { pattern: /^Runs >= (.+)$/, replace: (_, value) => `运行次数 >= ${value}` },
    { pattern: /^(\d+) available$/, replace: (_, count) => `${count} 个可用` },
    { pattern: /^(\d+) discovered$/, replace: (_, count) => `已发现 ${count} 个` },
    { pattern: /^\+(\d+) more$/, replace: (_, count) => `另有 ${count} 个` },
    { pattern: /^Default base URL: (.+)$/, replace: (_, url) => `默认 Base URL：${url}` },
    { pattern: /^Default model: (.+)$/, replace: (_, model) => `默认模型：${model}` },
    { pattern: /^Core equation: (.+)$/, replace: (_, equation) => `核心公式：${equation}` },
    { pattern: /^Rows after prepare: (.+)$/, replace: (_, value) => `准备后行数：${value}` },
    { pattern: /^Equation: (.+)$/, replace: (_, value) => `公式：${value}` },
    { pattern: /^Rows used: (.+)$/, replace: (_, value) => `使用行数：${value}` },
    { pattern: /^Covariance: (.+)$/, replace: (_, value) => `协方差：${value}` },
    { pattern: /^Figures: (\d+)$/, replace: (_, count) => `图形：${count}` },
    { pattern: /^Tables: (\d+)$/, replace: (_, count) => `表格：${count}` },
    { pattern: /^Signed in as (.+) with (.+) selected\.$/, replace: (_, user, workspace) => `当前已以 ${user} 登录，并选择了 ${workspace}。` },
    { pattern: /^(\d+) provider connection\(s\) saved\.$/, replace: (_, count) => `已保存 ${count} 个供应商连接。` },
    { pattern: /^(\d+) papers and (\d+) assets currently available\.$/, replace: (_, papers, assets) => `当前可用论文 ${papers} 篇、资产 ${assets} 项。` },
    { pattern: /^(\d+) notes, (\d+) briefings, (\d+) schedules\.$/, replace: (_, notes, briefings, schedules) => `当前有 ${notes} 条笔记、${briefings} 份简报、${schedules} 个日程。` },
  ];

  const runtime = {
    controller: null,
    observer: null,
    syncing: false,
  };
  const originalTextNodes = new WeakMap();
  const originalAttributes = new WeakMap();

  function normalizeLocale(locale) {
    return locale === "zh-CN" ? "zh-CN" : "en";
  }

  function resolveInitialLocale() {
    try {
      const stored = localStorage.getItem(LOCALE_KEY);
      if (SUPPORTED_LOCALES.has(stored)) {
        return stored;
      }
    } catch {
      // Ignore storage access issues.
    }
    const browserLocale = (navigator.language || navigator.languages?.[0] || "en").toLowerCase();
    return browserLocale.startsWith("zh") ? "zh-CN" : "en";
  }

  function currentLocale() {
    return normalizeLocale(runtime.controller?.getLocale?.() || document.documentElement.lang || resolveInitialLocale());
  }

  function syncDocumentLocale(locale = currentLocale()) {
    const normalized = normalizeLocale(locale);
    document.documentElement.lang = normalized;
    document.documentElement.dataset.locale = normalized;
  }

  function translateInlineText(value) {
    if (currentLocale() !== "zh-CN" || typeof value !== "string") {
      return value;
    }
    const match = value.match(/^(\s*)(.*?)(\s*)$/s);
    const leading = match?.[1] || "";
    const core = match?.[2] || "";
    const trailing = match?.[3] || "";
    if (!core) {
      return value;
    }
    if (Object.hasOwn(translations, core)) {
      return `${leading}${translations[core]}${trailing}`;
    }
    for (const entry of patterns) {
      const result = core.match(entry.pattern);
      if (result) {
        return `${leading}${entry.replace(...result)}${trailing}`;
      }
    }
    return value;
  }

  function t(key, params = {}) {
    const template = translateInlineText(key);
    return String(template).replace(/\{(\w+)\}/g, (_, token) => (token in params ? String(params[token]) : `{${token}}`));
  }

  function localizeValue(value) {
    if (currentLocale() !== "zh-CN") {
      return value;
    }
    if (typeof value === "string") {
      return translateInlineText(value);
    }
    if (Array.isArray(value)) {
      return value.map((item) => localizeValue(item));
    }
    if (value && typeof value === "object") {
      return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, localizeValue(item)]));
    }
    return value;
  }

  function isSkipped(node) {
    const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement;
    return Boolean(element && element.closest(SKIP_SELECTOR));
  }

  function originalAttributeMap(element) {
    const existing = originalAttributes.get(element);
    if (existing) {
      return existing;
    }
    const next = new Map();
    originalAttributes.set(element, next);
    return next;
  }

  function translateAttribute(element, attrName, markerName = "") {
    if (!element || isSkipped(element)) {
      return;
    }
    const key = markerName ? element.getAttribute(markerName) : "";
    const originals = originalAttributeMap(element);
    const current = element.getAttribute(attrName) || "";
    const stored = originals.get(attrName);
    const translatedStored = stored ? t(stored) : "";
    if (!key && (!stored || (current !== stored && current !== translatedStored))) {
      originals.set(attrName, current);
    }
    const original = key || originals.get(attrName) || current;
    if (!original) {
      return;
    }
    const translated = t(original);
    if (translated !== element.getAttribute(attrName)) {
      element.setAttribute(attrName, translated);
    }
  }

  function translateTextNode(node) {
    if (!node || isSkipped(node)) {
      return;
    }
    const current = node.nodeValue || "";
    const stored = originalTextNodes.get(node);
    const translatedStored = stored ? translateInlineText(stored) : "";
    if (!stored || (current !== stored && current !== translatedStored)) {
      originalTextNodes.set(node, current);
    }
    const translated = translateInlineText(originalTextNodes.get(node) || current);
    if (translated !== node.nodeValue) {
      node.nodeValue = translated;
    }
  }

  function translateElement(element) {
    if (!element || isSkipped(element)) {
      return;
    }
    const textKey = element.getAttribute("data-i18n");
    if (textKey && element.childElementCount === 0) {
      const translated = t(textKey);
      if (translated !== element.textContent) {
        element.textContent = translated;
      }
    }
    translateAttribute(element, "placeholder", "data-i18n-placeholder");
    translateAttribute(element, "aria-label", "data-i18n-aria-label");
    translateAttribute(element, "title", "data-i18n-title");
    translateAttribute(element, "value", "data-i18n-value");
    translateAttribute(element, "content", "data-i18n-content");
    if (element.matches("input[type='button'], input[type='submit'], input[type='reset']")) {
      translateAttribute(element, "value");
    }
  }

  function applyLocale(root = document.documentElement) {
    syncDocumentLocale();
    if (runtime.syncing) {
      updateLocaleSwitcherState();
      return;
    }
    runtime.syncing = true;
    try {
      const scope = root?.nodeType === Node.DOCUMENT_NODE ? root.documentElement : root;
      if (!scope) {
        return;
      }
      if (scope.nodeType === Node.TEXT_NODE) {
        translateTextNode(scope);
        return;
      } else if (scope.nodeType === Node.ELEMENT_NODE) {
        translateElement(scope);
        scope.querySelectorAll("*").forEach((element) => translateElement(element));
      }
      const walkerRoot = scope.nodeType === Node.ELEMENT_NODE ? scope : document.documentElement;
      const walker = document.createTreeWalker(
        walkerRoot,
        NodeFilter.SHOW_TEXT,
        {
          acceptNode(node) {
            return node.nodeValue?.trim() && !isSkipped(node) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
          },
        },
      );
      while (walker.nextNode()) {
        translateTextNode(walker.currentNode);
      }
    } finally {
      runtime.syncing = false;
      updateLocaleSwitcherState();
    }
  }

  function createLocaleSwitcher() {
    const wrapper = document.createElement("div");
    wrapper.className = "locale-switcher";
    wrapper.setAttribute("data-locale-switcher", "true");
    wrapper.setAttribute("data-i18n-skip", "true");
    wrapper.innerHTML = `
      <button type="button" class="locale-switcher__button" data-locale-choice="zh-CN">中文</button>
      <span class="locale-switcher__divider" aria-hidden="true">|</span>
      <button type="button" class="locale-switcher__button" data-locale-choice="en">EN</button>
    `;
    wrapper.querySelectorAll("[data-locale-choice]").forEach((button) => {
      button.addEventListener("click", () => {
        runtime.controller?.setLocale?.(button.getAttribute("data-locale-choice") || "en");
      });
    });
    return wrapper;
  }

  function mountSwitchers() {
    SWITCHER_HOSTS.forEach((selector) => {
      document.querySelectorAll(selector).forEach((host) => {
        if (!host.querySelector("[data-locale-switcher]")) {
          const switcher = createLocaleSwitcher();
          if (host.matches(".suite-page-kpis")) {
            host.prepend(switcher);
          } else {
            host.appendChild(switcher);
          }
        }
      });
    });
    updateLocaleSwitcherState();
  }

  function updateLocaleSwitcherState() {
    document.querySelectorAll("[data-locale-choice]").forEach((button) => {
      const isActive = button.getAttribute("data-locale-choice") === currentLocale();
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function ensureObserver() {
    if (currentLocale() !== "zh-CN") {
      runtime.observer?.disconnect();
      runtime.observer = null;
      return;
    }
    if (runtime.observer) {
      return;
    }
    runtime.observer = new MutationObserver((mutations) => {
      if (runtime.syncing) {
        return;
      }
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          applyLocale(mutation.target);
          continue;
        }
        if (mutation.type === "attributes") {
          applyLocale(mutation.target);
          continue;
        }
        mutation.addedNodes.forEach((node) => applyLocale(node));
      }
    });
    runtime.observer.observe(document.documentElement, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "aria-label", "title", "value"],
    });
  }

  function mount(controller) {
    runtime.controller = controller || runtime.controller;
    syncDocumentLocale();
    mountSwitchers();
    applyLocale(document.documentElement);
    ensureObserver();
  }

  function autoMount() {
    if (runtime.controller) {
      return;
    }
    mount({
      getLocale: resolveInitialLocale,
      setLocale: (locale) => {
        const normalized = normalizeLocale(locale);
        try {
          localStorage.setItem(LOCALE_KEY, normalized);
        } catch {
          // Ignore storage access issues.
        }
        window.location.reload();
      },
    });
  }

  window.erpLocale = {
    normalizeLocale,
    resolveInitialLocale,
    syncDocumentLocale,
    translateInlineText,
    t,
    localizeValue,
    applyLocale,
    ensureObserver,
    mount,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMount, { once: true });
  } else {
    queueMicrotask(autoMount);
  }
})();
