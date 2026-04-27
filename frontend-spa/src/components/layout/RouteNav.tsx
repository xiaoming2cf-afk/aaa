import { NavLink } from "react-router-dom";

import type { RouteMetadata } from "./types";

type RouteNavProps = {
  routes: RouteMetadata[];
};

export function RouteNav({ routes }: RouteNavProps): JSX.Element {
  return (
    <nav className="ops-nav" aria-label="Primary sections">
      {routes.map((route) => {
        const RouteIcon = route.icon;

        return (
          <NavLink key={route.path} to={route.path} className={({ isActive }) => isActive ? "ops-nav-link active" : "ops-nav-link"}>
            <RouteIcon aria-hidden="true" size={18} />
            <span>{route.navLabel}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
