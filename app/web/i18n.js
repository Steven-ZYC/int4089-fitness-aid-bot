/* Local, explicit catalogs. Original strings are stable message identifiers. */
'use strict';
window.FitCoachI18n = (() => {
  const supported = ['zh-CN', 'en', 'zh-HK'];
  let messages = {}, locale = 'zh-CN', staticText = [], staticAttrs = [], patterns = [];
  const escape = value => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  function t(value) {
    if (typeof value !== 'string') return value;
    if (value.includes('\n')) return value.split('\n').map(t).join('\n');
    if (value.startsWith('· ')) return '· '+t(value.slice(2));
    if (Object.hasOwn(messages[locale] || {}, value)) return messages[locale][value];
    for (const {key, regex} of patterns) {
      const match = value.match(regex);
      if (match) return messages[locale][key].replace(/\{(\d+)\}/g, (_, n) => t(match[Number(n) + 1]));
    }
    return value; // Preserve raw firmware diagnostics and unknown technical messages.
  }
  function rememberStatic() {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (['SCRIPT','STYLE','TEXTAREA'].includes(node.parentElement.tagName)) continue;
      const original = node.textContent, key = original.trim();
      if (Object.hasOwn(messages['zh-CN'], key)) staticText.push({node, original, key});
    }
    for (const el of document.querySelectorAll('[aria-label],[alt],[title]')) {
      for (const attr of ['aria-label','alt','title']) {
        const key = el.getAttribute(attr);
        if (key && Object.hasOwn(messages['zh-CN'], key)) staticAttrs.push({el, attr, key});
      }
    }
  }
  function setLocale(next, notify = true) {
    locale = supported.includes(next) ? next : 'zh-CN';
    document.documentElement.lang = locale;
    document.title = t('FitCoach AI · 运动控制台');
    for (const {node,original,key} of staticText) if (node.isConnected) node.textContent = original.replace(key,t(key));
    for (const {el,attr,key} of staticAttrs) el.setAttribute(attr,t(key));
    const selector = document.getElementById('language');
    selector.value = locale;
    try { localStorage.setItem('fitcoach.locale',locale); } catch (_) {}
    if (notify) window.dispatchEvent(new CustomEvent('fitcoach:language', {detail:locale}));
  }
  async function init() {
    const response = await fetch('/locales.json');
    if (!response.ok) throw Error('Unable to load language catalog');
    messages = await response.json();
    patterns = Object.keys(messages['zh-CN']).filter(key => key.includes('{0}')).map(key => ({
      key, regex: new RegExp('^'+key.split(/\{\d+\}/).map(escape).join('([\\s\\S]*?)')+'$')
    }));
    rememberStatic();
    let saved;
    try { saved = localStorage.getItem('fitcoach.locale'); } catch (_) {}
    const browser = navigator.language || '';
    const preferred = browser.startsWith('zh') ? (/HK|TW|Hant/i.test(browser) ? 'zh-HK' : 'zh-CN') : 'en';
    setLocale(supported.includes(saved) ? saved : preferred,false);
    document.getElementById('language').addEventListener('change',event=>setLocale(event.target.value));
  }
  return {t, init, setLocale, get locale() { return locale; }};
})();
