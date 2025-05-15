
export default {
  bootstrap: () => import('./main.server.mjs').then(m => m.default),
  inlineCriticalCss: true,
  baseHref: './',
  locale: undefined,
  routes: [
  {
    "renderMode": 2,
    "route": "/"
  }
],
  entryPointToBrowserMapping: undefined,
  assets: {
    'index.csr.html': {size: 2193, hash: '8398e9465f93ea7becf04410625be83d9f3ea411b28313d0d9dbc8eadd55b44e', text: () => import('./assets-chunks/index_csr_html.mjs').then(m => m.default)},
    'index.server.html': {size: 1006, hash: '2907af8177253e4b944252f90d57e1ba0f200263b90b91a458c9c24d6cb9cca6', text: () => import('./assets-chunks/index_server_html.mjs').then(m => m.default)},
    'index.html': {size: 7611, hash: '553fa1f25c9e336d0ea3253b3e4f276a40527c9c0e96cc2dc1a92bb95b372257', text: () => import('./assets-chunks/index_html.mjs').then(m => m.default)},
    'styles-Z7HM6NKM.css': {size: 10900, hash: 'ItnpHCFyKh0', text: () => import('./assets-chunks/styles-Z7HM6NKM_css.mjs').then(m => m.default)}
  },
};
