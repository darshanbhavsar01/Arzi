import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Self-hosted IBM Plex. Each file declares every subset with a unicode-range, so the browser
// fetches only what a page uses (latin, plus latin-ext for the ₹ sign).
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';

import { App } from '@/app/App';
import '@/styles/global.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root element #root is missing from index.html');
}

createRoot(container).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
