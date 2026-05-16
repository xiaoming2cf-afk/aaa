import { NavLink } from "react-router-dom";

import { useI18n } from "../../i18n";
import type { RouteMetadata } from "./types";

type RouteNavProps = {
  routes: RouteMetadata[];
};

export function RouteNav({ routes }: RouteNavProps): JSX.Element {
  const { t } = useI18n();

  return (
    <nav className="ops-nav" aria-label="Primary sections">
      {routes.map((route) => {
        const RouteIcon = route.icon;
        const label = route.navKey ? t(route.navKey) : route.navLabel;

        return (
          <NavLink key={route.path} to={route.path} className={({ isActive }) => isActive ? "ops-nav-link active" : "ops-nav-link"}>
            <RouteIcon aria-hidden="true" size={18} />
            <span>{label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
