
export default {
  bootstrap: () => import('./main.server.mjs').then(m => m.default),
  inlineCriticalCss: true,
  baseHref: '/',
  locale: undefined,
  routes: [
  {
    "renderMode": 2,
    "route": "/"
  }
],
  entryPointToBrowserMapping: undefined,
  assets: {
    'index.csr.html': {size: 2192, hash: '2cfcf5ba5ba45c264b92eacb6c04a857caa8462ce594ad564aa0a12de517902d', text: () => import('./assets-chunks/index_csr_html.mjs').then(m => m.default)},
    'index.server.html': {size: 1005, hash: '4be3bda6933ee2a99030804dd48e836b51735d24b969a2fe8ab9e25ba1bda45c', text: () => import('./assets-chunks/index_server_html.mjs').then(m => m.default)},
    'index.html': {size: 3951, hash: '5ffd1782db3293dbec53f31ea191097988109369aefe2fc6934c548eb0377bfd', text: () => import('./assets-chunks/index_html.mjs').then(m => m.default)},
    'styles-GD6BWSNL.css': {size: 8901, hash: 'ookTrh7HPwQ', text: () => import('./assets-chunks/styles-GD6BWSNL_css.mjs').then(m => m.default)}
  },
};
