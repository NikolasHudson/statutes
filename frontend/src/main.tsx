import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';
import Shell from './Shell.tsx';

const params = new URLSearchParams(window.location.search);
const showDemo = params.has('demo');
const Root = showDemo ? App : Shell;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
);
