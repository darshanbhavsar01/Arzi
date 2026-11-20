/** Phase 0 placeholder shell; the desk app shell replaces it in Phase 5. */
export function App() {
  return (
    <div className="placeholder">
      <main className="placeholder__main">
        <img
          className="placeholder__logo"
          src="/brand/arzi-logo.png"
          alt=""
          width={96}
          height={96}
        />
        <h1 className="placeholder__title">Arzi</h1>
        <p className="placeholder__lead">
          Your claim, defended before and after the insurer says no. The claims desk workspace is
          being set up.
        </p>
      </main>
      <footer className="placeholder__footer">
        Arzi is decision support. A qualified person reviews and signs every appeal.
      </footer>
    </div>
  );
}
