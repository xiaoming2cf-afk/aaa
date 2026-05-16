import { RefreshCw } from "lucide-react";

import { useI18n } from "../../i18n";
import { Button } from "../ui";
import { ScopePanel } from "./ScopePanel";
import type { RouteMetadata, Team, Workspace } from "./types";

type CommandBarProps = {
  currentRoute: RouteMetadata;
  currentWorkspace?: Workspace;
  currentTeam?: Team;
  workspaces: Workspace[];
  teams: Team[];
  workspaceId: string;
  onWorkspaceChange: (value: string) => void;
  teamId: string;
  onTeamChange: (value: string) => void;
  onRefreshAll: () => void;
};

export function CommandBar({
  currentRoute,
  currentWorkspace,
  currentTeam,
  workspaces,
  teams,
  workspaceId,
  onWorkspaceChange,
  teamId,
  onTeamChange,
  onRefreshAll,
}: CommandBarProps): JSX.Element {
  const CurrentIcon = currentRoute.icon;
  const { language, t, toggleLanguage } = useI18n();
  const routeEyebrow = currentRoute.eyebrowKey ? t(currentRoute.eyebrowKey) : currentRoute.eyebrow;
  const routeTitle = currentRoute.titleKey ? t(currentRoute.titleKey) : currentRoute.title;

  return (
    <header className="ops-command-bar">
      <div className="ops-command-title">
        <p className="eyebrow">{routeEyebrow}</p>
        <h2><CurrentIcon aria-hidden="true" size={22} /> {routeTitle}</h2>
        <p className="ops-command-scope">
          {currentWorkspace?.name || t("app.workspacePending")} / {currentTeam?.name || t("app.noTeamSelected")}
        </p>
      </div>
      <div className="ops-command-actions">
        <label className="ops-command-search">
          <span>{t("app.search")}</span>
          <input aria-label={t("app.search")} placeholder={t("app.search")} />
        </label>
        <ScopePanel
          workspaces={workspaces}
          teams={teams}
          workspaceId={workspaceId}
          onWorkspaceChange={onWorkspaceChange}
          teamId={teamId}
          onTeamChange={onTeamChange}
        />
        <Button
          type="button"
          variant="ghost"
          icon={<RefreshCw size={16} aria-hidden="true" />}
          onClick={onRefreshAll}
        >
          {t("app.refreshAll")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="ops-language-toggle"
          aria-label="EN / 中文"
          onClick={toggleLanguage}
        >
          {language === "zh" ? "EN / 中文" : "中文 / EN"}
        </Button>
        <span className="ops-avatar" aria-label="Signed in user">{(currentTeam?.name || currentWorkspace?.name || "VK").slice(0, 2).toUpperCase()}</span>
      </div>
    </header>
  );
}
