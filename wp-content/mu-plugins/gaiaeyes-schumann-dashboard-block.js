(function (blocks, element, i18n) {
  if (!blocks || !element) {
    return;
  }

  var el = element.createElement;

  blocks.registerBlockType('gaiaeyes/schumann-dashboard', {
    apiVersion: 2,
    title: i18n.__('Schumann Dashboard', 'gaiaeyes'),
    description: i18n.__('Gauge, heatmap, and pulse chart backed by Gaia Eyes Schumann APIs.', 'gaiaeyes'),
    category: 'widgets',
    icon: 'chart-area',
    supports: {
      html: false,
    },
    edit: function () {
      return el(
        'div',
        { className: 'gaiaeyes-schumann-dashboard-editor-placeholder' },
        i18n.__('Schumann Dashboard block: preview renders on the frontend.', 'gaiaeyes')
      );
    },
    save: function () {
      return null;
    },
  });
})(window.wp && window.wp.blocks, window.wp && window.wp.element, window.wp && window.wp.i18n);
