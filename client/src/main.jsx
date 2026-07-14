import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './style.css'

const nativeFetch = window.fetch.bind(window)
window.fetch = (input, init = {}) => nativeFetch(input, { credentials: 'include', ...init })

const root = ReactDOM.createRoot(document.getElementById('root'))
root.render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
