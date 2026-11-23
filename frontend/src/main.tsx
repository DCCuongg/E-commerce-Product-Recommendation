import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import App from './App';
import { PreferencesProvider } from './context/PreferencesContext';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><BrowserRouter><PreferencesProvider><AuthProvider><App/></AuthProvider></PreferencesProvider></BrowserRouter></React.StrictMode>
);
