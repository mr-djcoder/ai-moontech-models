import { NavLink, Outlet } from "react-router-dom";

export default function App() {
  return (
    <>
      <header className="top">
        <div className="wrap">
          <div className="brand">
            <span className="mark" aria-hidden="true"><span className="moon"></span></span>
            <span>MoonTech Casting<small>virtual talent studio</small></span>
          </div>
          <nav className="tabs">
            <NavLink to="/" end className={({ isActive }) => (isActive ? "on" : "")}>Roster</NavLink>
            <NavLink to="/new" className={({ isActive }) => (isActive ? "on" : "")}>Casting console</NavLink>
          </nav>
        </div>
      </header>
      <main className="wrap">
        <Outlet />
      </main>
    </>
  );
}
